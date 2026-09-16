"""Moteur comptable : soldes, agrégats, clôtures, comptage de caisse, imports, bilans."""
from __future__ import annotations

import csv
import io
import logging
import re
from calendar import monthrange
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import models, transaction
from django.utils import timezone

from audit import services as audit
from core.models import Setting
from finance.models import (
    DEFAULT_EXPENSES,
    DEFAULT_INCOMES,
    MODES,
    Account,
    AccountOpening,
    BalanceRun,
    CashCount,
    Category,
    Entry,
    ImportBatch,
    MonthLock,
)

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")
MODE_LABELS = {value: str(label) for value, label in MODES}


class FinanceError(Exception):
    """Erreur métier de la trésorerie (message directement affichable)."""


# ------------------------------------------------------------------ référentiel

def ensure_default_categories() -> None:
    """Crée les catégories par défaut (7 dépenses, 6 recettes) si elles manquent."""
    with transaction.atomic():
        for index, label in enumerate(DEFAULT_EXPENSES):
            Category.objects.get_or_create(label=label, kind="D",
                                          defaults={"order": (index + 1) * 10, "color": "#a76a43"})
        for index, label in enumerate(DEFAULT_INCOMES):
            Category.objects.get_or_create(label=label, kind="R",
                                          defaults={"order": (index + 1) * 10, "color": "#33556e"})


GAP_LABEL = "Écart de caisse"


def ensure_gap_category() -> None:
    """Catégorie dédiée aux régularisations de caisse (charge ou produit)."""
    Category.objects.get_or_create(label=GAP_LABEL, kind="D", defaults={"order": 990, "color": "#8a3b3b"})
    Category.objects.get_or_create(label=GAP_LABEL, kind="R", defaults={"order": 990, "color": "#3b6f4a"})


def ensure_accounts() -> None:
    """Garantit au minimum un compte bancaire et le coffre de calcul."""
    with transaction.atomic():
        if not Account.objects.filter(type="bank").exists():
            Account.objects.get_or_create(name="Compte bancaire", defaults={"type": "bank", "order": 10})
        Account.objects.get_or_create(name="Coffre-fort",
                                     defaults={"type": "safe", "is_safe": True, "order": 90,
                                               "note": "Solde calculé à partir des mouvements."})


def active_accounts() -> list[Account]:
    return list(Account.objects.filter(active=True).order_by("order", "name"))


# ------------------------------------------------------------------ périodes

def month_bounds(year, month: int, year_number: int) -> tuple[date, date]:
    first = date(year_number, month, 1)
    return first, date(year_number, month, monthrange(year_number, month)[1])


def months_for(year) -> list[dict[str, Any]]:
    """Liste des mois de l'année scolaire, du plus ancien au plus récent."""
    items = []
    for year_number, month in year.months():
        items.append({"month": month, "year": year_number,
                      "label": "%02d/%d" % (month, year_number),
                      "start": date(year_number, month, 1),
                      "end": date(year_number, month, monthrange(year_number, month)[1])})
    return items


def month_index(year, month: int, year_number: int) -> int:
    return (year_number - year.start_date.year) * 12 + (month - year.start_date.month)


# ------------------------------------------------------------------ agrégats

def month_locked(year, month: int, year_number: int) -> MonthLock | None:
    return MonthLock.objects.filter(year=year, month=month, year_number=year_number).first()


def balance_for_account(year, account: Account, up_to: date | None = None) -> dict[str, Decimal]:
    """Solde d'un compte = ouverture + écritures signées (jusqu'à une date optionnelle)."""
    opening = AccountOpening.objects.filter(year=year, account=account).first()
    opening_value = opening.amount if opening else ZERO
    entries = Entry.objects.filter(year=year, account=account)
    if up_to:
        entries = entries.filter(day__lte=up_to)
    movements = ZERO
    for item in entries:
        if item.kind in ("D", "R"):
            movements += item.signed
        elif item.kind == "T":
            movements -= item.amount
    incoming = Entry.objects.filter(year=year, to_account=account, kind="T")
    if up_to:
        incoming = incoming.filter(day__lte=up_to)
    for item in incoming:
        movements += item.amount
    return {"opening": opening_value, "movements": movements, "total": opening_value + movements}


def safe_account() -> Account | None:
    return Account.objects.filter(is_safe=True).first()


def safe_balance(year, up_to: date | None = None) -> Decimal:
    """Solde du coffre = solde du compte « coffre » (les dépôts en banque le diminuent)."""
    account = safe_account()
    if not account:
        return ZERO
    return balance_for_account(year, account, up_to)["total"]


def flows(queryset) -> dict[str, Decimal]:
    """Totaux dépenses / recettes / solde d'un jeu d'écritures."""
    data = queryset.values("kind").annotate(total=models.Sum("amount"))
    expenses = ZERO
    incomes = ZERO
    for row in data:
        if row["kind"] == "D":
            expenses += row["total"] or ZERO
        elif row["kind"] == "R":
            incomes += row["total"] or ZERO
    return {"expenses": expenses, "incomes": incomes, "balance": incomes - expenses}


def month_flows(year, month: int, year_number: int) -> dict[str, Any]:
    start, end = month_bounds(year, month, year_number)
    entries = Entry.objects.filter(year=year, day__gte=start, day__lte=end)
    result = flows(entries)
    result.update({"month": month, "year": year_number, "start": start, "end": end,
                   "locked": bool(month_locked(year, month, year_number)),
                   "count": entries.count()})
    return result


def year_flows(year) -> dict[str, Any]:
    entries = Entry.objects.filter(year=year)
    return flows(entries)


def year_histogram(year, months: Iterable[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Histogramme mensuel (recettes en positif, dépenses en négatif)."""
    result = []
    for item in months or months_for(year):
        start, end = item["start"], item["end"]
        entries = Entry.objects.filter(year=year, day__gte=start, day__lte=end, kind__in=("D", "R"))
        data = flows(entries)
        result.append({"label": item["label"], "month": item["month"], "year": item["year"],
                       "expenses": data["expenses"], "incomes": data["incomes"],
                       "value": float(data["balance"]), "expense_value": -float(data["expenses"]),
                       "income_value": float(data["incomes"])})
    return result


def category_breakdown(year, kind: str, up_to: date | None = None) -> list[dict[str, Any]]:
    entries = Entry.objects.filter(year=year, kind=kind, category__isnull=False)
    if up_to:
        entries = entries.filter(day__lte=up_to)
    rows = (entries.values("category__label", "category__color", "category__order")
            .annotate(total=models.Sum("amount"), count=models.Count("id"))
            .order_by("-total"))
    return [{"label": row["category__label"], "color": row["category__color"] or "#33556e",
             "order": row["category__order"], "total": row["total"] or ZERO, "count": row["count"]}
            for row in rows]


def mode_breakdown(year, up_to: date | None = None) -> list[dict[str, Any]]:
    entries = Entry.objects.filter(year=year, kind__in=("D", "R")).exclude(mode="")
    if up_to:
        entries = entries.filter(day__lte=up_to)
    rows = entries.values("mode").annotate(total=models.Sum("amount")).order_by("-total")
    return [{"label": MODE_LABELS.get(row["mode"], row["mode"]), "total": row["total"] or ZERO}
            for row in rows]


def account_balances(year, up_to: date | None = None) -> list[dict[str, Any]]:
    """Soldes de tous les comptes actifs + coffre."""
    result = []
    for account in Account.objects.filter(active=True):
        data = balance_for_account(year, account, up_to)
        result.append({"account": account, **data})
    return result


def overview(year, up_to: date | None = None) -> dict[str, Any]:
    year_data = year_flows(year)
    today = timezone.localdate()
    current_month = today.month if year.contains(today) else year.start_date.month
    current_year = today.year if year.contains(today) else year.start_date.year
    current = month_flows(year, current_month, current_year)
    months = months_for(year)
    index = next((i for i, item in enumerate(months)
                  if item["month"] == current_month and item["year"] == current_year), -1)
    previous = (month_flows(year, months[index - 1]["month"], months[index - 1]["year"])
                if index > 0 else None)
    return {
        "year": year, "year_flows": year_data, "current_month": current, "previous_month": previous,
        "accounts": account_balances(year, up_to), "safe": safe_balance(year),
        "histogram": year_histogram(year),
        "expenses_by_category": category_breakdown(year, "D", up_to),
        "incomes_by_category": category_breakdown(year, "R", up_to),
        "modes": mode_breakdown(year, up_to),
        "locked_months": list(MonthLock.objects.filter(year=year).values_list("month", "year_number")),
    }


# ------------------------------------------------------------------ verrou dur

def assert_not_locked(entry_date: date, year, actor=None) -> None:
    """Lève FinanceError si la date appartient à un mois clôturé."""
    lock = month_locked(year, entry_date.month, entry_date.year)
    if lock:
        raise FinanceError("Le mois %02d/%d est clôturé. Réouvrez-le depuis Réglages → Bilan mensuel."
                           % (entry_date.month, entry_date.year))


def lock_month(year, month: int, year_number: int, actor, note: str = "", document=None) -> MonthLock:
    """Clôture un mois : le bilan doit exister, sinon refus."""
    if MonthLock.objects.filter(year=year, month=month, year_number=year_number).exists():
        raise FinanceError("Ce mois est déjà clôturé.")
    if document is None and not BalanceRun.objects.filter(year=year, up_to_month__gte=_month_rank(year, month,
                                                                                                 year_number)).exists():
        raise FinanceError("Générez d'abord le bilan de cette période.")
    with transaction.atomic():
        lock = MonthLock.objects.create(year=year, month=month, year_number=year_number, locked_by=actor,
                                        note=note, balance_document=document)
        start, end = month_bounds(year, month, year_number)
        Entry.objects.filter(year=year, day__gte=start, day__lte=end).update(month_lock=lock)
    audit.log(actor, "finance.month_locked", "finance", lock, "Clôture mensuelle %02d/%d" % (month, year_number),
              level="warn")
    return lock


def unlock_month(year, month: int, year_number: int, actor, reason: str) -> None:
    """Réouverture : ré-authentification demandée par la vue, traçage obligatoire."""
    if not reason.strip():
        raise FinanceError("Un motif est obligatoire pour rouvrir un mois.")
    lock = month_locked(year, month, year_number)
    if not lock:
        raise FinanceError("Ce mois n'est pas clôturé.")
    with transaction.atomic():
        Entry.objects.filter(month_lock=lock).update(month_lock=None)
        lock.delete()
    audit.log(actor, "finance.month_unlocked", "finance", None,
              "Réouverture de %02d/%d — %s" % (month, year_number, reason), level="danger")


def _month_rank(year, month: int, year_number: int) -> int:
    return month_index(year, month, year_number) + 1


# ------------------------------------------------------------------ écritures

def create_entry(actor, year, *, day: date, title: str, amount: Decimal, kind: str = "D",
                 account: Account, to_account: Account | None = None, category=None,
                 subcategory=None, mode: str = "", third_party: str = "", reference: str = "",
                 note: str = "", source: str = "manuel", safe_movement: str = "",
                 support_file=None, batch: ImportBatch | None = None) -> list[Entry]:
    """Crée une écriture (et la paire débit/crédit pour un transfert)."""
    assert_not_locked(day, year, actor)
    if not title.strip():
        raise FinanceError("Le libellé est obligatoire.")
    if amount is None or amount <= 0:
        raise FinanceError("Le montant doit être strictement positif.")
    if kind == "T":
        if not to_account:
            raise FinanceError("Choisissez le compte destinataire du transfert.")
        if to_account.pk == account.pk:
            raise FinanceError("Le compte émetteur et le compte destinataire doivent être différents.")
    with transaction.atomic():
        entry = Entry.objects.create(
            year=year, day=day, title=title.strip(), amount=amount, kind=kind, account=account,
            to_account=to_account if kind == "T" else None, category=category, subcategory=subcategory,
            mode=mode, third_party=third_party, reference=reference, note=note, source=source,
            safe_movement=safe_movement, created_by=actor, support_file=support_file, import_batch=batch)
    audit.log(actor, "finance.entry_created", "finance", entry, "Création de l'écriture %s" % entry,
              previous=None, current=_entry_snapshot(entry))
    return [entry]


def _entry_snapshot(entry: Entry) -> dict[str, Any]:
    return {"date": entry.day.isoformat(), "libellé": entry.title, "montant": str(entry.amount),
            "sens": entry.kind, "compte": entry.account_id, "catégorie": entry.category_id,
            "mode": entry.mode, "tiers": entry.third_party}


def update_entry(actor, entry: Entry, payload: dict[str, Any]) -> Entry:
    assert_not_locked(entry.day, entry.year, actor)
    if entry.month_lock_id:
        raise FinanceError("Cette écriture appartient à un mois clôturé.")
    before = _entry_snapshot(entry)
    for field in ("title", "mode", "third_party", "reference", "note"):
        if field in payload:
            setattr(entry, field, payload[field])
    if "amount" in payload and payload["amount"] and payload["amount"] > 0:
        entry.amount = payload["amount"]
    if "category" in payload:
        entry.category = payload["category"] or None
    if "subcategory" in payload:
        entry.subcategory = payload["subcategory"] or None
    entry.updated_by = actor
    entry.save()
    audit.log(actor, "finance.entry_updated", "finance", entry, "Modification de l'écriture %s" % entry,
              previous=before, current=_entry_snapshot(entry))
    return entry


def delete_entry(actor, entry: Entry, reason: str) -> None:
    """Suppression motivée uniquement : jamais de modification silencieuse."""
    if not reason.strip():
        raise FinanceError("Un motif est obligatoire pour supprimer une écriture.")
    assert_not_locked(entry.day, entry.year, actor)
    if entry.month_lock_id:
        raise FinanceError("Cette écriture appartient à un mois clôturé.")
    snapshot = _entry_snapshot(entry)
    with transaction.atomic():
        entry.delete_reason = reason
        entry.save(update_fields=["delete_reason"])
        entry.delete()
    audit.log(actor, "finance.entry_deleted", "finance", None,
              "Suppression de l'écriture %s — motif : %s" % (snapshot["libellé"], reason),
              previous=snapshot, level="danger")


# ------------------------------------------------------------------ coffre

def cash_count(actor, year, *, day: date, account: Account, counted: Decimal,
               reason: str = "") -> CashCount:
    """Comptage : théorique calculé, écart justifié, ajustement automatique si écart."""
    assert_not_locked(day, year, actor)
    expected = balance_for_account(year, account, day)["total"]
    counted = (counted or ZERO).quantize(Decimal("0.01"))
    delta = counted - expected
    if abs(delta) < Decimal("0.01") and not reason.strip():
        pass
    elif abs(delta) >= Decimal("0.01") and not reason.strip():
        raise FinanceError("Un écart existe : indiquez un motif (erreur de caisse, pièce perdue…).")
    with transaction.atomic():
        count = CashCount.objects.create(year=year, day=day, account=account, expected=expected,
                                         counted=counted, reason=reason, created_by=actor)
        if abs(delta) >= Decimal("0.01"):
            # Un écart est une charge (manquant) ou un produit (excédent), jamais une écriture muette.
            gap_kind = "R" if delta > 0 else "D"
            gap_category = Category.objects.filter(label=GAP_LABEL, kind=gap_kind).first()
            adjustment = Entry.objects.create(
                year=year, day=day, title="Écart de caisse du %s" % day.strftime("%d/%m/%Y"),
                amount=abs(delta), kind=gap_kind, account=account, category=gap_category, mode="especes",
                source="reglage", safe_movement="misc", created_by=actor,
                note="Compté %s pour %s théorique. %s" % (counted, expected, reason))
            count.adjustment = adjustment
            count.save(update_fields=["adjustment"])
    audit.log(actor, "finance.cash_count", "finance", count, "Comptage de caisse du %s" % day.strftime("%d/%m/%Y"),
              previous={"théorique": str(expected)}, current={"compté": str(counted), "écart": str(delta)},
              level="warn" if abs(delta) >= Decimal("0.01") else "info")
    return count


# ------------------------------------------------------------------ import

def read_import(file_obj) -> tuple[list[dict[str, Any]], str]:
    """Lit un OFX, un QIF ou un CSV en lignes normalisées (utf-8 avec repli latin-1)."""
    raw = file_obj.read()
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
    else:
        text = raw
    stripped = text.lstrip()
    if stripped.upper().startswith("<OFX>") or "<STMTTRN>" in text.upper():
        return _parse_ofx(text), "ofx"
    if stripped.upper().startswith("!TYPE"):
        return _parse_qif(text), "qif"
    return _parse_csv(text), "csv"


def _ofx_tag(block: str, tag: str) -> str:
    match = re.search(r"<%s>([^<\n]*)" % tag, block, flags=re.I)
    return match.group(1).strip() if match else ""


def _parse_ofx(text: str) -> list[dict[str, Any]]:
    rows = []
    for block in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, flags=re.S | re.I):
        rows.append({"date": _ofx_tag(block, "DTPOSTED") or _ofx_tag(block, "DTUSER"),
                     "amount": _ofx_tag(block, "TRNAMT"),
                     "label": _ofx_tag(block, "NAME") or _ofx_tag(block, "MEMO"),
                     "reference": _ofx_tag(block, "FITID"),
                     "mode": _ofx_tag(block, "SIC")})
    return rows


def _parse_qif(text: str) -> list[dict[str, Any]]:
    rows = []
    current: dict[str, Any] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        marker, value = line[0], line[1:].strip()
        if marker == "^":
            if current:
                rows.append(current)
            current = {}
        elif marker in "DTNMPFL":
            key = {"D": "date", "T": "amount", "P": "label", "M": "memo", "N": "reference",
                   "L": "category", "F": "cleared"}.get(marker, marker)
            current[key] = value
    if current:
        rows.append(current)
    return rows


def _parse_csv(text: str) -> list[dict[str, Any]]:
    dialect = None
    sample = text[:4096]
    for candidate in (";", ",", "\t"):
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=candidate)
            break
        except csv.Error:
            continue
    reader = csv.DictReader(io.StringIO(text),
                            delimiter=dialect.delimiter if dialect else ";")
    rows = []
    for raw_row in reader:
        row = {(key or "").strip().lower(): (value or "").strip() for key, value in raw_row.items()}
        rows.append(row)
    return rows


def parse_date(value: str) -> date | None:
    value = (value or "").strip().replace("T000000", "").replace("T000000[", "")
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d", "%d/%m/%y"):
        try:
            return datetime.strptime(value[:len(value)], pattern).date()
        except (ValueError, TypeError):
            continue
    return None


def parse_amount(value: str | Decimal) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace("\xa0", " ").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def prepare_import(rows: list[dict[str, Any]], mapping: dict[str, str], account: Account,
                   year) -> list[dict[str, Any]]:
    """Normalise, devine le sens, détecte les doublons — sans rien écrire."""
    prepared = []
    for index, raw_row in enumerate(rows):
        row = {key.lower(): value for key, value in raw_row.items()}
        day = parse_date(row.get(mapping.get("date", "date"), ""))
        amount = parse_amount(row.get(mapping.get("amount", "montant"), ""))
        label = (row.get(mapping.get("label", "libellé"), "") or "")[:200]
        reference = (row.get(mapping.get("reference", "référence"), "") or "")[:80]
        if not day or amount is None:
            prepared.append({"row": index + 2, "error": "date ou montant illisible",
                             "day": day, "amount": amount, "label": label, "reference": reference})
            continue
        kind = "R" if amount >= 0 else "D"
        prepared.append({"row": index + 2, "error": "", "day": day, "amount": abs(amount),
                         "label": label or "(sans libellé)", "reference": reference, "kind": kind,
                         "duplicate": Entry.objects.filter(year=year, day=day, account=account,
                                                           amount=abs(amount), title=label[:200]).exists()})
    return prepared


def run_import(actor, batch: ImportBatch, prepared: list[dict[str, Any]], account: Account,
               year, skip_duplicates: bool = True) -> ImportBatch:
    """Écrit les lignes validées. Annulable : revert_import supprime le lot entier."""
    created = skipped = errored = 0
    report = []
    with transaction.atomic():
        for item in prepared:
            if item.get("error"):
                errored += 1
                report.append({"ligne": item["row"], "statut": "erreur", "détail": item["error"]})
                continue
            if item.get("duplicate") and skip_duplicates:
                skipped += 1
                report.append({"ligne": item["row"], "statut": "doublon ignoré",
                               "détail": "%s — %s" % (item["day"].strftime("%d/%m/%Y"), item["label"][:60])})
                continue
            try:
                create_entry(actor, year, day=item["day"], title=item["label"], amount=item["amount"],
                             kind=item["kind"], account=account, mode="autre", source="import",
                             reference=item["reference"], batch=batch)
                created += 1
                report.append({"ligne": item["row"], "statut": "importé",
                               "détail": "%s — %s" % (item["day"].strftime("%d/%m/%Y"), item["label"][:60])})
            except FinanceError as exc:
                errored += 1
                report.append({"ligne": item["row"], "statut": "erreur", "détail": str(exc)})
        batch.rows_created = created
        batch.rows_skipped = skipped
        batch.rows_error = errored
        batch.report = report
        batch.save()
    audit.log(actor, "finance.import", "finance", batch, "Import %s" % batch,
              current={"créées": created, "doublons": skipped, "erreurs": errored})
    return batch


def revert_import(actor, batch: ImportBatch) -> int:
    """Annule un import entier (un clic, avec confirmation)."""
    count = Entry.objects.filter(import_batch=batch).count()
    for entry in Entry.objects.filter(import_batch=batch):
        entry.delete()
    batch.reverted_at = timezone.now()
    batch.reverted_by = actor
    batch.save(update_fields=["reverted_at", "reverted_by"])
    audit.log(actor, "finance.import_reverted", "finance", batch, "Annulation de l'import %s" % batch,
              current={"écritures supprimées": count}, level="danger")
    return count


# ------------------------------------------------------------------ bilan

def bilan_setting(key: str, default: str) -> str:
    return Setting.value("bilan", key, default)


def should_generate_today(today: date | None = None, year=None) -> bool:
    """Le bilan est généré : le 1er, le dernier jour du mois, le dernier jour ouvré, ou au trimestre."""
    today = today or timezone.localdate()
    mode = bilan_setting("mode", "ouvrable")
    if not year or not year.contains(today):
        return False
    last_day = monthrange(today.year, today.month)[1]
    if mode == "jour":
        return today.day == int(bilan_setting("jour", "1"))
    if mode == "dernier":
        return today.day == last_day
    if mode == "trimestriel":
        return today.day == last_day and today.month % 3 == 0
    # dernier jour ouvré (du lundi au vendredi)
    candidate = date(today.year, today.month, last_day)
    while candidate.weekday() >= 5:
        candidate = candidate.replace(day=candidate.day - 1)
    return candidate == today


def generate_balance(year, up_to: date | None = None, actor=None, auto: bool = False) -> BalanceRun:
    """Génère le classeur Excel (4 types de feuilles) et l'enregistre dans Documents → Bilans."""
    from finance import excel

    up_to = up_to or timezone.localdate()
    included = [item for item in months_for(year) if item["start"] <= up_to]
    if not included:
        raise FinanceError("Aucun mois à inclure dans le bilan.")
    up_to_month = _month_rank(year, included[-1]["month"], included[-1]["year"])
    workbook_bytes = excel.build_workbook(year, included, up_to)
    months = ["%02d/%d" % (item["month"], item["year"]) for item in included]
    stats = {
        "recettes": str(year_flows(year)["incomes"]),
        "depenses": str(year_flows(year)["expenses"]),
        "solde": str(year_flows(year)["balance"]),
        "ecritures": Entry.objects.filter(year=year).count(),
        "coffre": str(safe_balance(year)),
    }
    from documents.models import Category as DocCategory
    from documents.services import UploadError, store_version, validate_upload

    category = DocCategory.objects.filter(slug="bilans").first()
    if category is None:
        from documents.services import ensure_default_categories
        ensure_default_categories()
        category = DocCategory.objects.filter(slug="bilans").first()
    if category is None:
        raise FinanceError("La catégorie de documents « Bilans » est introuvable.")
    name = "Bilan %s — %s.xlsx" % (year.label, timezone.localdate().strftime("%d-%m-%Y"))
    try:
        validate_upload(name, len(workbook_bytes))
    except UploadError as exc:
        raise FinanceError(str(exc)) from exc
    try:
        from io import BytesIO

        from django.core.files.base import File

        from documents.models import Document
        with transaction.atomic():
            document, created = Document.objects.get_or_create(
                category=category, folder=None, title="Bilan %s" % year.label,
                defaults={"description": "Bilan mensuel automatique de l'année %s. "
                                         "Une nouvelle version est ajoutée à chaque génération." % year.label,
                          "owner": actor, "tags": ["bilan", year.label]})
            version = store_version(document, File(BytesIO(workbook_bytes), name=name), actor,
                                    comment="Génération du %s (%s)" % (
                                        timezone.localdate().strftime("%d/%m/%Y"),
                                        "automatique" if auto else "manuelle"))
            run = BalanceRun.objects.create(year=year, up_to_month=up_to_month, auto=auto,
                                            generated_by=actor, workbook=document, months=months,
                                            stats=stats, status="ok",
                                            message="%s version v%s" % (name, version.version))
    except Exception as exc:  # noqa: BLE001 - le bilan doit échouer proprement
        logger.exception("Échec de la génération du bilan")
        run = BalanceRun.objects.create(year=year, up_to_month=up_to_month, auto=auto, generated_by=actor,
                                        months=months, stats=stats, status="failed", message=str(exc)[:240])
        audit.log(actor, "finance.balance_failed", "finance", run,
                  "Échec du bilan %s : %s" % (year.label, str(exc)[:200]), level="danger")
        return run
    audit.log(actor, "finance.balance_generated", "finance", run, "Bilan %s généré" % year.label,
              current=stats, level="warn" if auto else "info")
    return run


def cron_run(today: date | None = None) -> dict[str, Any]:
    """Point d'entrée du cron quotidien : bilan du jour + alerte de mois non clôturé."""
    from core.models import SchoolYear

    today = today or timezone.localdate()
    result = {"bilan": None, "alertes": []}
    year = SchoolYear.objects.filter(start_date__lte=today, end_date__gte=today).order_by("-start_date").first()
    if not year:
        return result
    if should_generate_today(today, year):
        run = generate_balance(year, up_to=today, auto=True)
        result["bilan"] = run.status
    previous = today.replace(day=1) - timezone.timedelta(days=1)
    if month_index(year, previous.month, previous.year) >= 0 and not month_locked(year, previous.month,
                                                                                 previous.year):
        result["alertes"].append("Le mois %02d/%d n'est pas clôturé." % (previous.month, previous.year))
    return result


def latest_balance(year) -> BalanceRun | None:
    return BalanceRun.objects.filter(year=year).order_by("-generated_at").first()
