"""Notifications : matrice événement × canaux, envoi in-app / e-mail / push, heures de silence."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from core.models import Setting

# Événements obligatoires non coupables.
EVENTS = [
    {"key": "invitation", "label": "Invitation à rejoindre l'association", "mandatory": True},
    {"key": "password_reset", "label": "Réinitialisation de mot de passe", "mandatory": True},
    {"key": "security", "label": "Alerte de sécurité (A2F, mot de passe, intervention)", "mandatory": True},
    {"key": "mail", "label": "Message interne reçu"},
    {"key": "mail_reminder", "label": "Relance d'un message non lu"},
    {"key": "campaign_open", "label": "Ouverture d'une campagne"},
    {"key": "campaign_deadline", "label": "Clôture de campagne imminente"},
    {"key": "campaign_closed", "label": "Campagne clôturée"},
    {"key": "planning_published", "label": "Planning publié"},
    {"key": "swap_request", "label": "Demande d'échange"},
    {"key": "swap_answer", "label": "Réponse à une demande d'échange"},
    {"key": "menage_assigned", "label": "Ménage attribué"},
    {"key": "menage_reminder", "label": "Rappel de ménage (la veille)"},
    {"key": "menage_redo", "label": "Ménage à refaire"},
    {"key": "bilan_generated", "label": "Bilan généré"},
    {"key": "document_new", "label": "Nouveau document"},
    {"key": "document_locked", "label": "Catégorie verrouillée"},
    {"key": "finance_deleted", "label": "Écriture supprimée"},
    {"key": "quota_full", "label": "Quota de stockage"},
    {"key": "inactive_member", "label": "Membre inactif depuis 12 mois"},
    {"key": "year_closed", "label": "Année scolaire clôturée"},
    {"key": "devhub_intervention", "label": "Intervention technique", "mandatory": True},
    {"key": "update_available", "label": "Mise à jour disponible"},
]
MANDATORY = {event["key"] for event in EVENTS if event.get("mandatory")}
DEFAULT_MATRIX = {event["key"]: {"inapp": True, "email": False, "push": False} for event in EVENTS}
for _key in ("invitation", "password_reset", "security", "mail", "menage_assigned", "bilan_generated",
             "planning_published", "devhub_intervention"):
    DEFAULT_MATRIX[_key] = {"inapp": True, "email": True, "push": True}
for _key in MANDATORY:
    DEFAULT_MATRIX[_key]["inapp"] = True


def admin_matrix() -> dict:
    stored = Setting.value("notifications", "matrice", {}) or {}
    matrix = {key: dict(DEFAULT_MATRIX[key]) for key in DEFAULT_MATRIX}
    for key, channels in stored.items():
        if key in matrix and isinstance(channels, dict):
            matrix[key].update({channel: bool(value) for channel, value in channels.items()})
    for key in MANDATORY:
        matrix[key]["inapp"] = True
    return matrix


def matrix_for_admin() -> dict:
    return admin_matrix()


def save_matrix(payload: dict) -> None:
    stored = Setting.value("notifications", "matrice", {}) or {}
    for key, channels in (payload or {}).items():
        if key not in DEFAULT_MATRIX:
            continue
        current = dict(DEFAULT_MATRIX[key])
        current.update({channel: (channel in channels and bool(channels[channel]))
                        for channel in ("inapp", "email", "push")})
        if key in MANDATORY:
            current["inapp"] = True
        stored[key] = current
    Setting.set("notifications", "matrice", stored)


def matrix_for_user(user) -> dict:
    matrix = admin_matrix()
    try:
        prefs = {pref.kind: pref for pref in user.notification_prefs.all()}
    except Exception:
        prefs = {}
    for key, channels in matrix.items():
        pref = prefs.get(key)
        if pref is None:
            continue
        for channel in ("inapp", "email", "push"):
            value = getattr(pref, channel)
            if value is not None:
                channels[channel] = bool(value)
        if key in MANDATORY:
            channels["inapp"] = True
    return matrix


def save_user_matrix(user, payload: dict) -> None:
    from notifications.models import NotificationPreference

    base = admin_matrix()
    for key, channels in (payload or {}).items():
        if key not in DEFAULT_MATRIX:
            continue
        pref, _created = NotificationPreference.objects.get_or_create(user=user, kind=key)
        for channel in ("inapp", "email", "push"):
            if key in MANDATORY and channel == "inapp":
                setattr(pref, channel, None)
                continue
            wanted = bool(channels.get(channel))
            setattr(pref, channel, None if wanted == base[key][channel] else wanted)
        pref.save()


def reset_user_matrix(user) -> int:
    from notifications.models import NotificationPreference

    return NotificationPreference.objects.filter(user=user).delete()[0]


def in_quiet_hours(user) -> bool:
    quiet = getattr(user, "quiet_hours", {}) or {}
    if not quiet.get("actif"):
        silence = Setting.value("notifications", "silence", {}) or {}
        if not silence.get("actif"):
            return False
        quiet = silence
    try:
        start_h, start_m = (int(part) for part in str(quiet.get("debut", "22:00")).split(":"))
        end_h, end_m = (int(part) for part in str(quiet.get("fin", "07:00")).split(":"))
    except (ValueError, AttributeError):
        return False
    now = timezone.localtime()
    minutes = now.hour * 60 + now.minute
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if start == end:
        return False
    return minutes >= start if start > end else start <= minutes < end


def unread_count(user) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    try:
        return user.notifications.filter(read_at__isnull=True).count()
    except Exception:
        return 0


def notify(user, kind: str, title: str, body: str = "", *, url: str = "", level: str = "info",
           channels: set | None = None, force: bool = False) -> dict:
    """Émet une notification sur les canaux autorisés pour ce membre et cet événement."""
    from notifications.models import Notification

    matrix = matrix_for_user(user)
    allowed = matrix.get(kind, {"inapp": True})
    wanted = channels or {"inapp", "email", "push"}
    result = {"inapp": False, "email": False, "push": False}
    quiet = in_quiet_hours(user)

    if force or kind in MANDATORY or ("inapp" in wanted and allowed.get("inapp")):
        Notification.objects.create(user=user, kind=kind, title=title[:160], body=body,
                                    url=url[:240], level=level)
        result["inapp"] = True

    if not quiet and "email" in wanted and (force or allowed.get("email")) and getattr(user, "receive_personal_email", True):
        try:
            from mail.services import queue_email

            queue_email(to_email=user.email, recipient_user=user, subject=title, text_body=body or title,
                        kind=kind, notification=result)
            result["email"] = True
        except Exception:
            result["email"] = False

    if not quiet and "push" in wanted and (force or allowed.get("push")) and getattr(user, "push_enabled", True):
        from notifications.push import send_push

        result["push"] = send_push(user, title, body, url)

    if result["email"] or result["push"]:
        Notification.objects.filter(user=user, kind=kind, title=title[:160], email_sent=False).update(
            email_sent=result["email"], push_sent=result["push"])
    return result


def notify_many(users, kind: str, title: str, body: str = "", **kwargs) -> int:
    count = 0
    for user in users:
        notify(user, kind, title, body, **kwargs)
        count += 1
    return count


def purge_notifications(days: int = 90, dry_run: bool = False) -> int:
    from notifications.models import Notification

    limit = timezone.now() - timedelta(days=days)
    queryset = Notification.objects.filter(read_at__isnull=False, created_at__lt=limit)
    count = queryset.count()
    if not dry_run and count:
        return queryset.delete()[0]
    return count


def mark_read(user, notification_id: int | None = None) -> int:

    queryset = user.notifications.filter(read_at__isnull=True)
    if notification_id:
        queryset = queryset.filter(pk=notification_id)
    return queryset.update(read_at=timezone.now())
