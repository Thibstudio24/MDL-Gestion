"""Tuiles du tableau de bord : jamais vides, filtrées par droits, cliquables."""
from __future__ import annotations

import calendar
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from core import permissions
from core.models import SchoolYear, Setting

ZERO = Decimal("0.00")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # module absent, base vide, table non migrée…
        return default


def _year():
    return SchoolYear.current()


def _months_labels(year) -> tuple[list[str], list[tuple[int, int]]]:
    if year is None:
        today = timezone.localdate()
        pairs = [(today.year, m) for m in range(1, 13)]
    else:
        pairs = year.months()
    return ["%s %s" % (calendar.month_abbr[m], str(y)[2:]) for y, m in pairs], pairs


# --------------------------------------------------------------------------- #
# Tuiles
# --------------------------------------------------------------------------- #
def tile_balance(user) -> dict:
    from finance.models import Account, Entry
    from finance.services import balance_for_account

    year = _year()
    accounts = list(Account.objects.filter(active=True).order_by("order", "name"))
    items, total = [], ZERO
    for account in accounts:
        amount = balance_for_account(year, account) or ZERO
        total += amount
        items.append({"label": account.name, "value": amount, "url": "/tresorerie/comptes/"})
    previous = _previous_month_delta(year)
    return {
        "key": "solde",
        "module": "finance",
        "title": "Solde de trésorerie",
        "value": total,
        "money": True,
        "subtitle": " · ".join("%s %s" % (i["label"], "{:,.2f}".format(i["value"]).replace(",", " ").replace(".", ",")) for i in items)
        or "Aucun compte créé",
        "url": "/tresorerie/",
        "delta": previous,
        "items": items,
        "chart": {"type": "doughnut", "labels": [i["label"] for i in items],
                  "series": [{"label": "Solde", "data": [float(i["value"]) for i in items]}]},
    }


def _previous_month_delta(year):
    from finance.models import Entry

    today = timezone.localdate()
    first = today.replace(day=1)
    last_month_end = first - timedelta(days=1)
    month_start = last_month_end.replace(day=1)

    def net(start, end):
        rows = Entry.objects.filter(day__gte=start, day__lte=end)
        if year is not None:
            rows = rows.filter(year=year)
        total = ZERO
        for kind, amount in rows.values_list("kind", "amount"):
            total += amount if kind == "R" else (-amount if kind == "D" else ZERO)
        return total

    return {"mois": net(month_start, last_month_end), "encours": net(first, today)}


def tile_month_flows(user) -> dict:
    from finance.models import Entry
    from finance.services import month_flows

    year = _year()
    today = timezone.localdate()
    flows = month_flows(year, today.year, today.month)
    by_category = flows["categories"]
    return {
        "key": "mois",
        "module": "finance",
        "title": "Ce mois-ci",
        "value": flows["net"],
        "money": True,
        "subtitle": "Recettes %s · Dépenses %s" % (flows["recettes"], flows["depenses"]),
        "url": "/tresorerie/?mois=%d-%02d" % (today.year, today.month),
        "items": [
            {"label": "Recettes", "value": flows["recettes"], "css": "success"},
            {"label": "Dépenses", "value": flows["depenses"], "css": "danger"},
        ],
        "chart": {"type": "doughnut", "labels": list(by_category)[:8],
                  "series": [{"label": "Dépenses", "data": [float(v) for v in list(by_category.values())[:8]]}]},
    }


def tile_year_histogram(user) -> dict:
    from finance.services import year_histogram

    year = _year()
    labels, pairs = _months_labels(year)
    series = year_histogram(year, pairs)
    return {
        "key": "histogramme",
        "module": "finance",
        "title": "Recettes et dépenses de l'année",
        "value": sum(series["recettes"]) - sum(series["depenses"]),
        "money": True,
        "subtitle": "%s" % (year.label if year else "année en cours"),
        "url": "/tresorerie/",
        "chart": {"type": "bar", "labels": labels,
                  "series": [{"label": "Recettes", "data": series["recettes"], "css": "success"},
                             {"label": "Dépenses", "data": series["depenses"], "css": "danger"}]},
    }


def tile_safe(user) -> dict:
    from finance.models import Account, CashCount
    from finance.services import balance_for_account

    year = _year()
    safe = Account.objects.filter(is_safe=True, active=True).first()
    amount = balance_for_account(year, safe) if safe else ZERO
    count = CashCount.objects.order_by("-day").first()
    delta = (count.counted - count.expected) if count else ZERO
    return {
        "key": "coffre",
        "module": "finance",
        "title": "Coffre-fort",
        "value": amount or ZERO,
        "money": True,
        "subtitle": ("Dernier comptage du %s : écart %s" % (count.day.strftime("%d/%m/%Y"), delta))
        if count else "Aucun comptage enregistré",
        "url": "/tresorerie/coffre/",
        "alert": bool(count and delta != 0),
        "level": "warning" if count and delta != 0 else "info",
    }


def tile_unclosed(user) -> dict:
    from finance.models import Entry, MonthLock
    from finance.services import month_locked

    year = _year()
    today = timezone.localdate()
    locked = {m.month for m in MonthLock.objects.filter(year=year)} if year else set()
    labels, pairs = _months_labels(year)
    pending = [(y, m) for (y, m) in pairs if (y, m) < (today.year, today.month) and m not in locked]
    count = _safe(lambda: Entry.objects.filter(month_lock__isnull=True).count(), 0)
    return {
        "key": "clotures",
        "module": "finance",
        "title": "Mois à clôturer",
        "value": len(pending),
        "subtitle": ", ".join("%s/%s" % (m, str(y)[2:]) for y, m in pending) or "Tous les mois passés sont clôturés",
        "url": "/tresorerie/clotures/",
        "alert": bool(pending),
        "level": "warning" if pending else "success",
        "extra": "%s écritures hors période clôturée" % count,
    }


def tile_members(user) -> dict:
    from accounts.models import Invitation, User

    total = _safe(lambda: User.objects.filter(status="active").count(), 0)
    pending = _safe(lambda: Invitation.objects.filter(accepted_at__isnull=True, expires_at__gte=timezone.now()).count(), 0)
    no_2fa = _safe(lambda: User.objects.filter(status="active", totp_enabled=False).count(), 0)
    limit = timezone.now() - timedelta(days=365)
    stale = _safe(lambda: User.objects.filter(status="active", last_seen__lt=limit).count(), 0)
    from django.db.models import Count

    roles = _safe(lambda: list(
        User.objects.filter(status="active").values_list("role__name")
        .annotate(n=Count("id")).order_by("-n")
    ), [])
    return {
        "key": "membres",
        "module": "members",
        "title": "Membres",
        "value": total,
        "subtitle": "%s invitations en cours · %s sans A2F · %s inactifs depuis 12 mois" % (pending, no_2fa, stale),
        "url": "/membres/",
        "items": [{"label": name or "sans rôle", "value": n} for name, n in roles][:6],
        "chart": {"type": "bar", "labels": [name or "sans rôle" for name, _n in roles][:6],
                  "series": [{"label": "Membres", "data": [n for _name, n in roles][:6]}]},
    }


def tile_room(user) -> dict:
    from plannings.models import Campaign
    from plannings.services import campaign_stats

    campaign = _safe(lambda: Campaign.objects.order_by("-start_date").first())
    if campaign is None:
        return {
            "key": "salle", "module": "planning_salle", "title": "Planning de la salle",
            "value": 0, "subtitle": "Aucune campagne : lancez-en une pour la rentrée",
            "url": "/planning/", "level": "muted",
        }
    stats = campaign_stats(campaign)
    return {
        "key": "salle",
        "module": "planning_salle",
        "title": "Planning de la salle",
        "value": stats["reponse_pct"],
        "percent": True,
        "subtitle": "%s — %s créneaux sans gérant" % (campaign.label, stats["gaps"]),
        "url": "/planning/%d/couverture/" % campaign.pk,
        "alert": stats["gaps"] > 0,
        "level": "danger" if stats["gaps"] else "success",
        "chart": {"type": "bar", "labels": ["Répondu", "En attente"],
                  "series": [{"label": "Membres", "data": [stats["answered"], stats["missing"]]}]},
    }


def tile_chores(user) -> dict:
    from chores.models import Assignment, Campaign, Response
    from chores.services import campaign_progress

    campaign = _safe(lambda: Campaign.objects.order_by("-start_date").first())
    late = _safe(lambda: Assignment.objects.filter(status="todo", done_at__isnull=True).count(), 0)
    proofs = _safe(lambda: Assignment.objects.filter(status="done").count(), 0)
    missing = campaign_progress(campaign)["missing"] if campaign else 0
    return {
        "key": "menage",
        "module": "planning_menage",
        "title": "Planning de ménage",
        "value": late,
        "subtitle": "%s tâches en retard · %s preuves à valider · %s membres sans réponse" % (late, proofs, missing),
        "url": "/menage/admin/suivi/",
        "alert": late > 0,
        "level": "warning" if late else "success",
    }


def tile_documents(user) -> dict:
    from documents.models import Category, Document
    from documents.services import quota_usage

    usage = _safe(lambda: quota_usage(), {"used": 0, "total": 1, "pct": 0})
    latest = _safe(lambda: list(Document.objects.live().order_by("-created_at")[:5]), [])
    locked = _safe(lambda: Category.objects.filter(locked_read=True).count(), 0)
    return {
        "key": "documents",
        "module": "documents",
        "title": "Documents",
        "value": usage["pct"],
        "percent": True,
        "subtitle": "Quota %s · %s catégories verrouillées" % (usage["label"], locked),
        "url": "/documents/",
        "items": [{"label": d.title, "value": d.created_at.strftime("%d/%m"), "url": "/documents/%d/" % d.pk}
                  for d in latest],
        "alert": usage["pct"] >= 80,
        "level": "danger" if usage["pct"] >= 95 else ("warning" if usage["pct"] >= 80 else "info"),
    }


def tile_messages(user) -> dict:
    from finance.models import BalanceRun
    from mail.models import Recipient

    unread = _safe(lambda: Recipient.objects.filter(user=user, read_at__isnull=True).count(), 0)
    last = _safe(lambda: BalanceRun.objects.order_by("-generated_at").first())
    return {
        "key": "messages",
        "module": "mail",
        "title": "Messages",
        "value": unread,
        "subtitle": ("Dernier bilan : %s" % last.generated_at.strftime("%d/%m/%Y")) if last
        else "Le bilan n'a pas encore été généré",
        "url": "/messages/",
        "alert": unread > 0,
        "level": "info" if unread else "muted",
    }


def tile_mine(user) -> dict:
    from chores.models import Assignment
    from plannings.models import Availability

    q1 = _safe(lambda: Availability.objects.filter(member=user, week="Q1").count(), 0)
    q2 = _safe(lambda: Availability.objects.filter(member=user, week="Q2").count(), 0)
    next_task = _safe(lambda: Assignment.objects.filter(member=user, status__in=["todo", "redo"]).order_by("week").first())
    return {
        "key": "moi",
        "module": "dashboard",
        "title": "Mes disponibilités",
        "value": q1 + q2,
        "subtitle": "Semaine 1 : %s · Semaine 2 : %s · %s" % (
            q1, q2,
            ("prochain ménage : %s" % next_task.task.label) if next_task and next_task.task else "aucun ménage à venir",
        ),
        "url": "/planning/mes-disponibilites/",
        "items": [
            {"label": "Semaine 1 (Q1)", "value": q1},
            {"label": "Semaine 2 (Q2)", "value": q2},
            {"label": "Statut", "value": "Interne" if getattr(user, "is_boarder", False) else "Externe"},
        ],
    }


def tile_alerts(user) -> dict:
    from core.services import health_alerts

    alerts = _safe(lambda: health_alerts(user), [])
    return {
        "key": "alertes",
        "module": "dashboard",
        "title": "Alertes administratives",
        "value": len(alerts),
        "subtitle": alerts[0]["message"] if alerts else "Rien à signaler",
        "url": "/reglages/",
        "items": [{"label": a["message"], "value": a["kind"], "url": a.get("url")} for a in alerts][:6],
        "alert": bool(alerts),
        "level": "warning" if alerts else "success",
    }


TILES = [
    tile_balance, tile_month_flows, tile_year_histogram, tile_safe, tile_unclosed, tile_members,
    tile_room, tile_chores, tile_documents, tile_messages, tile_mine, tile_alerts,
]

SECTIONS = [
    ("mois", "Ce mois-ci", ["solde", "mois", "histogramme", "coffre"]),
    ("afaire", "À faire", ["clotures", "salle", "menage"]),
    ("vie", "Vie de l'asso", ["membres", "documents", "messages", "moi"]),
    ("technique", "Technique", ["alertes"]),
]


def build_tiles(user) -> list[dict]:
    """Une tuile non autorisée n'est pas affichée (pas grisée)."""
    tiles = []
    for builder in TILES:
        try:
            tile = builder(user)
        except Exception:
            continue
        module = tile.get("module", "dashboard")
        if not permissions.can_view(user, module):
            continue
        tiles.append(tile)
    return tiles


def build_sections(user) -> list[dict]:
    tiles = {tile["key"]: tile for tile in build_tiles(user)}
    sections = []
    for key, label, keys in SECTIONS:
        items = [tiles[k] for k in keys if k in tiles]
        if items:
            sections.append({"key": key, "label": label, "tiles": items})
    return sections
