"""Web Push réel (pywebpush + VAPID). Échec → repli badge in-app + e-mail, désactivation après 5."""
from __future__ import annotations

import json

from django.conf import settings
from django.utils import timezone

from core.models import Setting

MAX_FAILURES = 5
TTL_SECONDS = 24 * 3600


def vapid_keys() -> tuple[str, str, str]:
    public = str(getattr(settings, "VAPID_PUBLIC_KEY", "") or Setting.value("push", "public_key", "") or "")
    private = str(getattr(settings, "VAPID_PRIVATE_KEY", "") or Setting.value("push", "private_key", "") or "")
    claims = str(getattr(settings, "VAPID_CLAIMS_EMAIL", "") or Setting.value("push", "claims_email", "") or "")
    return public, private, claims


def public_key() -> str:
    return vapid_keys()[0]


def send_push(user, title: str, body: str = "", url: str = "") -> bool:
    """Envoie la notification à tous les appareils du membre. Retourne True si au moins un envoi passe."""
    public, private, claims = vapid_keys()
    if not (public and private):
        return False
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover
        return False
    payload = json.dumps({"title": title, "body": body, "url": url or "/", "tag": "mdl"}, ensure_ascii=False)
    sent = False
    for device in list(user.push_devices.filter(disabled=False)):
        subscription = {"endpoint": device.endpoint, "keys": device.keys or {}}
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=private,
                vapid_claims={"sub": "mailto:%s" % (claims or "mdl@localhost")},
                ttl=TTL_SECONDS,
            )
            device.failures = 0
            device.last_success = timezone.now()
            device.save(update_fields=["failures", "last_success"])
            sent = True
        except WebPushException as exc:
            device.failures = (device.failures or 0) + 1
            if device.failures >= MAX_FAILURES or getattr(exc, "response", None) is not None and \
                    getattr(exc.response, "status_code", 0) in (404, 410):
                device.disabled = True
            device.save(update_fields=["failures", "disabled"])
        except Exception:
            device.failures = (device.failures or 0) + 1
            if device.failures >= MAX_FAILURES:
                device.disabled = True
            device.save(update_fields=["failures", "disabled"])
    return sent


def subscribe(user, subscription: dict, label: str = "", user_agent: str = ""):
    """Abonnement idempotent : le même endpoint ne crée pas de doublon."""
    from notifications.models import PushDevice

    endpoint = (subscription or {}).get("endpoint", "")
    if not endpoint:
        return None
    keys = (subscription or {}).get("keys", {}) or {}
    device, _created = PushDevice.objects.update_or_create(
        endpoint=endpoint[:500],
        defaults={"user": user, "keys": keys, "ua": (user_agent or "")[:240], "label": label[:80],
                  "disabled": False, "failures": 0},
    )
    return device


def unsubscribe(user, endpoint: str) -> int:
    from notifications.models import PushDevice

    return PushDevice.objects.filter(user=user, endpoint=endpoint).delete()[0]


def device_count(user=None) -> int:
    from notifications.models import PushDevice

    queryset = PushDevice.objects.filter(disabled=False)
    return queryset.filter(user=user).count() if user is not None else queryset.count()
