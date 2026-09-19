"""Vues de la trésorerie : grand livre, coffre, imports, clôtures, bilans."""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from audit import services as audit
from core import permissions
from core.decorators import fine_required, module_required, reauth_required
from core.models import SchoolYear
from core.services import aucune_annee
from finance import services
from finance.forms import (
    AccountForm,
    BalanceForm,
    CashCountForm,
    CategoryForm,
    DeleteReasonForm,
    EntryForm,
    ImportForm,
    LedgerFilterForm,
    LockForm,
    OpeningForm,
)
from finance.models import (
    Account,
    AccountOpening,
    BalanceRun,
    CashCount,
    Category,
    Entry,
    ImportBatch,
    MonthLock,
)
from finance.services import FinanceError

MODULE = "finance"


def _year(request) -> SchoolYear:
    requested = request.GET.get("annee") or request.POST.get("annee")
    if requested:
        found = SchoolYear.objects.filter(pk=requested).first()
        if found:
            return found
    return SchoolYear.current()


def _filter_summary(form) -> str:
    """Résumé lisible des filtres actifs, imprimé en sous-titre du PDF."""
    if not form.is_valid():
        return ""
    data = form.cleaned_data
    parts = []
    if data.get("q"):
        parts.append("recherche « %s »" % data["q"])
    for field in ("account", "category"):
        if data.get(field):
            parts.append("%s : %s" % (form.fields[field].label, data[field]))
    for field in ("mode", "kind"):
        if data.get(field):
            labels = dict(form.fields[field].choices)
            parts.append("%s : %s" % (form.fields[field].label, labels.get(data[field], data[field])))
    if data.get("start") or data.get("end"):
        parts.append("du %s au %s" % (data["start"].strftime("%d/%m/%Y") if data.get("start") else "…",
                                      data["end"].strftime("%d/%m/%Y") if data.get("end") else "…"))
    return ", ".join(parts)


def _fail(request, exc: Exception, back: str, **kwargs) -> HttpResponse:
    """Signale une erreur métier et revient à la page d'origine."""
    messages.error(request, str(exc))
    return redirect(back, **kwargs)


# ------------------------------------------------------------------ tableau de bord

@module_required(MODULE)
def finance_list(request):
    """Tableau de bord : soldes, mois en cours, histogramme, dernières écritures."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    services.ensure_accounts()
    data = services.overview(year)
    entries = (Entry.objects.filter(year=year).select_related("account", "category", "created_by")
               .order_by("-day", "-id")[:15])
    return render(request, "finance/list.html", {
        "page_title": _("Trésorerie"), "year": year, "years": SchoolYear.objects.all(),
        "overview": data, "entries": entries,
        "accounts": data["accounts"], "safe": data["safe"],
        "histogram": data["histogram"], "modes": data["modes"],
        "expenses_by_category": data["expenses_by_category"],
        "incomes_by_category": data["incomes_by_category"],
        "current_month": data["current_month"], "previous_month": data["previous_month"],
        "year_flows": data["year_flows"], "locked_months": data["locked_months"],
        "total_balance": sum((row["total"] for row in data["accounts"]), Decimal("0.00")),
        "latest_balance": services.latest_balance(year),
        "can_edit": permissions.can_edit(request.user, MODULE),
    })


# ------------------------------------------------------------------ grand livre

@module_required(MODULE)
def finance_ledger(request):
    """Grand livre filtrable et paginé."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    form = LedgerFilterForm(request.GET or None)
    entries = Entry.objects.filter(year=year).select_related("account", "category", "subcategory", "created_by")
    if form.is_valid():
        entries = form.filter_queryset(entries)
    entries = entries.order_by("-day", "-id")
    totals = services.flows(entries)
    paginator = Paginator(entries, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "finance/ledger.html", {
        "page_title": _("Grand livre"), "year": year, "years": SchoolYear.objects.all(),
        "form": form, "page_obj": page_obj, "totals": totals,
        "count": paginator.count,
    })


@module_required(MODULE, edit=True)
def entry_create(request):
    """Saisie d'une écriture (dépense, recette, transfert)."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    form = EntryForm(request.POST or None, request.FILES or None,
                     initial={"day": timezone.localdate(),
                              "account": Account.objects.filter(active=True).order_by("order").first()})
    if request.method == "POST" and form.is_valid():
        payload = form.cleaned_data
        try:
            services.create_entry(
                request.user, year, day=payload["day"], title=payload["title"], amount=payload["amount"],
                kind=payload["kind"], account=payload["account"], to_account=payload.get("to_account"),
                category=payload.get("category"), subcategory=payload.get("subcategory"),
                mode=payload.get("mode") or "", third_party=payload.get("third_party") or "",
                reference=payload.get("reference") or "", note=payload.get("note") or "",
                support_file=payload.get("support_file"))
        except FinanceError as exc:
            return _fail(request, exc, "finance:entry_create")
        messages.success(request, _("Écriture enregistrée."))
        return redirect("finance:ledger")
    return render(request, "finance/entry_form.html", {
        "page_title": _("Nouvelle écriture"), "form": form, "year": year, "creating": True,
    })


@module_required(MODULE)
def entry_detail(request, pk):
    entry = get_object_or_404(Entry.objects.select_related("account", "to_account", "category", "subcategory",
                                                           "created_by", "year"), pk=pk)
    siblings = (Entry.objects.filter(year=entry.year, title__icontains=entry.title[:40])
                .exclude(pk=entry.pk).order_by("-day")[:5])
    return render(request, "finance/entry_detail.html", {
        "page_title": entry.title, "entry": entry, "siblings": siblings,
        "balance": services.balance_for_account(entry.year, entry.account, entry.day)["total"],
        "delete_form": DeleteReasonForm(),
        "can_edit": permissions.can_edit(request.user, MODULE),
    })


@module_required(MODULE, edit=True)
def entry_edit(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    form = EntryForm(request.POST or None, request.FILES or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        payload = form.cleaned_data
        try:
            services.update_entry(request.user, entry, {
                "title": payload["title"], "amount": payload["amount"], "category": payload.get("category"),
                "subcategory": payload.get("subcategory"), "mode": payload.get("mode") or "",
                "third_party": payload.get("third_party") or "", "reference": payload.get("reference") or "",
                "note": payload.get("note") or ""})
            if payload.get("support_file"):
                entry.support_file = payload["support_file"]
                entry.save(update_fields=["support_file"])
        except FinanceError as exc:
            return _fail(request, exc, "finance:entry_detail", pk=pk)
        messages.success(request, _("Écriture mise à jour."))
        return redirect("finance:entry_detail", pk=entry.pk)
    return render(request, "finance/entry_form.html", {
        "page_title": _("Modifier l'écriture"), "form": form, "entry": entry, "year": entry.year,
        "creating": False,
    })


@fine_required("finance.export", MODULE)
@require_POST
def entry_duplicate(request, pk):
    """Dupliquer une écriture : pratique pour les charges récurrentes."""
    entry = get_object_or_404(Entry, pk=pk)
    try:
        services.create_entry(request.user, entry.year, day=timezone.localdate(),
                              title=entry.title, amount=entry.amount, kind=entry.kind,
                              account=entry.account, to_account=entry.to_account, category=entry.category,
                              subcategory=entry.subcategory, mode=entry.mode, third_party=entry.third_party,
                              reference=entry.reference, note=entry.note)
    except FinanceError as exc:
        return _fail(request, exc, "finance:entry_detail", pk=pk)
    audit.log(request.user, "finance.entry_duplicated", MODULE, entry, "Écriture dupliquée depuis %s" % entry)
    messages.success(request, _("Écriture dupliquée à la date du jour."))
    return redirect("finance:ledger")


@module_required(MODULE, edit=True)
@require_POST
def entry_delete(request, pk):
    """Suppression motivée : motif obligatoire, jamais de modification silencieuse."""
    entry = get_object_or_404(Entry, pk=pk)
    form = DeleteReasonForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Un motif est obligatoire pour supprimer une écriture."))
        return redirect("finance:entry_detail", pk=pk)
    try:
        services.delete_entry(request.user, entry, form.cleaned_data["reason"])
    except FinanceError as exc:
        return _fail(request, exc, "finance:entry_detail", pk=pk)
    messages.success(request, _("Écriture supprimée et tracée dans le journal d'audit."))
    return redirect("finance:ledger")


# ------------------------------------------------------------------ comptes

@module_required(MODULE)
def accounts(request):
    """Comptes bancaires, coffre, soldes d'ouverture."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    services.ensure_accounts()
    rows = []
    for account in Account.objects.all():
        data = services.balance_for_account(year, account, None)
        rows.append({"account": account, "opening": data["opening"], "movements": data["movements"],
                     "total": data["total"],
                     "entries": Entry.objects.filter(year=year, account=account).count()})
    opening_form = OpeningForm(request.POST or None)
    if request.method == "POST" and "opening" in request.POST:
        form = OpeningForm(request.POST)
        if form.is_valid():
            opening, _created = AccountOpening.objects.update_or_create(
                year=year, account=form.cleaned_data["account"],
                defaults={"amount": form.cleaned_data["amount"]})
            audit.log(request.user, "finance.account_updated", MODULE, opening.account,
                      "Solde d'ouverture %s = %s" % (year.label, opening.amount),
                      previous=None, current={"année": year.label, "montant": str(opening.amount)})
            messages.success(request, _("Solde d'ouverture enregistré."))
            return redirect("finance:accounts")
        opening_form = form
    return render(request, "finance/accounts.html", {
        "page_title": _("Comptes"), "year": year, "years": SchoolYear.objects.all(),
        "rows": rows, "opening_form": opening_form,
        "account_form": AccountForm(prefix="compte"), "safe": services.safe_balance(year),
    })


@module_required(MODULE, edit=True)
def account_create(request):
    form = AccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.save()
        audit.log(request.user, "finance.account_updated", MODULE, account, "Création du compte %s" % account)
        messages.success(request, _("Compte créé."))
        return redirect("finance:accounts")
    return render(request, "finance/account_form.html", {"page_title": _("Nouveau compte"), "form": form})


@module_required(MODULE, edit=True)
def account_edit(request, pk):
    account = get_object_or_404(Account, pk=pk)
    form = AccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.log(request.user, "finance.account_updated", MODULE, account, "Modification du compte %s" % account)
        messages.success(request, _("Compte mis à jour."))
        return redirect("finance:accounts")
    return render(request, "finance/account_form.html", {"page_title": account.name, "form": form,
                                                         "account": account})


# ------------------------------------------------------------------ coffre

@module_required(MODULE)
def cash(request):
    """Comptage de caisse : théorique calculé, écart justifié, ajustement automatique."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    services.ensure_accounts()
    safe = services.safe_account()
    form = CashCountForm(request.POST or None, initial={"day": timezone.localdate(), "account": safe})
    if request.method == "POST" and form.is_valid():
        try:
            count = services.cash_count(request.user, year, day=form.cleaned_data["day"],
                                        account=form.cleaned_data["account"],
                                        counted=form.cleaned_data["counted"],
                                        reason=form.cleaned_data["reason"])
        except FinanceError as exc:
            return _fail(request, exc, "finance:cash")
        if count.adjustment_id:
            messages.warning(request, _("Écart de %(ecart)s : une régularisation a été créée.")
                             % {"ecart": count.delta})
        else:
            messages.success(request, _("Comptage enregistré, aucun écart."))
        return redirect("finance:cash")
    counts = CashCount.objects.filter(year=year).select_related("account", "adjustment")[:30]
    return render(request, "finance/cash.html", {
        "page_title": _("Coffre-fort"), "year": year, "years": SchoolYear.objects.all(),
        "form": form, "counts": counts, "safe_balance": services.safe_balance(year),
        "accounts": services.active_accounts(),
    })


# ------------------------------------------------------------------ catégories

@module_required(MODULE)
def categories(request):
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    form = CategoryForm(request.POST or None, prefix="categorie")
    if request.method == "POST" and form.is_valid():
        category = form.save()
        audit.log(request.user, "finance.account_updated", MODULE, category, "Catégorie %s" % category.label)
        messages.success(request, _("Catégorie enregistrée."))
        return redirect("finance:categories")
    rows = []
    for category in Category.objects.all():
        rows.append({"category": category,
                     "expenses": sum((e.amount for e in category.entries.filter(year=year, kind="D")),
                                     Decimal("0.00")),
                     "incomes": sum((e.amount for e in category.entries.filter(year=year, kind="R")),
                                    Decimal("0.00")),
                     "count": category.entries.filter(year=year).count()})
    return render(request, "finance/categories.html", {
        "page_title": _("Catégories"), "year": year, "years": SchoolYear.objects.all(),
        "form": form, "rows": rows,
    })


# ------------------------------------------------------------------ import

@fine_required("finance.import", MODULE)
def import_view(request):
    """Import bancaire : aperçu avant écriture, détection des doublons, annulable."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    services.ensure_accounts()
    form = ImportForm(request.POST or None, request.FILES or None)
    prepared = []
    batch = None
    if request.method == "POST" and form.is_valid():
        mapping = form.cleaned_data.get("mapping") or {"date": "date", "amount": "montant", "label": "libellé"}
        account = form.cleaned_data["account"]
        try:
            rows, format_name = services.read_import(form.cleaned_data["file"])
        except Exception as exc:  # noqa: BLE001 - fichier illisible
            messages.error(request, _("Fichier illisible : %(erreur)s") % {"erreur": exc})
            return redirect("finance:import")
        prepared = services.prepare_import(rows, mapping, account, year)
        batch = ImportBatch.objects.create(file_name=form.cleaned_data["file"].name[:240], year=year,
                                           rows_total=len(rows), created_by=request.user)
        request.session["finance_import"] = {
            "batch": batch.pk, "account": account.pk, "format": format_name,
            "prepared": [{"row": item["row"], "day": item["day"].isoformat() if item.get("day") else "",
                          "amount": str(item["amount"]) if item.get("amount") is not None else "",
                          "label": item.get("label", ""), "reference": item.get("reference", ""),
                          "kind": item.get("kind", ""), "duplicate": bool(item.get("duplicate")),
                          "error": item.get("error", "")} for item in prepared]}
        valid = len([item for item in prepared if not item.get("error")])
        duplicates = len([item for item in prepared if item.get("duplicate")])
        messages.info(request, _("%(total)s lignes lues (%(format)s) : %(valid)s importables, "
                                 "%(doublons)s doublon(s) détecté(s).")
                      % {"total": len(rows), "format": format_name, "valid": valid, "doublons": duplicates})
    session_data = request.session.get("finance_import")
    if session_data:
        prepared = session_data["prepared"]
        batch = ImportBatch.objects.filter(pk=session_data["batch"]).first()
    history = ImportBatch.objects.order_by("-created_at")[:20]
    return render(request, "finance/import.html", {
        "page_title": _("Import bancaire"), "year": year, "years": SchoolYear.objects.all(),
        "form": form, "prepared": prepared, "batch": batch, "history": history,
        "accounts": services.active_accounts(),
    })


@fine_required("finance.import", MODULE)
@require_POST
def import_run(request):
    """Écrit les lignes validées après vérification visuelle."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    data = request.session.get("finance_import")
    if not data:
        messages.error(request, _("Aucun import en attente : rechargez votre fichier."))
        return redirect("finance:import")
    batch = get_object_or_404(ImportBatch, pk=data["batch"])
    account = get_object_or_404(Account, pk=data["account"])
    prepared = []
    for item in data["prepared"]:
        prepared.append({
            "row": item["row"], "error": item.get("error", ""),
            "day": datetime.strptime(item["day"], "%Y-%m-%d").date() if item.get("day") else None,
            "amount": Decimal(item["amount"]) if item.get("amount") else None,
            "label": item.get("label", ""), "reference": item.get("reference", ""),
            "kind": item.get("kind", "D"), "duplicate": item.get("duplicate", False)})
    services.run_import(request.user, batch, prepared, account, year,
                        skip_duplicates=request.POST.get("skip_duplicates") != "0")
    request.session.pop("finance_import", None)
    messages.success(request, _("%(crees)s écriture(s) importée(s), %(doublons)s doublon(s) ignoré(s), "
                                "%(erreurs)s erreur(s).")
                     % {"crees": batch.rows_created, "doublons": batch.rows_skipped,
                        "erreurs": batch.rows_error})
    return redirect("finance:ledger")


@fine_required("finance.import", MODULE)
@require_POST
def import_revert(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    count = services.revert_import(request.user, batch)
    messages.success(request, _("Import annulé : %(nombre)s écriture(s) supprimée(s).") % {"nombre": count})
    return redirect("finance:import")


# ------------------------------------------------------------------ export

@fine_required("finance.export", MODULE)
def export(request):
    """Export du grand livre en Excel, en CSV ou en PDF."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    form = LedgerFilterForm(request.GET or None)
    entries = Entry.objects.filter(year=year).select_related("account", "category")
    if form.is_valid():
        entries = form.filter_queryset(entries)
    entries = entries.order_by("day", "id")
    fmt = request.GET.get("format", "xlsx")
    audit.log(request.user, "finance.exported", MODULE, None, "Export du grand livre (%s lignes, %s)"
              % (entries.count(), fmt))
    if fmt == "pdf":
        from finance import pdf

        return pdf.ledger_pdf(year, list(entries), services.flows(entries), filters=_filter_summary(form))
    if fmt == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="grand-livre-%s.csv"' % year.label
        response.write("\ufeff")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["N°", "Date", "Libellé", "Compte", "Catégorie", "Mode", "Tiers", "Pièce",
                         "Dépense", "Recette"])
        for index, entry in enumerate(entries, start=1):
            writer.writerow([index, entry.day.strftime("%d/%m/%Y"), entry.title, entry.account.name,
                             entry.category.label if entry.category_id else "", entry.get_mode_display(),
                             entry.third_party, entry.reference,
                             str(entry.amount) if entry.kind == "D" else "",
                             str(entry.amount) if entry.kind == "R" else ""])
        return response
    from finance import excel

    months = services.months_for(year)
    content = excel.build_workbook(year, months, timezone.localdate())
    response = HttpResponse(content,
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="grand-livre-%s.xlsx"' % year.label
    return response


# ------------------------------------------------------------------ bilans & clôtures

@module_required(MODULE)
def balance(request):
    """Génération du bilan et historique des classeurs."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    form = BalanceForm(request.POST or None, initial={"up_to": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            run = services.generate_balance(year, up_to=form.cleaned_data["up_to"], actor=request.user)
        except FinanceError as exc:
            return _fail(request, exc, "finance:balance")
        if run.status == "ok":
            messages.success(request, _("Bilan généré : %(message)s") % {"message": run.message})
        else:
            messages.error(request, _("Génération échouée : %(message)s") % {"message": run.message})
        return redirect("finance:balance")
    runs = BalanceRun.objects.filter(year=year).select_related("workbook")[:20]
    schedule = {"mode": services.bilan_setting("mode", "ouvrable"), "jour": services.bilan_setting("jour", "1"),
                "heure": services.bilan_setting("heure", "06:00")}
    return render(request, "finance/balance.html", {
        "page_title": _("Bilan mensuel"), "year": year, "years": SchoolYear.objects.all(),
        "form": form, "runs": runs, "schedule": schedule,
        "months": services.months_for(year),
        "locks": MonthLock.objects.filter(year=year).select_related("locked_by"),
    })


@fine_required("finance.lock", MODULE)
def locks(request):
    """Clôtures mensuelles : verrou dur, réouverture motivée et ré-authentifiée."""
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    form = LockForm(year, request.POST or None)
    if request.method == "POST" and form.is_valid():
        month, year_number = (int(value) for value in form.cleaned_data["month"].split("-"))
        try:
            services.lock_month(year, month, year_number, request.user, form.cleaned_data["note"])
        except FinanceError as exc:
            return _fail(request, exc, "finance:locks")
        messages.success(request, _("Mois clôturé : plus aucune écriture ne peut y être modifiée."))
        return redirect("finance:locks")
    locks = MonthLock.objects.filter(year=year).select_related("locked_by")
    lock_by_month = {(lock.month, lock.year_number): lock for lock in locks}
    months = []
    for item in services.months_for(year):
        lock = lock_by_month.get((item["month"], item["year"]))
        months.append(dict(item, locked=lock is not None, lock_pk=lock.pk if lock else 0,
                           locked_at=lock.locked_at if lock else None,
                           locked_by=lock.locked_by if lock else None,
                           flows=services.month_flows(year, item["month"], item["year"])))
    return render(request, "finance/locks.html", {
        "page_title": _("Clôtures mensuelles"), "year": year, "years": SchoolYear.objects.all(),
        "form": form, "months": months,
    })


@fine_required("finance.lock", MODULE)
@require_POST
def lock_create(request):
    year = _year(request)
    if year is None:
        return aucune_annee(request)
    month = int(request.POST.get("month", 0))
    year_number = int(request.POST.get("year_number", 0))
    try:
        services.lock_month(year, month, year_number, request.user, request.POST.get("note", ""))
    except FinanceError as exc:
        return _fail(request, exc, "finance:locks")
    messages.success(request, _("Mois %(mois)02d/%(annee)d clôturé.") % {"mois": month, "annee": year_number})
    return redirect("finance:locks")


@fine_required("finance.lock", MODULE)
@reauth_required
@require_POST
def lock_reopen(request, pk):
    """Réouverture : ré-authentification + motif obligatoire, tracée en rouge."""
    lock = get_object_or_404(MonthLock, pk=pk)
    reason = request.POST.get("reason", "").strip()
    try:
        services.unlock_month(lock.year, lock.month, lock.year_number, request.user, reason)
    except FinanceError as exc:
        return _fail(request, exc, "finance:locks")
    messages.warning(request, _("Mois rouvert. L'action est journalisée."))
    return redirect("finance:locks")
