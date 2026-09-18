"""URLs absolues pour les courriels : jamais de lien nu « /page ».

Un courriel affiche hors de l'application : un lien relatif n'est pas
cliquable. ``BASE_URL`` (config/instance.json, ``app.base_url`` ou
``MDL_BASE_URL``) fait foi ; à défaut, le premier hôte autorisé concret
sert de base en https.
"""
from __future__ import annotations

from django.conf import settings


def site_base_url() -> str:
    base = str(getattr(settings, "BASE_URL", "") or "").rstrip("/")
    if base:
        return base
    hotes = [h for h in (getattr(settings, "ALLOWED_HOSTS", []) or [])
             if h and "*" not in h and not h.startswith(".")]
    if hotes:
        return "https://%s" % hotes[0]
    return ""


def absolute_url(path: str) -> str:
    """``/inviter/abc/`` → ``https://mdl-xxx.alwaysdata.net/inviter/abc/``."""
    if not path:
        return path
    if path.startswith(("http://", "https://")):
        return path
    return "%s%s" % (site_base_url(), path)
