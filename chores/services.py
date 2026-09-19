"""Logique du ménage : attribution, suivi, preuves, rappels, purges."""
from __future__ import annotations

import random
from typing import Any

from django.utils import timezone

from audit import services as audit
from notifications import services as notifications


def campaign_progress(campaign) -> dict[str, Any]:
    """Avancement d'une campagne : faites, à valider, en retard, membres sans réponse."""
    from accounts.models import User
    from chores.models import Assignment, Response

    assignments = Assignment.objects.filter(campaign=campaign)
    responded = set(Response.objects.filter(campaign=campaign).values_list("member_id", flat=True))
    assigned = set(assignments.values_list("member_id", flat=True))
    members = User.objects.filter(status="active")
    missing = members.exclude(pk__in=responded).count()
    late = 0
    today = timezone.localdate()
    for item in assignments:
        if item.status in ("todo", "redo") and today > campaign.end_date:
            late += 1
    return {
        "total": assignments.count(),
        "done": assignments.filter(status="validated").count(),
        "proof_pending": assignments.filter(status="done").count(),
        "todo": assignments.filter(status="todo").count(),
        "redo": assignments.filter(status="redo").count(),
        "late": late,
        "missing": missing,
        "assigned": len(assigned),
        "responded": len(responded),
        "pct": int(round(assignments.filter(status="validated").count() * 100 / assignments.count()))
        if assignments.count() else 0,
    }


def ensure_tasks(campaign) -> list:
    """Les tâches de la campagne : celles choisies par l'admin, sinon les 5 types.

    Créées dès la création de la campagne pour que l'administration puisse les
    modifier avant publication.
    """
    from chores.models import DEFAULT_TASKS, Task

    tasks = list(campaign.tasks.all())
    if not tasks:
        tasks = [Task.objects.create(campaign=campaign, label=nom, weekday=(index % 5) + 1)
                 for index, nom in enumerate(DEFAULT_TASKS)]
    return tasks


def generate_assignments(campaign, actor, seed: int | None = None) -> int:
    """Attribue chaque tâche au membre le moins chargé, en respectant les préférences.

    Sont exclus d'une tâche : le membre qui l'a refusée, puis (s'il reste du
    monde) ceux dont les jours disponibles ne comprennent pas le jour de la
    tâche. Les tâches déjà attribuées (éventuellement réarrangées à la main)
    ne sont pas touchées.
    """
    from chores.models import Assignment, ChorePreference, Response

    tasks = ensure_tasks(campaign)
    volunteers = [item.member for item in Response.objects.filter(campaign=campaign, choice="accept")
                  .select_related("member")]
    if not volunteers:
        from accounts.models import User

        volunteers = list(User.objects.filter(status="active"))
    if not volunteers:
        return 0
    prefs = {pref.member_id: pref for pref in ChorePreference.objects.filter(campaign=campaign)}
    charge = {membre.pk: Assignment.objects.filter(campaign=campaign, member=membre).count()
              for membre in volunteers}
    picker = random.Random(seed)
    tiebreak = {membre.pk: picker.random() for membre in volunteers}
    created = 0
    for tache in tasks:
        if Assignment.objects.filter(campaign=campaign, task_def=tache).exists():
            continue
        sans_refus = [m for m in volunteers
                      if tache.pk not in (prefs[m.pk].refused_ids if m.pk in prefs else [])]
        pool = sans_refus or volunteers
        dispo = [m for m in pool
                 if not (m.pk in prefs and prefs[m.pk].days) or tache.weekday in prefs[m.pk].days_list]
        choix = min(dispo or pool, key=lambda m: (charge[m.pk], tiebreak[m.pk]))
        Assignment.objects.create(campaign=campaign, member=choix, task=tache.label,
                                  task_def=tache, weekday=tache.weekday, zone=tache.zone,
                                  week=campaign.week, status="todo")
        charge[choix.pk] += 1
        created += 1
    audit.log(actor, "chores.generated", "planning_menage", campaign,
              "%s tâche(s) attribuée(s) pour %s" % (created, campaign))
    return created


def publish(campaign, actor) -> int:
    """Publie la campagne, attribue les tâches et notifie les membres concernés."""
    from chores.models import Assignment

    campaign.published = True
    campaign.save(update_fields=["published"])
    count = generate_assignments(campaign, actor)
    members = list({item.member for item in Assignment.objects.filter(campaign=campaign)
                    .select_related("member")})
    notifications.notify_many(members, "menage_assigned", "Ménage : votre tâche de la semaine",
                              "Consultez votre tâche pour %s et déposez une photo une fois faite." % campaign.label,
                              url="/menage/")
    audit.log(actor, "chores.campaign_published", "planning_menage", campaign,
              "Campagne publiée : %s tâche(s)" % count)
    return count


def mark_done(member, assignment, proof=None, note: str = ""):
    """Le membre déclare sa tâche faite, photo à l'appui."""

    if assignment.member_id != member.pk:
        raise ValueError("Cette tâche ne vous est pas attribuée.")
    assignment.status = "done"
    assignment.done_at = timezone.now()
    assignment.note = note[:240]
    if proof:
        assignment.proof = proof
    assignment.save()
    audit.log(member, "chores.response_saved", "planning_menage", assignment,
              "Tâche déclarée faite : %s" % assignment)
    return assignment


def validate(assignment, actor) -> None:
    assignment.status = "validated"
    assignment.validated_by = actor
    assignment.validated_at = timezone.now()
    assignment.save(update_fields=["status", "validated_by", "validated_at"])
    notifications.notify(assignment.member, "menage_assigned", "Ménage validé",
                         "Votre tâche « %s » a été validée." % assignment.task, url="/menage/")
    audit.log(actor, "chores.assignment_validated", "planning_menage", assignment,
              "Tâche validée : %s" % assignment)


def request_redo(assignment, actor, reason: str) -> None:
    """Refus motivé : la tâche repasse à faire, avec photo exigée."""
    if not reason.strip():
        raise ValueError("Un motif est obligatoire pour demander à refaire la tâche.")
    assignment.status = "redo"
    assignment.note = ("%s %s" % (assignment.note, reason)).strip()[:240]
    assignment.done_at = None
    assignment.save(update_fields=["status", "note", "done_at"])
    notifications.notify(assignment.member, "menage_redo", "Ménage : à refaire",
                         "Votre tâche « %s » doit être refaite : %s" % (assignment.task, reason),
                         url="/menage/")
    audit.log(actor, "chores.assignment_redo", "planning_menage", assignment,
              "Tâche à refaire : %s — %s" % (assignment, reason), level="warn")


def save_response(member, campaign, choice: str, note: str = ""):
    from chores.models import Response

    if not campaign.is_open:
        raise ValueError("La campagne n'accepte plus de réponse.")
    item, _created = Response.objects.update_or_create(campaign=campaign, member=member,
                                                       defaults={"choice": choice, "note": note[:240]})
    audit.log(member, "chores.response_saved", "planning_menage", item, "Réponse ménage : %s" % item)
    return item


def send_reminders(campaign=None) -> int:
    """Rappel aux membres dont la tâche n'est pas faite."""
    from chores.models import Assignment, Campaign

    campaigns = [campaign] if campaign else list(Campaign.objects.filter(published=True, closed=False))
    total = 0
    for item in campaigns:
        pending = Assignment.objects.filter(campaign=item, status__in=("todo", "redo")).select_related("member")
        if not pending:
            continue
        for assignment in pending:
            notifications.notify(assignment.member, "menage_reminder", "Ménage : tâche en attente",
                                 "Il reste « %s » à faire pour %s." % (assignment.task, item.label),
                                 url="/menage/")
            total += 1
        item.reminder_sent_at = timezone.now()
        item.save(update_fields=["reminder_sent_at"])
    return total


def close_expired_campaigns(today=None) -> int:
    """Le cron clôture les campagnes de ménage dont la semaine est passée."""
    from chores.models import Campaign

    today = today or timezone.localdate()
    expired = Campaign.objects.filter(published=True, closed=False, end_date__lt=today)
    count = expired.count()
    expired.update(closed=True)
    return count


def purge_photos(days: int = 180, dry_run: bool = False) -> int:
    """Les photos de preuve ne sont pas conservées indéfiniment (quota disque)."""
    from chores.models import Assignment

    limit = timezone.now() - timezone.timedelta(days=days)
    items = Assignment.objects.exclude(proof="").filter(validated_at__lt=limit)
    count = items.count()
    if dry_run:
        return count
    for item in items:
        if item.proof:
            item.proof.delete(save=False)
        item.proof = ""
        item.save(update_fields=["proof"])
    audit.log(None, "chores.proof_deleted", "planning_menage", None,
              "%s photo(s) de preuve purgée(s)" % count)
    return count
