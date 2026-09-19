"""Vues du planning de ménage."""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from audit import services as audit
from chores import services
from chores.models import DAYS, Assignment, Campaign, ChorePreference, Response, Task
from core import permissions
from core.decorators import module_required
from core.models import SchoolYear

MODULE = "planning_menage"


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["label", "description", "week", "start_date", "end_date", "deadline"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}),
                   "end_date": forms.DateInput(attrs={"type": "date"}),
                   "deadline": forms.DateInput(attrs={"type": "date"}),
                   "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["start_date"].initial = today
        self.fields["end_date"].initial = today
        self.fields["deadline"].initial = today


@module_required(MODULE)
def chores_list(request):
    """Mes tâches de la semaine et ma réponse à la campagne en cours."""
    today = timezone.localdate()
    campaign = (Campaign.objects.filter(published=True, closed=False, start_date__lte=today)
                .order_by("-start_date").first()
                or Campaign.objects.order_by("-start_date").first())
    mine = (Assignment.objects.filter(member=request.user).select_related("campaign")
            .order_by("-campaign__start_date", "weekday"))[:20]
    response = Response.objects.filter(campaign=campaign, member=request.user).first() if campaign else None
    pref = ChorePreference.objects.filter(campaign=campaign, member=request.user).first() if campaign else None
    return render(request, "chores/list.html", {
        "page_title": _("Planning de ménage"), "campaign": campaign, "mine": mine, "response": response,
        "progress": services.campaign_progress(campaign) if campaign else None,
        "can_edit": permissions.can_edit(request.user, MODULE),
        "days": DAYS, "tasks": list(campaign.tasks.all()) if campaign else [],
        "pref": pref,
        "pref_days": pref.days_list if pref else [],
        "pref_refused": pref.refused_ids if pref else [],
    })


@module_required(MODULE)
@require_POST
def respond(request):
    campaign = get_object_or_404(Campaign, pk=request.POST.get("campaign"))
    try:
        services.save_response(request.user, campaign, request.POST.get("choice", "accept"),
                               request.POST.get("note", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("chores:chores_list")
    messages.success(request, _("Réponse enregistrée. Merci !"))
    return redirect("chores:chores_list")


@module_required(MODULE)
@require_POST
def mark_done(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)
    try:
        services.mark_done(request.user, assignment, request.FILES.get("proof"), request.POST.get("note", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("chores:chores_list")
    messages.success(request, _("Tâche déclarée faite : elle attend la validation."))
    return redirect("chores:chores_list")


@module_required(MODULE)
def admin_tracking(request):
    """Suivi administrateur : toutes les tâches, preuves, retards."""
    year = SchoolYear.get_or_current()
    campaigns = Campaign.objects.filter(year=year)
    campaign_id = request.GET.get("campagne")
    campaign = campaigns.filter(pk=campaign_id).first() if campaign_id else campaigns.first()
    assignments = (Assignment.objects.filter(campaign=campaign).select_related("member", "campaign")
                   if campaign else Assignment.objects.none())
    return render(request, "chores/admin.html", {
        "page_title": _("Suivi du ménage"), "year": year, "campaigns": campaigns, "campaign": campaign,
        "assignments": assignments,
        "progress": services.campaign_progress(campaign) if campaign else None,
    })


@module_required(MODULE, edit=True)
def campaigns(request):
    year = SchoolYear.get_or_current()
    rows = [{"campaign": item, "progress": services.campaign_progress(item)}
            for item in Campaign.objects.filter(year=year)]
    return render(request, "chores/campaigns.html", {
        "page_title": _("Campagnes de ménage"), "year": year, "rows": rows,
    })


@module_required(MODULE, edit=True)
def campaign_create(request):
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.year = SchoolYear.get_or_current()
        campaign.created_by = request.user
        campaign.save()
        services.ensure_tasks(campaign)
        audit.log(request.user, "chores.campaign_created", MODULE, campaign, "Campagne créée : %s" % campaign)
        messages.success(request, _("Campagne créée. Publiez-la pour attribuer les tâches."))
        return redirect("chores:campaign_detail", pk=campaign.pk)
    return render(request, "chores/campaign_form.html", {"page_title": _("Nouvelle campagne"), "form": form})


@module_required(MODULE, edit=True)
def campaign_detail(request, pk):
    from accounts.models import User

    campaign = get_object_or_404(Campaign.objects.select_related("year"), pk=pk)
    prefs = list(ChorePreference.objects.filter(campaign=campaign).select_related("member"))
    refused_labels = {t.pk: t.label for t in campaign.tasks.all()}
    for pref in prefs:
        pref.refused_labels = [refused_labels.get(i, "#%s" % i) for i in pref.refused_ids]
    return render(request, "chores/campaign_detail.html", {
        "page_title": campaign.label, "campaign": campaign,
        "progress": services.campaign_progress(campaign),
        "assignments": Assignment.objects.filter(campaign=campaign).select_related("member"),
        "responses": Response.objects.filter(campaign=campaign).select_related("member"),
        "tasks": list(campaign.tasks.all()), "days": DAYS, "prefs": prefs,
        "members": User.objects.filter(status="active").order_by("last_name", "first_name"),
    })


@module_required(MODULE, edit=True)
@require_POST
def delete(request, pk):
    """Supprime une campagne de ménage et les tâches qui en découlent."""
    campaign = get_object_or_404(Campaign, pk=pk)
    label = str(campaign)
    campaign.delete()
    audit.log(request.user, "chores.campaign_deleted", MODULE, None,
              "Campagne de ménage supprimée : %s" % label, level="warn", request=request)
    messages.success(request, _("Campagne « %(label)s » supprimée.") % {"label": label})
    return redirect("chores:campaigns")


@module_required(MODULE, edit=True)
@require_POST
def publish(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    count = services.publish(campaign, request.user)
    messages.success(request, _("%(nombre)s tâche(s) attribuée(s) et notifiée(s).") % {"nombre": count})
    return redirect("chores:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def close(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    campaign.closed = True
    campaign.save(update_fields=["closed"])
    audit.log(request.user, "chores.campaign_published", MODULE, campaign, "Campagne clôturée : %s" % campaign)
    messages.success(request, _("Campagne clôturée."))
    return redirect("chores:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def remind(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    count = services.send_reminders(campaign)
    messages.success(request, _("%(nombre)s rappel(s) envoyé(s).") % {"nombre": count})
    return redirect("chores:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def validate(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)
    services.validate(assignment, request.user)
    messages.success(request, _("Tâche validée."))
    return redirect("chores:admin_tracking")


@module_required(MODULE, edit=True)
@require_POST
def request_redo(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)
    try:
        services.request_redo(assignment, request.user, request.POST.get("reason", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("chores:admin_tracking")
    messages.warning(request, _("Tâche renvoyée au membre avec le motif."))
    return redirect("chores:admin_tracking")

@module_required(MODULE, edit=True)
@require_POST
def task_add(request, pk):
    """L'administration choisit les tâches de la campagne (libellé, jour, lieu)."""
    campaign = get_object_or_404(Campaign, pk=pk)
    label = (request.POST.get("label") or "").strip()
    if not label:
        messages.error(request, _("Un libellé de tâche est requis."))
        return redirect("chores:campaign_detail", pk=pk)
    try:
        weekday = int(request.POST.get("weekday") or 1)
    except ValueError:
        weekday = 1
    if weekday not in dict(DAYS):
        weekday = 1
    Task.objects.create(campaign=campaign, label=label[:160], weekday=weekday,
                        zone=(request.POST.get("zone") or "Local MDL")[:120])
    audit.log(request.user, "chores.task_added", MODULE, campaign, "Tâche ajoutée : %s" % label)
    messages.success(request, _("Tâche ajoutée à la campagne."))
    return redirect("chores:campaign_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def task_delete(request, pk):
    campaign_task = get_object_or_404(Task, pk=pk)
    campaign = campaign_task.campaign
    if campaign_task.assignments.exists():
        messages.error(request, _("Cette tâche est déjà attribuée : réarrangez ou supprimez "
                                  "d'abord l'attribution."))
    else:
        label = campaign_task.label
        campaign_task.delete()
        audit.log(request.user, "chores.task_deleted", MODULE, campaign, "Tâche retirée : %s" % label)
        messages.success(request, _("Tâche retirée de la campagne."))
    return redirect("chores:campaign_detail", pk=campaign.pk)


@module_required(MODULE, edit=True)
@require_POST
def reassign(request, pk):
    """Réarrange une attribution : autre membre et/ou autre jour."""
    from accounts.models import User

    assignment = get_object_or_404(Assignment, pk=pk)
    member = get_object_or_404(User, pk=request.POST.get("member"))
    try:
        weekday = int(request.POST.get("weekday") or assignment.weekday)
    except ValueError:
        weekday = assignment.weekday
    if weekday not in dict(DAYS):
        weekday = assignment.weekday
    avant = "%s / %s" % (assignment.member, assignment.get_weekday_display())
    assignment.member = member
    assignment.weekday = weekday
    assignment.save(update_fields=["member", "weekday"])
    audit.log(request.user, "chores.assignment_updated", MODULE, assignment,
              "Tâche réarrangée (%s → %s / %s)" % (avant, member, assignment.get_weekday_display()))
    messages.success(request, _("Tâche réattribuée à %(membre)s (%(jour)s).")
                     % {"membre": member.get_full_name() or member.email,
                        "jour": assignment.get_weekday_display()})
    return redirect("chores:campaign_detail", pk=assignment.campaign_id)


@module_required(MODULE)
@require_POST
def save_prefs(request):
    """Le membre déclare ses jours disponibles et les tâches qu'il ne peut pas faire."""
    campaign = get_object_or_404(Campaign, pk=request.POST.get("campaign"))
    days = [d for d in request.POST.getlist("days") if d.isdigit() and int(d) in dict(DAYS)]
    refused = [t for t in request.POST.getlist("refused") if t.isdigit()]
    ChorePreference.objects.update_or_create(
        campaign=campaign, member=request.user,
        defaults={"days": ",".join(days), "refused": ",".join(refused)})
    messages.success(request, _("Préférences enregistrées : l'attribution en tiendra compte."))
    return redirect("chores:chores_list")
