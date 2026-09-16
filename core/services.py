"""Services transverses : quota, purge, sauvegarde, hub éditeur, mises à jour, cron."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.utils import timezone

from core.models import Installation, Intervention, SchoolYear, Setting

# --------------------------------------------------------------------------- #
# Quota
# --------------------------------------------------------------------------- #
def quota_config() -> dict:
    return Setting.data().get("quota", {})


def quota_usage() -> dict:
    """Espace consommé par media/ + base, comparé au quota global."""
    root = Path(settings.MEDIA_ROOT)
    used = 0
    if root.exists():
        for path in root.rglob("*"):
            try:
                if path.is_file():
                    used += path.stat().st_size
            except OSError:
                continue
    db_file = Path(settings.DATABASES["default"].get("NAME", ""))
    if db_file.exists():
        try:
            used += db_file.stat().st_size
        except OSError:
            pass
    total_mb = int(quota_config().get("total_mb", 400) or 400)
    total = total_mb * 1024 * 1024
    pct = int(used * 100 / total) if total else 0
    thresholds = quota_config().get("alerte_pct") or [80, 95]
    return {
        "used": used,
        "total": total,
        "pct": pct,
        "label": "%s / %s Mo" % (round(used / 1048576, 1), total_mb),
        "thresholds": thresholds,
        "max_file_mb": int(quota_config().get("max_file_mb", 10) or 10),
        "versions_kept": int(quota_config().get("versions_kept", 3) or 3),
    }


def quota_alert_level() -> int:
    usage = quota_usage()
    thresholds = sorted(usage["thresholds"], reverse=True)
    for index, threshold in enumerate(thresholds):
        if usage["pct"] >= threshold:
            return len(thresholds) - index
    return 0


def check_quota(size: int = 0) -> tuple[bool, str]:
    usage = quota_usage()
    if usage["used"] + size > usage["total"]:
        return False, (
            "L'espace de stockage est plein (%s Mo) : purgez la corbeille ou relevez la limite."
            % int(usage["total"] / 1048576)
        )
    return True, ""


# --------------------------------------------------------------------------- #
# Purges
# --------------------------------------------------------------------------- #
def purge(what: str, dry_run: bool = False) -> dict:
    """Purge ciblée : versions, photos de ménage, corbeille, e-mails lus, notifications."""
    result = {"quoi": what, "supprimes": 0, "octets": 0}
    if what == "versions":
        from documents.services import purge_old_versions

        result["supprimes"] = purge_old_versions(int(quota_config().get("versions_kept", 3)), dry_run)
    elif what == "photos":
        from chores.services import purge_photos

        result["supprimes"] = purge_photos(dry_run)
    elif what == "trash":
        from documents.services import purge_trash

        result["supprimes"] = purge_trash(dry_run)
    elif what == "emails":
        from mail.services import purge_read_emails

        result["supprimes"] = purge_read_emails(int(quota_config().get("mail_purge_years", 2)), dry_run)
    elif what == "notifications":
        from notifications.services import purge_notifications

        result["supprimes"] = purge_notifications(dry_run)
    elif what == "audit":
        from audit.services import purge_audit

        result["supprimes"] = purge_audit(int(Setting.value("securite", "audit_keep_years", 5)), dry_run)
    else:
        raise ValueError("purge inconnue : %s" % what)
    return result


# --------------------------------------------------------------------------- #
# Sauvegarde / restauration
# --------------------------------------------------------------------------- #
def dump_data() -> str:
    from django.core.management import call_command

    buffer = io.StringIO()
    call_command("dumpdata", "--natural-foreign", "--natural-primary", "-e", "contenttypes",
                 "-e", "sessions.session", stdout=buffer)
    return buffer.getvalue()


def backup(output: str | None = None, with_media: bool = True) -> Path:
    """ZIP = dump JSON + config (mots de passe masqués) + media/."""
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    target = Path(output) if output else Path(settings.BASE_DIR) / "backups" / ("mdl-%s.zip" % stamp)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", dump_data())
        archive.writestr("config/instance.json", json.dumps(_masked_instance(), ensure_ascii=False, indent=2))
        archive.writestr("VERSION", getattr(settings, "VERSION", ""))
        if with_media:
            root = Path(settings.MEDIA_ROOT)
            if root.exists():
                for path in root.rglob("*"):
                    if path.is_file():
                        archive.write(path, "media/%s" % path.relative_to(root))
    return target


def _masked_instance() -> dict:
    path = Path(settings.CONFIG_DIR) / "instance.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for section in ("database", "mail", "security"):
        for key in ("password", "secret_key", "user"):
            if section in data and data[section].get(key):
                data[section][key] = "***"
    return data


def restore(archive: str) -> dict:
    """Restaure un ZIP de sauvegarde (données + media)."""
    from django.core.management import call_command

    path = Path(archive)
    if not path.exists():
        raise FileNotFoundError(archive)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if "data.json" not in names:
            raise ValueError("archive invalide : data.json absent")
        payload = zf.read("data.json").decode("utf-8")
        tmp = Path(settings.BASE_DIR) / "backups" / "restore-%d.json" % timezone.now().timestamp()
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(payload, encoding="utf-8")
        call_command("loaddata", str(tmp), verbosity=0)
        tmp.unlink(missing_ok=True)
        root = Path(settings.MEDIA_ROOT)
        for name in names:
            if name.startswith("media/") and not name.endswith("/"):
                destination = root / Path(name).relative_to("media")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(zf.read(name))
    Setting.flush()
    return {"archive": str(path), "fichiers": len(names)}


# --------------------------------------------------------------------------- #
# Hub éditeur (sortant uniquement)
# --------------------------------------------------------------------------- #
def heartbeat_payload() -> dict:
    """Aucun nom, aucun contenu : uniquement des compteurs."""
    def count(model_path):
        try:
            module, name = model_path.split(".")
            from django.apps import apps

            return apps.get_model(module, name).objects.count()
        except Exception:
            return 0

    return {
        "members": count("accounts.User"),
        "entries": count("finance.Entry"),
        "documents": count("documents.Document"),
        "media_bytes": quota_usage()["used"],
        "version": getattr(settings, "VERSION", ""),
        "python": "%d.%d.%d" % sys.version_info[:3],
        "django": __import__("django").get_version(),
        "db": str(settings.DATABASES["default"].get("ENGINE", "")).split(".")[-1],
    }


def hub_request(endpoint: str, payload: dict, timeout: int = 15) -> dict:
    """Appel HTTP horodaté signé (ID + secret + signature)."""
    import requests

    install = Installation.get()
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    signature = hashlib.sha256(("%s|%s|%s" % (install.install_id, install.secret, body)).encode()).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Install-Id": install.install_id,
        "X-Signature": signature,
        "X-Timestamp": str(int(timezone.now().timestamp())),
    }
    url = "%s/api/%s" % (str(settings.HUB_URL).rstrip("/"), endpoint.strip("/"))
    response = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json() if response.content else {}


def hub_ping() -> dict:
    """Ping horaire : version disponible, actions en attente, compteurs."""
    install = Installation.get()
    result = {"ok": False, "message": ""}
    try:
        data = hub_request("heartbeat/", {"heartbeat": heartbeat_payload(), "install_id": install.install_id})
        install.last_ping_at = timezone.now()
        install.last_error = ""
        install.pending_update = str(data.get("latest_version", "") or "")
        payload_actions = data.get("pending_actions", [])
        _sync_interventions(payload_actions)
        install.save(update_fields=["last_ping_at", "last_error", "pending_update"])
        result = {"ok": True, "message": "contact établi", "data": data}
    except Exception as exc:
        install.last_error = str(exc)[:400]
        install.save(update_fields=["last_error"])
        result = {"ok": False, "message": str(exc)[:200]}
    return result


def _sync_interventions(actions) -> None:
    for item in actions or []:
        code = str(item.get("code", ""))[:32]
        if not code:
            continue
        Intervention.objects.update_or_create(
            code=code,
            defaults={
                "action": str(item.get("action", ""))[:32],
                "target": str(item.get("target", ""))[:254],
                "reason": str(item.get("reason", ""))[:240],
                "token": str(item.get("token", "")),
                "origin": "hub",
                "expires_at": _parse_dt(item.get("expires_at")),
            },
        )


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def apply_intervention(intervention: Intervention, actor=None) -> dict:
    """Applique une intervention bornée : reset_password / disable_2fa / resend_invite."""
    from accounts.services import apply_remote_action

    result = apply_remote_action(intervention.action, intervention.target, actor=actor)
    intervention.status = "applied" if result.get("ok") else "failed"
    intervention.result = json.dumps(result, ensure_ascii=False, default=str)
    intervention.applied_at = timezone.now()
    intervention.applied_by = actor
    intervention.save(update_fields=["status", "result", "applied_at", "applied_by"])
    try:
        from audit.services import log

        log(actor, "devhub.intervention_applied", "devhub", intervention,
            "Intervention technique appliquée : %s" % intervention.action, level="danger")
    except Exception:
        pass
    return result


def revoke_intervention(intervention: Intervention, actor=None) -> None:
    intervention.status = "revoked"
    intervention.revoked_by = actor
    intervention.save(update_fields=["status", "revoked_by"])


# --------------------------------------------------------------------------- #
# Mises à jour
# --------------------------------------------------------------------------- #
def _semver(value: str) -> tuple:
    parts = str(value or "0").lstrip("v").split(".")
    out = []
    for part in parts[:3]:
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits or 0))
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def check_update(force: bool = False) -> dict:
    """Compare les versions sémantiques depuis les Releases GitHub du dépôt."""
    import requests

    hub = Setting.data().get("hub", {})
    if not hub.get("update_check", True) and not force:
        return {"checked": False, "reason": "vérification automatique désactivée"}
    repo = getattr(settings, "GITHUB_REPO", "")
    token = getattr(settings, "GITHUB_TOKEN", "")
    channel = hub.get("update_channel", "stable")
    pinned = hub.get("pinned_version", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    try:
        response = requests.get("https://api.github.com/repos/%s/releases" % repo, headers=headers, timeout=20)
        response.raise_for_status()
        releases = response.json()
    except Exception as exc:
        return {"checked": False, "reason": str(exc)[:200]}
    current = _semver(getattr(settings, "VERSION", "1.0.0"))
    best = None
    for release in releases or []:
        tag = release.get("tag_name", "")
        if release.get("draft") or release.get("prerelease") and channel == "stable":
            continue
        version = _semver(tag)
        if version <= current:
            continue
        if pinned and version > _semver(pinned):
            continue
        if best is None or version > _semver(best["tag"]):
            best = {"tag": tag, "name": release.get("name", tag), "notes": release.get("body", ""),
                    "assets": [{"name": a.get("name"), "url": a.get("browser_download_url"),
                                "size": a.get("size")} for a in release.get("assets", [])]}
    if best is None:
        return {"checked": True, "up_to_date": True, "version": getattr(settings, "VERSION", "")}
    install = Installation.get()
    install.pending_update = best["tag"]
    install.save(update_fields=["pending_update"])
    return {"checked": True, "up_to_date": False, "version": best["tag"], "release": best}


PROTECTED_PATHS = ("config", "media", "db.sqlite3", ".venv", "staticfiles", "backups", ".git")


def apply_update(archive_path: str, expected_sha256: str = "") -> dict:
    """Sauvegarde → vérification SHA-256 → remplacement (rollback possible) → migrate."""
    from django.core.management import call_command

    archive = Path(archive_path)
    if not archive.exists():
        raise FileNotFoundError(archive_path)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if expected_sha256 and digest != expected_sha256.lower():
        raise ValueError("somme SHA-256 différente : archive refusée")
    backup_file = backup()
    rollback_dir = Path(settings.BASE_DIR) / "backups" / ("rollback-%d" % timezone.now().timestamp())
    rollback_dir.mkdir(parents=True, exist_ok=True)
    replaced = []
    try:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                top = Path(name).parts[0] if Path(name).parts else ""
                if top in PROTECTED_PATHS or any(part in PROTECTED_PATHS for part in Path(name).parts):
                    continue
                destination = Path(settings.BASE_DIR) / name
                if destination.exists():
                    slot = rollback_dir / name
                    slot.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, slot)
                    replaced.append(name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(zf.read(name))
        call_command("migrate", "--noinput", verbosity=0)
        call_command("collectstatic", "--noinput", verbosity=0)
    except Exception as exc:
        for name in replaced:  # rollback
            source = rollback_dir / name
            if source.exists():
                shutil.copy2(source, Path(settings.BASE_DIR) / name)
        return {"ok": False, "error": str(exc), "rollback": True, "backup": str(backup_file)}
    return {"ok": True, "backup": str(backup_file), "fichiers": len(replaced),
            "notice": "Redémarrez votre service web dans le panneau alwaysdata."}


# --------------------------------------------------------------------------- #
# Cron
# --------------------------------------------------------------------------- #
def cron_run() -> dict:
    """Orchestrateur appelé par ``manage.py cron:run`` (cron alwaysdata, toutes les heures)."""
    report: dict[str, object] = {"lance_le": timezone.localtime().isoformat(), "etapes": {}}

    def step(name, fn):
        try:
            report["etapes"][name] = fn()
        except Exception as exc:
            report["etapes"][name] = "erreur : %s" % exc

    from mail.services import drain_outbox, send_scheduled

    step("mail_drain", lambda: drain_outbox())
    step("diffusions", lambda: send_scheduled())
    step("invitations", lambda: _invitation_reminders())
    step("campagnes", lambda: _close_campaigns())
    step("menage", lambda: _chores_reminders())
    step("bilan", lambda: _auto_balance())
    step("quota", lambda: quota_alert_level())
    step("purges", lambda: _scheduled_purges())
    if getattr(settings, "HUB_URL", ""):
        step("hub", lambda: hub_ping())
        step("update", lambda: check_update())
    return report


def _invitation_reminders() -> int:
    from accounts.services import remind_invitations

    return remind_invitations()


def _close_campaigns() -> dict:
    out = {}
    try:
        from plannings.services import close_expired_campaigns

        out["salle"] = close_expired_campaigns()
    except Exception:
        out["salle"] = 0
    try:
        from chores.services import close_expired_campaigns as close_chores

        out["menage"] = close_chores()
    except Exception:
        out["menage"] = 0
    return out


def _chores_reminders() -> int:
    try:
        from chores.services import send_reminders

        return send_reminders()
    except Exception:
        return 0


def _auto_balance() -> str:
    from finance.services import should_generate_today, generate_balance

    if not should_generate_today():
        return "hors échéance"
    year = SchoolYear.current()
    if year is None:
        return "aucune année scolaire"
    run = generate_balance(year, auto=True)
    return "généré (%s)" % run.status


def _scheduled_purges() -> dict:
    out = {}
    for what in ("versions", "trash", "notifications"):
        try:
            out[what] = purge(what)["supprimes"]
        except Exception as exc:
            out[what] = "erreur : %s" % exc
    return out


# --------------------------------------------------------------------------- #
# Alertes techniques (tuile dashboard + /sante/)
# --------------------------------------------------------------------------- #
def health_alerts(user=None) -> list[dict]:
    alerts: list[dict] = []
    year = SchoolYear.current()
    if year and year.days_left() <= 45:
        alerts.append({"kind": "année", "level": "warning", "url": "/reglages/annees/",
                       "message": "L'année scolaire %s se termine dans %s jours." % (year.label, year.days_left())})
    if not Setting.value("app", "smtp_tested", False) and not getattr(settings, "MAIL_ENABLED", False):
        alerts.append({"kind": "smtp", "level": "warning", "url": "/reglages/smtp/",
                       "message": "SMTP non testé : les e-mails ne partiront pas."})
    if not (getattr(settings, "VAPID_PUBLIC_KEY", "") and getattr(settings, "VAPID_PRIVATE_KEY", "")):
        try:
            install = Installation.get()
            if not install.public_key_pem:
                raise AssertionError
        except Exception:
            alerts.append({"kind": "vapid", "level": "warning", "url": "/reglages/pwa/",
                           "message": "Clés VAPID absentes : les notifications push sont inactives."})
    try:
        from accounts.models import User
        from core.models import LegalDocument

        charte = LegalDocument.objects.filter(kind="charte", requires_acceptance=True, published=True).first()
        if charte and user is not None and not user.legal_acceptances.filter(document=charte).exists():
            alerts.append({"kind": "charte", "level": "info", "url": "/parametres/charte/",
                           "message": "Vous n'avez pas encore accepté la charte."})
        unsigned = User.objects.filter(status="active").exclude(
            legal_acceptances__document=charte).count() if charte else 0
        if charte and unsigned:
            alerts.append({"kind": "charte", "level": "warning", "url": "/membres/",
                           "message": "%s membres n'ont pas accepté la charte." % unsigned})
    except Exception:
        pass
    if Intervention.pending().exists():
        alerts.append({"kind": "intervention", "level": "danger", "url": "/reglages/interventions/",
                       "message": "Une intervention technique est en attente de validation."})
    usage = quota_usage()
    if usage["pct"] >= 80:
        alerts.append({"kind": "quota", "level": "danger" if usage["pct"] >= 95 else "warning",
                       "url": "/reglages/quotas/",
                       "message": "Espace utilisé à %s %% (%s)." % (usage["pct"], usage["label"])})
    return alerts


def health() -> dict:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    usage = quota_usage()
    return {
        "status": "ok",
        "version": getattr(settings, "VERSION", ""),
        "heure": timezone.localtime().isoformat(),
        "base": str(settings.DATABASES["default"].get("ENGINE", "")).split(".")[-1],
        "disque": usage["label"],
        "mail": bool(getattr(settings, "MAIL_ENABLED", False)),
        "push": bool(getattr(settings, "VAPID_PUBLIC_KEY", "")),
        "alertes": len(health_alerts()),
    }
