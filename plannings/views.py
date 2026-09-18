"""Vues du planning de la salle."""
from __future__ import annotations

import csv

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from audit import services as audit
from core import permissions
from core.decorators import module_required
from core.models import SchoolYear
from plannings import services
from plannings.models import CHOICES, Availability, Campaign, Slot

MODULE = "planning_salle"


@module_required(MODULE)
def planning_list(request):
    """Campagnes en cours et passées."""
    year = SchoolYear.get_or_current()
    campaigns = Campaign.objects.filter(year=year).select_related("year")
    rows = [{"campaign": item, "stats": services.campaign_stats(item)} for item in campaigns]
    return render(request, "plannings/list.html", {
        "page_title": _("Planning de la salle"), "year": year, "rows": rows,
        "can_edit": permissions.can_edit(request.user, MODULE),
    })


@module_required(MODULE)
def campaign_detail(request, pk):
    """Grille des créneaux et réponses."""
    campaign = get_object_or_404(Campaign.objects.select_related("year"), pk=pk)
    slots = list(Slot.objects.filter(campaign=campaign))
    mine = {item.slot_id: item for item in Availability.objects.filter(campaign=campaign, member=request.user)}
    return render(request, "plannings/detail.html", {
        "page_title": campaign.label, "campaign": campaign, "slots": slots, "mine": mine,
        "stats": services.campaign_stats(campaign), "days": services.by_day(campaign),
        "choice_options": CHOICES,
        "can_edit": permissions.can_edit(request.user, MODULE),
    })


@module_required(MODULE)
def coverage(request, pk):
    """Couverture : créneaux sans gérant en évidence."""
    campaign = get_object_or_404(Campaign, pk=pk)
    stats = services.campaign_stats(campaign)
    rows = sorted(stats["coverage"].values(), key=lambda row: (row["covered"], row["slot"].weekday))
    return render(request, "plannings/coverage.html", {
        "page_title": _("Couverture"), "campaign": campaign, "stats": stats, "rows": rows,
    })


@module_required(MODULE)
def my_availabilities(request):
    """Mes réponses, toutes campagnes confondues."""
    items = (Availability.objects.filter(member=request.user).select_related("campaign", "slot")
             .order_by("-campaign__start_date", "slot__weekday", "slot__start_time"))
    return render(request, "plannings/mine.html", {"page_title": _("Mes disponibilités"), "items": items})


@module_required(MODULE, edit=True)
@require_POST
def save_availability(request):
    slot = get_object_or_404(Slot, pk=request.POST.get("slot"))
    choice = request.POST.get("choice", "yes")
    try:
        services.save_availability(request.user, slot.campaign, slot, choice, request.POST.get("note", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("plannings:campaign_detail", pk=slot.campaign_id)
    messages.success(request, _("Réponse enregistrée."))
    return redirect("plannings:campaign_detail", pk=slot.campaign_id)


@module_required(MODULE, edit=True)
def campaign_create(request):
    """Création d'une campagne et de ses créneaux types."""
    year = SchoolYear.get_or_current()
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.year = year
        campaign.created_by = request.user
        campaign.save()
        _default_slots(campaign)
        audit.log(request.user, "planning.campaign_created", MODULE, campaign, "Campagne créée : %s" % campaign)
        messages.success(request, _("Campagne créée avec ses créneaux types. Publiez-la pour ouvrir les réponses."))
        return redirect("plannings:campaign_detail", pk=campaign.pk)
    return render(request, "plannings/campaign_form.html", {"page_title": _("Nouvelle campagne"), "form": form})


@module_required(MODULE, edit=True)
@require_POST
def publish(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    services.publish(campaign, request.user)
    messages.success(request, _("Campagne publiée : les membres ont été notifiés."))
    return redirect("plannings:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def close(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    services.close_campaign(campaign, request.user)
    messages.success(request, _("Campagne clôturée."))
    return redirect("plannings:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def delete(request, pk):
    """Supprime une campagne de planning de salle et ses créneaux."""
    campaign = get_object_or_404(Campaign, pk=pk)
    label = str(campaign)
    campaign.delete()
    audit.log(request.user, "planning.campaign_deleted", MODULE, None,
              "Campagne de planning supprimée : %s" % label, level="warn", request=request)
    messages.success(request, _("Campagne « %(label)s » supprimée.") % {"label": label})
    return redirect("plannings:planning_list")


@module_required(MODULE, edit=True)
@require_POST
def remind(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    count = services.send_reminder(campaign, request.user)
    messages.success(request, _("Rappel envoyé à %(nombre)s membre(s).") % {"nombre": count})
    return redirect("plannings:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def slot_add(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    slot = Slot.objects.create(campaign=campaign, weekday=int(request.POST.get("weekday", 1)),
                               start_time=request.POST.get("start_time", "12:00"),
                               end_time=request.POST.get("end_time", "13:00"),
                               capacity=int(request.POST.get("capacity", 1) or 1),
                               label=request.POST.get("label", "")[:140])
    audit.log(request.user, "planning.campaign_updated", MODULE, campaign, "Créneau ajouté : %s" % slot)
    messages.success(request, _("Créneau ajouté."))
    return redirect("plannings:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def slot_delete(request, pk):
    slot = get_object_or_404(Slot, pk=pk)
    campaign_id = slot.campaign_id
    slot.delete()
    messages.success(request, _("Créneau supprimé."))
    return redirect("plannings:campaign_detail", pk=campaign_id)


@module_required(MODULE)
def export(request, pk):
    """Export de la grille : CSV pour tableur, PDF A4 paysage pour affichage papier."""
    campaign = get_object_or_404(Campaign, pk=pk)
    if request.GET.get("format") == "pdf":
        from plannings import pdf

        audit.log(request.user, "planning.campaign_updated", MODULE, campaign, "Export du planning (PDF)")
        return pdf.campaign_pdf(campaign)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="planning-%s.csv"' % campaign.pk
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Jour", "Créneau", "Intitulé", "Gérants", "En attente", "Indisponibles"])
    for row in services.by_day(campaign):
        writer.writerow([row["label"], "%s–%s" % (row["slot"].start_time.strftime("%H:%M"),
                                                  row["slot"].end_time.strftime("%H:%M")),
                         row["slot"].label,
                         ", ".join(str(item.member) for item in row["yes"]),
                         ", ".join(str(item.member) for item in row["maybe"]),
                         ", ".join(str(item.member) for item in row["no"])])
    audit.log(request.user, "planning.campaign_updated", MODULE, campaign, "Export du planning")
    return response


def _default_slots(campaign) -> None:
    """Créneaux types d'une MDL : permanences du midi et ouverture du foyer."""
    defaults = [(1, "12:00", "13:00", "Permanence du lundi"), (2, "12:00", "13:00", "Permanence du mardi"),
                (3, "12:00", "13:00", "Permanence du mercredi"), (4, "12:00", "13:00", "Permanence du jeudi"),
                (5, "12:00", "13:00", "Permanence du vendredi"), (5, "16:00", "18:00", "Ouverture du foyer")]
    for index, (weekday, start, end, label) in enumerate(defaults):
        Slot.objects.create(campaign=campaign, weekday=weekday, start_time=start, end_time=end,
                            label=label, capacity=2, order=(index + 1) * 10)


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["label", "description", "week", "start_date", "end_date", "slot_duration"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}),
                   "end_date": forms.DateInput(attrs={"type": "date"}),
                   "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["start_date"].initial = today
        self.fields["end_date"].initial = today.replace(day=min(28, today.day + 14))
