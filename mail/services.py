"""Messagerie : file SMTP en base, diffusions, purge."""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from audit import services as audit

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
READ_RETENTION_DAYS = 180


def queue_email(*, to_email: str, recipient_user=None, subject: str, text_body: str,
                kind: str = "", urgent: bool = False, notification=None) -> "Outbox":
    """Met un courriel en file. Jamais d'envoi synchrone dans une requête web."""
    from mail.models import Outbox

    return Outbox.objects.create(to_email=to_email[:254], recipient_user=recipient_user,
                                 subject=subject[:200], text_body=text_body or subject,
                                 kind=kind[:20], urgent=bool(urgent))


def drain_outbox(limit: int = 30) -> dict[str, int]:
    """Vide la file d'attente. Chaque échec est compté, au-delà de 5 tentatives on abandonne."""
    from mail.models import Outbox

    report = {"envoyes": 0, "echecs": 0, "abandons": 0}
    if not getattr(settings, "MAIL_ENABLED", False):
        queued = Outbox.objects.filter(status="queued")
        report["ignores"] = queued.count()
        queued.update(status="skipped", error="SMTP désactivé")
        return report
    for item in Outbox.objects.filter(status="queued").order_by("-urgent", "queued_at")[:limit]:
        item.attempts += 1
        try:
            message = EmailMultiAlternatives(subject=item.subject, body=item.text_body,
                                             from_email=_from_email(), to=[item.to_email])
            message.send(fail_silently=False)
            item.status = "sent"
            item.sent_at = timezone.now()
            item.error = ""
            report["envoyes"] += 1
        except Exception as exc:  # noqa: BLE001 - on ne bloque pas la file sur un échec SMTP
            item.error = str(exc)[:400]
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "failed"
                report["abandons"] += 1
            else:
                report["echecs"] += 1
        item.save(update_fields=["status", "attempts", "error", "sent_at"])
    return report


def _from_email() -> str:
    brand = None
    try:
        from core.models import Setting

        brand = Setting.brand()
    except Exception:  # pragma: no cover - base non migrée
        brand = {}
    name = (brand or {}).get("association") or "MDL"
    sender = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "mdl@localhost"
    return "%s <%s>" % (name, sender) if "<" not in sender else sender


def send_test_email(to_email: str) -> None:
    """Test SMTP immédiat depuis Réglages → Envois."""
    message = EmailMultiAlternatives(subject="Test de messagerie",
                                     body="Ce message confirme que le SMTP est correctement configuré.",
                                     from_email=_from_email(), to=[to_email])
    message.send(fail_silently=False)


def audience_members(broadcast) -> list:
    """Résout les destinataires d'une diffusion."""
    from accounts.models import User

    if broadcast.audience == "board":
        return list(User.objects.filter(status="active", role__is_board=True))
    if broadcast.audience == "role":
        return list(User.objects.filter(status="active", role__in=broadcast.roles.all()))
    return list(User.objects.filter(status="active"))


def send_broadcast(broadcast, actor=None) -> int:
    """Crée les destinataires, notifie et met les courriels en file."""
    from mail.models import Recipient
    from notifications import services as notifications

    members = audience_members(broadcast)
    with transaction.atomic():
        for member in members:
            Recipient.objects.get_or_create(broadcast=broadcast, user=member)
        broadcast.status = "sent"
        broadcast.sent_at = timezone.now()
        broadcast.save(update_fields=["status", "sent_at"])
    for member in members:
        notifications.notify(member, "mail", broadcast.subject, broadcast.body[:240],
                             url="/messages/%d/" % broadcast.pk,
                             level="danger" if broadcast.kind == "alert" else "info",
                             force=broadcast.kind in ("important", "alert"))
    audit.log(actor, "mail.broadcast_sent", "mail", broadcast, "Diffusion envoyée à %s membre(s)" % len(members))
    return len(members)


def send_scheduled(now=None) -> int:
    """Le cron envoie les diffusions programmées dont l'heure est venue."""
    from mail.models import Broadcast

    now = now or timezone.now()
    due = Broadcast.objects.filter(status="scheduled", scheduled_at__lte=now)
    count = 0
    for broadcast in due:
        send_broadcast(broadcast, broadcast.created_by)
        count += 1
    return count


def cancel_broadcast(broadcast, actor) -> None:
    broadcast.status = "cancelled"
    broadcast.save(update_fields=["status"])
    audit.log(actor, "mail.broadcast_cancelled", "mail", broadcast, "Diffusion annulée : %s" % broadcast)


def schedule(broadcast, when, actor) -> None:
    if when <= timezone.now():
        raise ValueError("La date programmée doit être dans le futur.")
    broadcast.scheduled_at = when
    broadcast.status = "scheduled"
    broadcast.save(update_fields=["scheduled_at", "status"])
    audit.log(actor, "mail.broadcast_scheduled", "mail", broadcast,
              "Diffusion programmée pour le %s" % when.strftime("%d/%m/%Y %H:%M"))


def mark_read(recipient) -> None:
    if recipient.read_at is None:
        recipient.read_at = timezone.now()
        recipient.save(update_fields=["read_at"])
        audit.log(recipient.user, "mail.read", "mail", recipient.broadcast, "Message lu : %s" % recipient.broadcast)


def unread_count(user) -> int:
    from mail.models import Recipient

    return Recipient.objects.filter(user=user, read_at__isnull=True, archived_at__isnull=True).count()


def inbox(user, unread_only: bool = False):
    from mail.models import Recipient

    items = Recipient.objects.filter(user=user, archived_at__isnull=True).select_related("broadcast")
    if unread_only:
        items = items.filter(read_at__isnull=True)
    return items.order_by("-created_at")


def purge_read_emails(days: int = READ_RETENTION_DAYS, dry_run: bool = False) -> int:
    """Purge les messages lus et les courriels de la file déjà traités (quota disque)."""
    from mail.models import Outbox, Recipient

    limit = timezone.now() - timezone.timedelta(days=days)
    recipients = Recipient.objects.filter(read_at__isnull=False, created_at__lt=limit)
    outbox = Outbox.objects.filter(status__in=("sent", "failed", "skipped"), queued_at__lt=limit)
    count = recipients.count() + outbox.count()
    if dry_run:
        return count
    with transaction.atomic():
        recipients.delete()
        outbox.delete()
    return count


def stats() -> dict[str, Any]:
    """Chiffres pour la tuile du tableau de bord et la page d'administration."""
    from mail.models import Broadcast, Outbox, Recipient

    return {
        "diffusions": Broadcast.objects.count(),
        "envoyees": Broadcast.objects.filter(status="sent").count(),
        "programmées": Broadcast.objects.filter(status="scheduled").count(),
        "file": Outbox.objects.filter(status="queued").count(),
        "echecs": Outbox.objects.filter(status="failed").count(),
        "non_lus": Recipient.objects.filter(read_at__isnull=True).count(),
    }
