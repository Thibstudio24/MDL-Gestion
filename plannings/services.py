"""Logique du planning : statistiques, publication, clôture, rappels."""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from audit import services as audit
from notifications import services as notifications


def campaign_stats(campaign) -> dict[str, Any]:
    """Taux de réponse, créneaux découverts, répartition par jour."""
    from accounts.models import User
    from plannings.models import Availability, Slot

    slots = list(Slot.objects.filter(campaign=campaign))
    members = User.objects.filter(status="active")
    expected = len(slots) * members.count()
    answers = Availability.objects.filter(campaign=campaign).select_related("slot")
    answered_members = {item.member_id for item in answers}
    answered = answers.filter(choice__in=("yes", "maybe")).count()
    missing = max(expected - answered, 0)
    coverage = {}
    gaps = 0
    for slot in slots:
        managers = len([item for item in answers if item.slot_id == slot.pk and item.choice == "yes"])
        coverage[slot.pk] = {"slot": slot, "managers": managers, "capacity": slot.capacity,
                             "covered": managers >= slot.capacity,
                             "candidates": len([item for item in answers if item.slot_id == slot.pk])}
        if managers < slot.capacity:
            gaps += 1
    return {
        "slots": len(slots), "members": members.count(), "expected": expected, "answered": answered,
        "missing": missing, "answered_members": len(answered_members),
        "reponse_pct": int(round(answered * 100 / expected)) if expected else 0,
        "gaps": gaps, "coverage": coverage,
    }


def by_day(campaign) -> list[dict[str, Any]]:
    """Grille lisible : un bloc par jour de la semaine avec les créneaux et les gérants."""
    from plannings.models import Availability, Slot

    stats = campaign_stats(campaign)
    answers = {item.pk: [] for item in Slot.objects.filter(campaign=campaign)}
    for item in Availability.objects.filter(campaign=campaign).select_related("member", "slot"):
        answers.setdefault(item.slot_id, []).append(item)
    days = []
    for slot in Slot.objects.filter(campaign=campaign).order_by("weekday", "start_time"):
        rows = answers.get(slot.pk, [])
        days.append({"slot": slot, "weekday": slot.weekday, "label": slot.get_weekday_display(),
                     "yes": [item for item in rows if item.choice == "yes"],
                     "maybe": [item for item in rows if item.choice == "maybe"],
                     "no": [item for item in rows if item.choice == "no"],
                     "covered": stats["coverage"].get(slot.pk, {}).get("covered", False)})
    return days


def publish(campaign, actor) -> None:
    """Publie la campagne et notifie les membres."""
    from accounts.models import User

    if campaign.published:
        return
    campaign.published = True
    campaign.save(update_fields=["published"])
    members = list(User.objects.filter(status="active").exclude(pk=getattr(actor, "pk", None)))
    notifications.notify_many(members, "planning_published", "Planning de la salle",
                              "Indiquez vos disponibilités pour %s avant le %s." % (
                                  campaign.label, campaign.end_date.strftime("%d/%m/%Y")),
                              url="/planning/%d/" % campaign.pk)
    audit.log(actor, "planning.published", "planning_salle", campaign, "Campagne publiée : %s" % campaign)


def close_campaign(campaign, actor) -> None:
    campaign.closed = True
    campaign.save(update_fields=["closed"])
    audit.log(actor, "planning.campaign_closed", "planning_salle", campaign, "Campagne clôturée : %s" % campaign)


def send_reminder(campaign, actor=None) -> int:
    """Rappel unique aux membres qui n'ont pas répondu."""
    from accounts.models import User
    from plannings.models import Availability

    answered = set(Availability.objects.filter(campaign=campaign).values_list("member_id", flat=True))
    pending = list(User.objects.filter(status="active").exclude(pk__in=answered))
    if not pending:
        return 0
    notifications.notify_many(pending, "campaign_deadline", "Planning : il manque votre réponse",
                              "Merci d'indiquer vos disponibilités pour %s avant le %s." % (
                                  campaign.label, campaign.end_date.strftime("%d/%m/%Y")),
                              url="/planning/%d/" % campaign.pk)
    campaign.reminder_sent_at = timezone.now()
    campaign.save(update_fields=["reminder_sent_at"])
    audit.log(actor, "planning.reminder_sent", "planning_salle", campaign,
              "Rappel envoyé à %s membre(s)" % len(pending))
    return len(pending)


def close_expired_campaigns(today=None) -> int:
    """Le cron clôture les campagnes dont la date de réponse est passée."""
    from plannings.models import Campaign

    today = today or timezone.localdate()
    expired = Campaign.objects.filter(published=True, closed=False, end_date__lt=today)
    count = expired.count()
    with transaction.atomic():
        expired.update(closed=True)
    return count


def save_availability(member, campaign, slot, choice: str, note: str = ""):
    """Enregistre (ou met à jour) la réponse d'un membre."""
    from plannings.models import Availability

    if not campaign.is_open:
        raise ValueError("La campagne n'accepte plus de réponse.")
    item, created = Availability.objects.update_or_create(
        campaign=campaign, member=member, slot=slot, defaults={"choice": choice, "note": note[:240]})
    audit.log(member, "planning.availability_saved", "planning_salle", item,
              "Disponibilité %s sur %s" % (item.get_choice_display(), slot))
    return item
