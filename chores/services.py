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


def generate_assignments(campaign, actor, seed: int | None = None) -> int:
    """Attribue les tâches types en tournant entre les membres volontaires."""
    from chores.models import Assignment, Response, DEFAULT_TASKS

    volunteers = [item.member for item in Response.objects.filter(campaign=campaign, choice="accept")
                  .select_related("member")]
    if not volunteers:
        from accounts.models import User

        volunteers = list(User.objects.filter(status="active"))
    if not volunteers:
        return 0
    picker = random.Random(seed)
    order = volunteers[:]
    picker.shuffle(order)
    created = 0
    for index, task in enumerate(DEFAULT_TASKS):
        member = order[index % len(order)]
        Assignment.objects.get_or_create(
            campaign=campaign, member=member, task=task,
            defaults={"weekday": (index % 5) + 1, "zone": "Local MDL", "week": campaign.week,
                      "status": "todo"})
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
    from chores.models import Assignment

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
