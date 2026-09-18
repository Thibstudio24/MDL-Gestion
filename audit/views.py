"""Journal d'audit : filtres, détail avant/après, export CSV."""
from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from audit import services as audit
from audit.models import ACTION_CHOICES, AuditEntry
from audit.services import export_rows
from core.decorators import administrator_required, module_required
from core.export import csv_response


def _filters(request):
    queryset = AuditEntry.objects.select_related("actor")
    params = {}
    if request.GET.get("q"):
        params["q"] = request.GET["q"].strip()
        queryset = queryset.filter(message__icontains=params["q"]) | queryset.filter(object_repr__icontains=params["q"])
    if request.GET.get("actor"):
        params["actor"] = request.GET["actor"]
        queryset = queryset.filter(actor_label__icontains=params["actor"])
    if request.GET.get("module"):
        params["module"] = request.GET["module"]
        queryset = queryset.filter(module=params["module"])
    if request.GET.get("action"):
        params["action"] = request.GET["action"]
        queryset = queryset.filter(action=params["action"])
    if request.GET.get("level"):
        params["level"] = request.GET["level"]
        queryset = queryset.filter(level=params["level"])
    if request.GET.get("depuis"):
        params["depuis"] = request.GET["depuis"]
        queryset = queryset.filter(at__gte=params["depuis"])
    if request.GET.get("jours"):
        params["jours"] = request.GET["jours"]
        try:
            queryset = queryset.filter(at__gte=timezone.now() - timedelta(days=int(params["jours"])))
        except ValueError:
            pass
    return queryset.order_by("-at", "-id"), params


@module_required("audit")
def list_view(request):
    queryset, params = _filters(request)
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    modules = sorted({value for value in AuditEntry.objects.values_list("module", flat=True)
                      .distinct() if value})
    return render(request, "audit/list.html", {
        "page_obj": page,
        "params": params,
        "actions": ACTION_CHOICES,
        "modules": modules,
        "levels": [("info", "info"), ("warn", "avertissement"), ("danger", "danger")],
        "page_title": "Journal d'audit",
        "keep_years": 5,
    })


@module_required("audit")
def detail(request, pk: int):
    entry = AuditEntry.objects.select_related("actor").get(pk=pk)
    return render(request, "audit/detail.html", {"entry": entry, "page_title": "Ligne d'audit"})


@administrator_required
def clear(request):
    """Vide le journal. Réservé à l'administrateur, POST uniquement.

    La trace du vidage lui-même est écrite après la purge : le journal
    repart vide, à l'exception de cette ligne qui en garde la mémoire.
    """
    if request.method != "POST":
        raise PermissionDenied()
    deleted = audit.empty_log()
    audit.log(request.user, "settings.audit_cleared", "audit", None,
              "Journal d'audit vidé (%(n)s lignes supprimées)" % {"n": deleted},
              level="danger", request=request)
    messages.success(request, _("Journal vidé : %(n)s lignes supprimées.") % {"n": deleted})
    return redirect("audit:audit_list")


@module_required("audit")
def export(request):
    queryset, _params = _filters(request)
    headers = ["Horodatage", "Auteur", "Action", "Module", "Objet", "Message", "Gravité", "Origine", "IP", "Avant/après"]
    messages.info(request, _("Export du journal en cours."))
    return csv_response("audit-%s.csv" % timezone.localdate().strftime("%Y%m%d"), headers, export_rows(queryset))
