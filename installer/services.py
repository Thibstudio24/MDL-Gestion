"""Assistance à la première installation : prérequis vérifiés, identité, administrateur."""
from __future__ import annotations

import os
from typing import Any

from django.conf import settings


def is_installed() -> bool:
    """Une installation est faite dès qu'un compte existe."""
    from accounts.models import User

    return User.objects.exists()


def prerequisites() -> list[dict[str, Any]]:
    """Contrôles affichés à l'écran : ce qui est prêt, ce qui doit être corrigé."""
    checks: list[dict[str, Any]] = []
    secret = getattr(settings, "SECRET_KEY", "")
    checks.append({
        "label": "Clé secrète changée",
        "ok": bool(secret) and secret != "dev-insecure-change-me",
        "detail": "Renseignez security.secret_key dans config/instance.json ou MDL_SECRET_KEY.",
    })
    checks.append({
        "label": "Mode debug désactivé",
        "ok": not getattr(settings, "DEBUG", False),
        "detail": "DEBUG doit valoir false en production (app.debug).",
    })
    hosts = getattr(settings, "ALLOWED_HOSTS", [])
    checks.append({
        "label": "Hôtes autorisés définis",
        "ok": bool(hosts) and hosts != ["*"],
        "detail": "Indiquez votre sous-domaine *.alwaysdata.net dans app.allowed_hosts.",
    })
    for path, label in ((settings.MEDIA_ROOT, "Dossier des fichiers (media/)"),
                        (settings.STATIC_ROOT or settings.BASE_DIR / "staticfiles", "Dossier statique")):
        try:
            os.makedirs(path, exist_ok=True)
            writable = os.access(path, os.W_OK)
        except OSError:
            writable = False
        checks.append({"label": "%s accessible en écriture" % label, "ok": writable,
                       "detail": "Chemin : %s" % path})
    try:
        from django.db import connection

        connection.ensure_connection()
        database_ok = True
        detail = connection.settings_dict.get("NAME") or connection.settings_dict.get("ENGINE", "")
    except Exception as exc:  # noqa: BLE001 - afficher l'erreur plutôt que planter l'assistant
        database_ok = False
        detail = str(exc)[:200]
    checks.append({"label": "Base de données joignable", "ok": database_ok, "detail": str(detail)})
    try:
        from accounts.models import User

        User.objects.count()
        migrated = True
    except Exception as exc:  # noqa: BLE001
        migrated = False
        detail = str(exc)[:200]
    checks.append({"label": "Migrations appliquées", "ok": migrated,
                   "detail": "python manage.py migrate" if migrated else detail})
    checks.append({
        "label": "Fuseau horaire",
        "ok": str(getattr(settings, "TIME_ZONE", "")) == "Europe/Paris",
        "detail": "Europe/Paris (semaines commençant le lundi, dates en d/m/Y).",
    })
    return checks


def prerequisites_ok() -> bool:
    blocking = ("Base de données joignable", "Migrations appliquées")
    return all(item["ok"] for item in prerequisites() if item["label"] in blocking)
