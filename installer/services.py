"""Assistance à la première installation : prérequis vérifiés, identité, administrateur."""
from __future__ import annotations

import os
from typing import Any

from django.conf import settings

from config import settings as instance


def is_installed() -> bool:
    """Une installation est faite dès qu'un compte existe."""
    from accounts.models import User

    return User.objects.exists()


def prerequisites() -> list[dict[str, Any]]:
    """Contrôles affichés à l'écran : ce qui est prêt, ce qui doit être corrigé.

    Chaque contrôle porte ``blocking`` : seuls les contrôles bloquants empêchent
    d'avancer. Un contrôle non bloquant signale quelque chose que l'assistant
    règle lui-même, ou un réglage à peaufiner plus tard — le verrouiller
    interdirait d'atteindre l'étape qui le corrige.
    """
    checks: list[dict[str, Any]] = []
    secret = getattr(settings, "SECRET_KEY", "")
    secret_ok = bool(secret) and secret != instance.DEFAULT_SECRET_KEY
    checks.append({
        "label": "Clé secrète changée",
        "ok": secret_ok,
        # Non bloquant par nécessité : c'est l'étape 2 qui génère la clé.
        # La rendre bloquante ici verrouillerait l'assistant sur un serveur neuf.
        "blocking": False,
        "detail": ("Clé en place." if secret_ok else
                   "Une clé de 50 caractères est générée et enregistrée à l'étape suivante "
                   "(config/instance.json, section security.secret_key). Vous pouvez aussi la "
                   "poser vous-même via MDL_SECRET_KEY."),
    })
    checks.append({
        "label": "Mode debug désactivé",
        "ok": not getattr(settings, "DEBUG", False),
        "blocking": False,
        "detail": "DEBUG doit valoir false en production (app.debug).",
    })
    hosts = getattr(settings, "ALLOWED_HOSTS", [])
    checks.append({
        "label": "Hôtes autorisés définis",
        "ok": bool(hosts) and hosts != ["*"],
        "blocking": False,
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
                       "blocking": False, "detail": "Chemin : %s" % path})
    try:
        from django.db import connection

        connection.ensure_connection()
        database_ok = True
        detail = connection.settings_dict.get("NAME") or connection.settings_dict.get("ENGINE", "")
    except Exception as exc:  # noqa: BLE001 - afficher l'erreur plutôt que planter l'assistant
        database_ok = False
        detail = str(exc)[:200]
    checks.append({"label": "Base de données joignable", "ok": database_ok, "blocking": True,
                   "detail": str(detail) if database_ok
                   else "%s — vérifiez la section database de config/instance.json." % detail})
    try:
        from accounts.models import User

        User.objects.count()
        migrated = True
        detail = "Les tables de l'application sont en place."
    except Exception as exc:  # noqa: BLE001
        migrated = False
        detail = "%s — lancez python manage.py migrate." % str(exc)[:200]
    checks.append({"label": "Migrations appliquées", "ok": migrated, "blocking": True,
                   "detail": detail})
    checks.append({
        "label": "Fuseau horaire",
        "ok": str(getattr(settings, "TIME_ZONE", "")) == "Europe/Paris",
        "blocking": False,
        "detail": "Europe/Paris (semaines commençant le lundi, dates en d/m/Y).",
    })
    return checks


def blocking_failures() -> list[dict[str, Any]]:
    """Contrôles bloquants en échec : ce que le message d'alerte doit nommer."""
    return [item for item in prerequisites() if item.get("blocking") and not item["ok"]]


def recommended_failures() -> list[dict[str, Any]]:
    """Contrôles non bloquants en échec, à signaler sans empêcher d'avancer."""
    return [item for item in prerequisites() if not item.get("blocking") and not item["ok"]]


def prerequisites_ok() -> bool:
    """L'assistant peut avancer dès que les contrôles bloquants passent.

    La clé secrète n'est pas bloquante ici : elle est générée à l'étape 2, et
    l'étape 3 refuse de créer un compte (donc une session) sans elle.
    """
    return not blocking_failures()
