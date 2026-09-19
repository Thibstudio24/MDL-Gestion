"""Vues des Réglages de l'association (/reglages/)."""
from __future__ import annotations

import json

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from audit import services as audit
from core import permissions, services, theme
from core.decorators import administrator_required, module_required, reauth_required
from core.forms_settings import (
    BalanceScheduleForm,
    BrandForm,
    ClosureDayForm,
    LegalForm,
    MaintenanceForm,
    PushForm,
    QuotaForm,
    SecurityForm,
    SmtpForm,
    StorageForm,
    TelemetryForm,
    UpdateForm,
    YearForm,
)
from core.models import ClosureDay, Installation, Intervention, LegalDocument, SchoolYear, Setting
from core.rich import render as render_markdown
from core.storage import s3_pret as _s3_pret

# Clés dont la valeur ne doit jamais atteindre le journal d'audit.
_SECRET_KEYS = frozenset({"password", "private_key", "secret", "token", "totp_secret", "secret_key"})


def _safe(payload) -> dict:
    """Renvoie une copie journalisable : les valeurs sensibles sont masquées.

    Le journal d'audit est lisible par tout administrateur et conservé cinq ans ;
    un mot de passe SMTP ou une clé privée VAPID n'ont rien à y faire.
    """
    if not payload:
        return {}
    return {
        key: ("***" if value and key in _SECRET_KEYS else value)
        for key, value in dict(payload).items()
    }


def _save_logo(uploaded, retirer, actuel: str) -> str:
    """Range le logo téléversé dans media/branding/ et renvoie son chemin relatif.

    Renvoie une chaîne vide si le membre demande à retirer le logo, et le
    chemin déjà enregistré quand aucun fichier n'est fourni.
    """
    if retirer:
        _delete_logo(actuel)
        return ""
    # Un FileField non requis renvoie le chemin déjà enregistré (une chaîne)
    # quand rien n'est téléversé : ce n'est pas un nouveau fichier.
    if not uploaded or isinstance(uploaded, str):
        return actuel
    import re as _re
    from pathlib import Path as _Path

    from django.conf import settings as django_settings
    from django.utils.text import get_valid_filename

    cible = _Path(django_settings.MEDIA_ROOT) / "branding"
    cible.mkdir(parents=True, exist_ok=True)
    racine, _, extension = get_valid_filename(uploaded.name).rpartition(".")
    nom = "logo-%s.%s" % (timezone.now().strftime("%Y%m%d%H%M%S"),
                          _re.sub(r"[^A-Za-z0-9]", "", extension)[:5].lower() or "png")
    for ancien in cible.glob("logo-*"):
        ancien.unlink(missing_ok=True)
    with (cible / nom).open("wb") as handle:
        for bloc in uploaded.chunks():
            handle.write(bloc)
    _delete_logo(actuel)
    return "branding/%s" % nom


def _delete_logo(relatif: str) -> None:
    """Supprime l'ancien logo s'il vivait bien dans media/branding/."""
    from pathlib import Path as _Path

    from django.conf import settings as django_settings

    if not relatif or not relatif.startswith("branding/"):
        return
    racine = _Path(django_settings.MEDIA_ROOT).resolve()
    cible = (racine / relatif).resolve()
    if racine in cible.parents and cible.is_file():
        cible.unlink(missing_ok=True)


def _tabs(active: str) -> list[dict]:
    entries = [
        ("brand", "Marque & textes", "settings_brand"),
        ("years", "Années scolaires", "settings_years"),
        ("quotas", "Quotas & purges", "settings_quotas"),
        ("notifications", "Notifications", "settings_notifications"),
        ("smtp", "Envois (SMTP)", "settings_smtp"),
        ("stockage", "Stockage", "settings_storage"),
        ("pwa", "PWA & push", "settings_pwa"),
        ("bilan", "Bilan", "settings_bilan"),
        ("backup", "Sauvegarde", "settings_backup"),
        ("interventions", "Interventions", "settings_interventions"),
        ("maintenance", "Maintenance", "settings_maintenance"),
        ("update", "Mises à jour", "settings_update"),
        ("audit", "Journal & télémétrie", "settings_telemetry"),
    ]
    from django.urls import reverse

    tabs = []
    for key, label, name in entries:
        try:
            url = reverse("settings:%s" % name)
        except Exception:  # onglet non monté : on l'ignore plutôt que d'afficher un lien mort
            continue
        tabs.append({"key": key, "label": label, "url": url, "active": key == active})
    return tabs


@module_required("settings_global")
def brand(request):
    current = Setting.brand()
    form = BrandForm(initial=current)
    if request.method == "POST":
        form = BrandForm(request.POST, request.FILES, initial=current)
        if form.is_valid():
            previous = Setting.brand()
            payload = dict(form.cleaned_data)
            # Le logo se téléverse : on range le fichier dans media/branding/ et
            # on ne conserve en base que son chemin relatif, sérialisable.
            payload.pop("logo_retirer", None)
            payload["logo"] = _save_logo(
                form.cleaned_data.get("logo"),
                form.cleaned_data.get("logo_retirer"),
                previous.get("logo") or "",
            )
            Setting.update_section("branding", payload)
            audit.log(request.user, "settings.brand_updated", "settings", None,
                      "Réglages de marque enregistrés", previous=_safe(previous),
                      current=_safe(payload), request=request)
            messages.success(request, _("Marque enregistrée."))
            return redirect("settings:settings_brand")
    previews = [{"key": key, "label": label, "light": theme.preview_svg(key, "light"),
                 "dark": theme.preview_svg(key, "dark")} for key, label in theme.palette_choices()]
    return render(request, "core/settings/brand.html", {
        "form": form, "page_title": "Réglages de l'association", "tab": "brand", "tabs": _tabs("brand"),
        "previews": previews, "seed_preview": theme.preview_svg("lycee", "light", current.get("couleur_principale")),
    })


@administrator_required
def years(request):
    form = YearForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        year = form.save()
        audit.log(request.user, "settings.year_created", "settings", year,
                  "Année scolaire créée : %s" % year.label, request=request)
        messages.success(request, _("Année « %(label)s » enregistrée.") % {"label": year.label})
        return redirect("settings:settings_years")
    closure_form = ClosureDayForm(request.POST or None)
    return render(request, "core/settings/years.html", {
        "years": SchoolYear.objects.all(),
        "form": form,
        "closure_form": closure_form,
        "closure_days": ClosureDay.objects.select_related("year").order_by("day")[:200],
        "page_title": "Années scolaires", "tab": "years", "tabs": _tabs("years"),
    })


@administrator_required
@require_POST
def year_action(request, pk: int):
    year = get_object_or_404(SchoolYear, pk=pk)
    action = request.POST.get("action")
    if action == "current":
        year.is_current = True
        year.save(update_fields=["is_current"])
        messages.success(request, _("« %(label)s » est maintenant l'année en cours.") % {"label": year.label})
    elif action == "lock":
        if not year.is_locked:
            year.is_locked = True
            year.save(update_fields=["is_locked"])
            audit.log(request.user, "settings.year_locked", "settings", year,
                      "Année clôturée (lecture seule) : %s" % year.label, level="warn", request=request)
            messages.success(request, _("Année clôturée : lecture seule."))
    elif action == "unlock":
        year.is_locked = False
        year.save(update_fields=["is_locked"])
        audit.log(request.user, "settings.year_unlocked", "settings", year,
                  "Année rouverte : %s" % year.label, level="warn", request=request)
        messages.warning(request, _("Année rouverte."))
    elif action == "delete" and not year.is_current:
        year.delete()
        messages.success(request, _("Année supprimée."))
    return redirect("settings:settings_years")


@administrator_required
@require_POST
def year_closure_add(request, pk: int):
    year = get_object_or_404(SchoolYear, pk=pk)
    form = ClosureDayForm(request.POST)
    if form.is_valid():
        day = form.save(commit=False)
        day.year = year
        day.save()
        messages.success(request, _("Jour de fermeture ajouté."))
    return redirect("settings:settings_years")


@administrator_required
@require_POST
def year_closure_delete(request, pk: int):
    ClosureDay.objects.filter(pk=pk).delete()
    messages.success(request, _("Jour de fermeture retiré."))
    return redirect("settings:settings_years")


@administrator_required
def quotas(request):
    quota = Setting.data().get("quota", {})
    form = QuotaForm(request.POST or None, initial=quota)
    usage = services.quota_usage()
    if request.method == "POST":
        form = QuotaForm(request.POST)
        if form.is_valid():
            Setting.update_section("quota", form.cleaned_data)
            audit.log(request.user, "settings.quota_updated", "settings", None,
                      "Quotas et purges enregistrés", previous=_safe(quota),
                      current=_safe(form.cleaned_data), request=request)
            messages.success(request, _("Quotas enregistrés."))
            return redirect("settings:settings_quotas")
    purges = {}
    if request.method == "POST" and request.POST.get("purge"):
        what = request.POST.get("purge")
        try:
            purges[what] = services.purge(what)["supprimes"]
            messages.success(request, _("Purge « %(what)s » : %(n)s éléments supprimés.") % {"what": what, "n": purges[what]})
        except Exception as exc:
            messages.error(request, _("Purge impossible : %(erreur)s") % {"erreur": exc})
        return redirect("settings:settings_quotas")
    return render(request, "core/settings/quotas.html", {
        "form": form, "usage": usage, "page_title": "Quotas & purges", "tab": "quotas", "tabs": _tabs("quotas"),
    })


@administrator_required
def security_settings(request):
    data = Setting.data().get("securite", {})
    form = SecurityForm(request.POST or None, initial=data)
    if request.method == "POST" and form.is_valid():
        Setting.update_section("securite", form.cleaned_data)
        audit.log(request.user, "settings.security_updated", "settings", None,
                  "Réglages de sécurité enregistrés", previous=_safe(data),
                  current=_safe(form.cleaned_data), level="warn", request=request)
        messages.success(request, _("Réglages de sécurité enregistrés."))
        return redirect("settings:settings_security")
    return render(request, "core/settings/security.html", {
        "form": form, "page_title": "Sécurité", "tab": "quotas", "tabs": _tabs("quotas"),
    })


@module_required("settings_global")
def notifications(request):
    from notifications.services import EVENTS, matrix_for_admin, save_matrix

    matrix = matrix_for_admin()
    if request.method == "POST":
        payload = {}
        for key, value in request.POST.items():
            if key.startswith("evt-"):
                _kind, channel = key[4:].rsplit("-", 1)
                payload.setdefault(_kind, {})[channel] = value
        save_matrix(payload)
        audit.log(request.user, "settings.matrix_updated", "settings", None,
                  "Matrice de notifications enregistrée", previous=_safe(matrix),
                  current=_safe(payload), request=request)
        messages.success(request, _("Matrice de notifications enregistrée."))
        return redirect("settings:settings_notifications")
    return render(request, "core/settings/notifications.html", {
        "events": EVENTS, "matrix": matrix, "page_title": "Notifications",
        "tab": "notifications", "tabs": _tabs("notifications"),
    })


@administrator_required
def smtp(request):
    data = Setting.data().get("mail", {})
    initial = dict(data)
    initial["mail_from"] = data.get("from", "")
    form = SmtpForm(request.POST or None, initial=initial)
    if request.method == "POST":
        form = SmtpForm(request.POST)
        if form.is_valid():
            payload = dict(form.cleaned_data)
            payload["from"] = payload.pop("mail_from", "")
            mot_de_passe = payload.get("password") or data.get("password") or ""
            if not payload.get("password"):
                payload.pop("password", None)
            Setting.update_section("mail", payload)
            _apply_mail_settings(payload, mot_de_passe)
            audit.log(request.user, "settings.smtp_updated", "settings", None,
                      "Réglages SMTP enregistrés", previous=_safe(data), current=_safe(payload),
                      level="warn", request=request)
            messages.success(request, _("Réglages SMTP enregistrés et appliqués immédiatement."))
            return redirect("settings:settings_smtp")
    return render(request, "core/settings/smtp.html", {
        "form": form, "page_title": "Envois (SMTP)", "tab": "smtp", "tabs": _tabs("smtp"),
        "queue": _outbox_preview(),
        "masked": "***" if data.get("password") else "",
    })


@administrator_required
def storage(request):
    """Choix du stockage : disque du serveur ou fournisseur tiers compatible S3."""
    data = Setting.data().get("stockage", {})
    form = StorageForm(request.POST or None, initial={**data, "secret_key": ""})
    if request.method == "POST":
        form = StorageForm(request.POST)
        if form.is_valid():
            payload = dict(form.cleaned_data)
            if not payload.get("secret_key"):
                payload["secret_key"] = data.get("secret_key", "")
            if payload.get("provider") == "local":
                payload = {**payload, "endpoint": "", "bucket": "", "access_key": "",
                           "secret_key": ""}
            Setting.update_section("stockage", payload)
            audit.log(request.user, "settings.storage_updated", "settings", None,
                      "Réglage de stockage enregistré : %s" % payload.get("provider"),
                      previous=_safe(data), current=_safe(payload), level="warn", request=request)
            messages.success(request, _("Réglage de stockage enregistré."))
            return redirect("settings:settings_storage")
    return render(request, "core/settings/stockage.html", {
        "form": form, "page_title": "Stockage des fichiers", "tab": "stockage",
        "tabs": _tabs("stockage"), "cfg": data,
        "masque": "•••" if data.get("secret_key") else "",
        "s3_pret": _s3_pret(data),
    })


@administrator_required
@require_POST
def storage_test(request):
    """Teste la connexion au fournisseur S3 enregistré : dépôt, lecture, retrait."""
    from core.storage import S3Error, s3_pret, s3_request

    cfg = Setting.data().get("stockage", {})
    if not s3_pret(cfg):
        messages.error(request, _("Le fournisseur tiers n'est pas complètement configuré."))
        return redirect("settings:settings_storage")
    objet = "mdl-test/connexion.txt"
    try:
        s3_request(cfg, "PUT", objet, payload=b"test MDL Gestion")
        corps = s3_request(cfg, "GET", objet)
        s3_request(cfg, "DELETE", objet)
    except S3Error as exc:
        messages.error(request, _("Échec de la connexion : %(erreur)s") % {"erreur": exc})
        return redirect("settings:settings_storage")
    if corps == b"test MDL Gestion":
        messages.success(request, _("Connexion réussie : dépôt, lecture et retrait du fichier "
                                    "de test ont fonctionné."))
    else:
        messages.warning(request, _("Connexion établie mais le fichier lu diffère du fichier déposé."))
    return redirect("settings:settings_storage")


def _apply_mail_settings(payload: dict, mot_de_passe: str = "") -> None:
    """Écrit la section mail dans config/instance.json et l'applique au processus.

    L'envoi (drain_outbox, send_test_email) lit settings.EMAIL_*, valeurs chargées
    depuis config/instance.json au démarrage. Enregistrer le formulaire seulement
    en base laissait donc l'envoi sur « SMTP désactivé » quoi qu'on saisisse à
    l'écran. On écrit le fichier (droits 600, survit au redémarrage) et on
    applique les valeurs au processus courant : le test d'envoi fonctionne sans
    redémarrer. Les variables MDL_* restent prioritaires au prochain démarrage.
    """
    from config import settings as instance

    config = instance.read_instance()
    mail = dict(config.get("mail") or {})
    mail.update({cle: val for cle, val in payload.items() if cle != "password"})
    if mot_de_passe:
        mail["password"] = mot_de_passe
    config["mail"] = mail
    instance.write_instance(config)
    settings.MAIL_ENABLED = bool(mail.get("enabled"))
    settings.EMAIL_HOST = mail.get("host") or "localhost"
    settings.EMAIL_PORT = int(mail.get("port") or 587)
    settings.EMAIL_HOST_USER = mail.get("user") or ""
    settings.EMAIL_HOST_PASSWORD = mail.get("password") or ""
    settings.EMAIL_USE_SSL = bool(mail.get("use_ssl"))
    settings.EMAIL_USE_TLS = bool(mail.get("use_tls"))
    if mail.get("from"):
        settings.DEFAULT_FROM_EMAIL = mail["from"]
        settings.SERVER_EMAIL = mail["from"]
    if mail.get("rate_per_minute"):
        settings.MAIL_RATE_PER_MINUTE = int(mail["rate_per_minute"])
    if not getattr(settings, "TESTING", False):
        settings.EMAIL_BACKEND = (
            "django.core.mail.backends.smtp.EmailBackend"
            if settings.MAIL_ENABLED and not settings.DEBUG
            else "django.core.mail.backends.console.EmailBackend"
        )


def _outbox_preview():
    try:
        from mail.models import Outbox

        return Outbox.objects.order_by("-created_at")[:15]
    except Exception:
        return []


@administrator_required
@require_POST
def smtp_test(request):
    target = request.POST.get("email", "").strip()
    if not target:
        messages.error(request, _("Saisissez une adresse de destination."))
        return redirect("settings:settings_smtp")
    try:
        from mail.services import send_test_email

        send_test_email(target)
        Setting.set("app", "smtp_tested", True)
        messages.success(request, _("E-mail de test envoyé à %(email)s.") % {"email": target})
    except Exception as exc:
        messages.error(request, _("Envoi impossible : %(erreur)s") % {"erreur": exc})
    return redirect("settings:settings_smtp")


@administrator_required
@require_POST
def smtp_drain(request):
    """Vide la file d'attente SMTP immédiatement, sans attendre le cron."""
    from mail.services import drain_outbox

    rapport = drain_outbox()
    resume = ", ".join("%s : %s" % (cle, val) for cle, val in rapport.items())
    audit.log(request.user, "mail.outbox_drained", "mail", None,
              "File SMTP vidée manuellement (%s)" % resume, request=request)
    messages.success(request, _("File d'attente traitée (%(resume)s).") % {"resume": resume})
    return redirect("settings:settings_smtp")


@module_required("settings_global", edit=False)
def pwa(request):
    data = Setting.data().get("push", {})
    install = Installation.get()
    form = PushForm(request.POST or None, initial={
        "enabled": bool(getattr(settings, "PUSH_ENABLED", True)),
        "public_key": data.get("public_key", ""),
        "private_key": data.get("private_key", ""),
        "claims_email": data.get("claims_email", ""),
    })
    if request.method == "POST" and permissions.can_edit(request.user, "settings_global"):
        form = PushForm(request.POST)
        if form.is_valid():
            Setting.update_section("push", form.cleaned_data)
            audit.log(request.user, "settings.push_updated", "settings", None,
                      "Réglages push enregistrés", previous=_safe(data),
                      current=_safe(form.cleaned_data), request=request)
            messages.success(request, _("Réglages push enregistrés."))
            return redirect("settings:settings_pwa")
    devices = []
    try:
        from notifications.models import PushDevice

        devices = PushDevice.objects.select_related("user").order_by("-created_at")[:30]
    except Exception:
        devices = []
    return render(request, "core/settings/pwa.html", {
        "form": form, "devices": devices, "install": install,
        "page_title": "PWA & push", "tab": "pwa", "tabs": _tabs("pwa"),
        "vapid_missing": not (getattr(settings, "VAPID_PUBLIC_KEY", "") or data.get("public_key")),
    })


@administrator_required
@require_POST
def pwa_generate_keys(request):
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid02, b64urlencode  # pywebpush fournit py_vapid

    vapid = Vapid02()
    vapid.generate_keys()
    # Format Web Push (RFC 8292) : clé publique = point non compressé X9.62
    # (65 octets), clé privée = entier brut de 32 octets, les deux en base64url.
    # C'est ce qu'attend le navigateur pour applicationServerKey et ce que
    # pywebpush relit via Vapid.from_string().
    public = b64urlencode(vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    private = b64urlencode(vapid.private_key.private_numbers().private_value.to_bytes(32, "big"))
    Setting.update_section("push", {"public_key": public, "private_key": private, "enabled": True,
                                    "claims_email": Setting.brand().get("contact") or "mdl@localhost"})
    messages.success(request, _("Clés VAPID générées. Redémarrez le service web, puis réabonnez les appareils."))
    return redirect("settings:settings_pwa")


@administrator_required
def bilan_settings(request):
    data = Setting.data().get("bilan", {})
    form = BalanceScheduleForm(request.POST or None, initial=data)
    if request.method == "POST" and form.is_valid():
        payload = dict(form.cleaned_data)
        payload["heure"] = payload["heure"].strftime("%H:%M") if hasattr(payload["heure"], "strftime") else str(payload["heure"])
        # Non négociable : le bilan va aux ayants droit du module Trésorerie.
        payload["destinataires"] = "module"
        Setting.update_section("bilan", payload)
        messages.success(request, _("Planification du bilan enregistrée."))
        return redirect("settings:settings_bilan")
    runs = []
    try:
        from finance.models import BalanceRun

        runs = BalanceRun.objects.order_by("-generated_at")[:10]
    except Exception:
        runs = []
    return render(request, "core/settings/bilan.html", {
        "form": form, "runs": runs, "page_title": "Bilan", "tab": "bilan", "tabs": _tabs("bilan"),
    })


@module_required("backup")
def backup_view(request):
    backups = []
    directory = settings.BASE_DIR / "backups"
    if directory.exists():
        for path in sorted(directory.glob("*.zip"), reverse=True)[:20]:
            stat = path.stat()
            backups.append({"name": path.name, "size": stat.st_size, "date": stat.st_mtime})
    return render(request, "core/settings/backup.html", {
        "backups": backups, "page_title": "Sauvegarde & restauration", "tab": "backup", "tabs": _tabs("backup"),
        "usage": services.quota_usage(),
    })


@module_required("backup", edit=True)
@require_POST
def backup_delete(request):
    """Supprime une archive du serveur. Le nom vient du formulaire, jamais de l'URL."""
    name = request.POST.get("archive") or ""
    directory = (settings.BASE_DIR / "backups").resolve()
    target = (directory / name).resolve() if name else None
    # Le nom saisi ne doit pas permettre de sortir du dossier de sauvegardes.
    if target is None or directory not in target.parents or not target.is_file():
        messages.error(request, _("Sauvegarde introuvable."))
        return redirect("settings:settings_backup")
    target.unlink(missing_ok=True)
    audit.log(request.user, "settings.backup_deleted", "settings", None,
              "Sauvegarde supprimée : %s" % name, level="warn", request=request)
    messages.success(request, _("Sauvegarde « %(name)s » supprimée.") % {"name": name})
    return redirect("settings:settings_backup")


@module_required("backup", edit=True)
@require_POST
def backup_create(request):
    try:
        path = services.backup(with_media=request.POST.get("media") != "0")
        audit.log(request.user, "settings.backup_created", "settings", None,
                  "Sauvegarde créée : %s (%d octets)" % (path.name, path.stat().st_size),
                  request=request)
        messages.success(request, _("Sauvegarde créée : %(fichier)s") % {"fichier": path.name})
    except Exception as exc:
        messages.error(request, _("Sauvegarde impossible : %(erreur)s") % {"erreur": exc})
    return redirect("settings:settings_backup")


@reauth_required
@require_POST
def backup_restore(request):
    name = request.POST.get("archive", "")
    path = settings.BASE_DIR / "backups" / name
    if not name or not str(path).startswith(str(settings.BASE_DIR / "backups")):
        messages.error(request, _("Archive introuvable."))
        return redirect("settings:settings_backup")
    try:
        result = services.restore(str(path))
        audit.log(request.user, "settings.backup_restored", "settings", None,
                  "Sauvegarde restaurée : %s (%s fichiers)" % (name, result["fichiers"]),
                  level="danger", request=request)
        messages.success(request, _("Sauvegarde restaurée (%(n)s fichiers). Redémarrez le service web.")
                         % {"n": result["fichiers"]})
    except Exception as exc:
        messages.error(request, _("Restauration impossible : %(erreur)s") % {"erreur": exc})
    return redirect("settings:settings_backup")


@administrator_required
@reauth_required
@require_POST
def reset_site(request):
    """Réinitialise complètement le site à l'état neuf : retour à l'assistant.

    Efface la base (comptes compris), le contenu de media/ et de backups/,
    puis repasse l'installation en mode « non installé ». Seul un
    administrateur ré-authentifié peut le faire, confirmation tapée.
    """
    import shutil
    from pathlib import Path

    from django.contrib.auth import logout
    from django.core.management import call_command

    from config import settings as instance

    if (request.POST.get("confirmation") or "").strip() != "REINITIALISER":
        messages.error(request, _("Saisissez « REINITIALISER » pour confirmer."))
        return redirect("settings:settings_backup")
    acteur = request.user
    courriel = getattr(acteur, "email", "")
    # Le stockage tiers est lu AVANT le vidage de la base (le réglage y est rangé).
    from core.storage import purge_all, s3_pret, stockage_cfg

    cfg_stockage = stockage_cfg()
    audit.log(acteur, "settings.site_reset", "settings", None,
              "Réinitialisation complète du site demandée", level="danger", request=request)
    for dossier in (Path(settings.MEDIA_ROOT), Path(settings.BACKUP_DIR)):
        if dossier.exists():
            for enfant in dossier.iterdir():
                try:
                    if enfant.is_dir() and not enfant.is_symlink():
                        shutil.rmtree(enfant, ignore_errors=True)
                    else:
                        enfant.unlink(missing_ok=True)
                except OSError:
                    pass
    config = instance.read_instance()
    meta = dict(config.get("meta") or {})
    meta["installed"] = False
    meta.pop("installed_at", None)
    config["meta"] = meta
    instance.write_instance(config)
    # Base de données : toutes les tables sont vidées (comptes, documents,
    # écritures, réglages compris), puis le fichier SQLite est reconstruit
    # physiquement (VACUUM) pour ne laisser aucune page de données anciennes.
    call_command("flush", "--noinput", verbosity=0)
    from django.db import connections

    if connections["default"].vendor == "sqlite":
        try:
            with connections["default"].cursor() as curseur:
                curseur.execute("VACUUM")
        except Exception:  # VACUUM refuse de tourner dans une transaction (tests)
            pass
    # Fichiers chez un fournisseur tiers : le bucket est purgé aussi.
    objets_purges = 0
    if s3_pret(cfg_stockage):
        try:
            objets_purges = purge_all(cfg_stockage)
        except Exception as exc:  # la réinitialisation ne doit pas échouer à moitié
            objets_purges = -1
            audit.log(None, "settings.site_reset", "settings", None,
                      "Purge du bucket impossible (par %s) : %s" % (courriel, exc),
                      level="danger", request=request)
    # Après le flush, le compte n'existe plus en base : on journalise sans FK,
    # l'identité reste dans le libellé.
    audit.log(None, "settings.site_reset", "settings", None,
              "Site réinitialisé par %s : base vidée%s, fichiers locaux et sauvegardes effacés%s."
              % (courriel,
                 ", fichier SQLite reconstruit" if connections["default"].vendor == "sqlite" else "",
                 ", bucket purgé (%d objet(s))" % objets_purges if objets_purges >= 0
                 else ", purge du bucket en échec"),
              level="danger", request=request)
    logout(request)
    return redirect("/installation/")


@module_required("settings_global")
def interventions(request):
    return render(request, "core/settings/interventions.html", {
        "items": Intervention.objects.order_by("-created_at")[:60],
        "pending": Intervention.pending(),
        "install": Installation.get(),
        "page_title": "Interventions techniques", "tab": "interventions", "tabs": _tabs("interventions"),
    })


@administrator_required
@require_POST
def intervention_action(request, pk: int):
    intervention = get_object_or_404(Intervention, pk=pk)
    action = request.POST.get("action")
    if action == "apply":
        result = services.apply_intervention(intervention, actor=request.user)
        if result.get("ok"):
            messages.success(request, _("Intervention appliquée : %(detail)s") % {"detail": result.get("message", "")})
        else:
            messages.error(request, _("Échec : %(erreur)s") % {"erreur": result.get("error", "?")})
    elif action == "revoke":
        services.revoke_intervention(intervention, actor=request.user)
        messages.success(request, _("Intervention révoquée."))
    return redirect("settings:settings_interventions")


@administrator_required
def maintenance(request):
    app = Setting.data().get("app", {})
    form = MaintenanceForm(request.POST or None, initial={
        "maintenance": app.get("maintenance", False),
        "maintenance_message": app.get("maintenance_message", ""),
        "exclus_maintenance": ", ".join(app.get("exclus_maintenance") or []),
    })
    if request.method == "POST" and form.is_valid():
        payload = dict(form.cleaned_data)
        payload["exclus_maintenance"] = [item.strip() for item in payload["exclus_maintenance"].split(",") if item.strip()]
        Setting.update_section("app", payload)
        audit.log(request.user, "settings.maintenance", "settings", None,
                  "Mode maintenance : %s" % ("activé" if payload.get("maintenance") else "désactivé"),
                  previous=_safe(app), current=_safe(payload), level="warn", request=request)
        messages.success(request, _("Mode maintenance mis à jour."))
        return redirect("settings:settings_maintenance")
    return render(request, "core/settings/maintenance.html", {
        "form": form, "page_title": "Maintenance", "tab": "maintenance", "tabs": _tabs("maintenance"),
    })


@module_required("settings_global")
def update(request):
    hub = Setting.data().get("hub", {})
    form = UpdateForm(request.POST or None, initial=hub)
    result = None
    if request.method == "POST":
        if request.POST.get("check"):
            result = services.check_update(force=True)
            messages.info(request, _("Vérification : %(detail)s") % {"detail": json.dumps(result, ensure_ascii=False, default=str)[:300]})
            return redirect("settings:settings_update")
        form = UpdateForm(request.POST)
        if form.is_valid():
            Setting.update_section("hub", form.cleaned_data)
            audit.log(request.user, "settings.update_applied", "settings", None,
                      "Réglages de mise à jour enregistrés", previous=_safe(hub),
                      current=_safe(form.cleaned_data), request=request)
            messages.success(request, _("Réglages de mise à jour enregistrés."))
            return redirect("settings:settings_update")
    return render(request, "core/settings/update.html", {
        "form": form, "result": result, "install": Installation.get(),
        "page_title": "Mises à jour", "tab": "update", "tabs": _tabs("update"),
    })


@administrator_required
def telemetry(request):
    hub = Setting.data().get("hub", {})
    form = TelemetryForm(request.POST or None, initial=hub)
    if request.method == "POST":
        if request.POST.get("ping"):
            outcome = services.hub_ping()
            audit.log(request.user, "devhub.ping", "devhub", None,
                      "Ping du canal éditeur : %s" % outcome["message"], request=request)
            messages.info(request, _("Ping hub : %(message)s") % {"message": outcome["message"]})
            return redirect("settings:settings_telemetry")
        form = TelemetryForm(request.POST)
        if form.is_valid():
            Setting.update_section("hub", form.cleaned_data)
            messages.success(request, _("Réglages du canal éditeur enregistrés."))
            return redirect("settings:settings_telemetry")
    return render(request, "core/settings/telemetry.html", {
        "form": form, "install": Installation.get(), "payload": services.heartbeat_payload(),
        "page_title": "Journal & télémétrie", "tab": "audit", "tabs": _tabs("audit"),
    })


@module_required("settings_global")
def texts(request):
    documents = LegalDocument.objects.all()
    return render(request, "core/settings/texts.html", {
        "documents": documents, "page_title": "Textes légaux", "tab": "brand", "tabs": _tabs("brand"),
        "previews": {doc.slug: render_markdown(doc.body)[:400] for doc in documents},
    })


@administrator_required
@require_POST
def texts_generate(request):
    """Crée les textes légaux manquants (RGPD, charte, mentions, règlement)."""
    from core.legal_texts import ensure_legal_texts

    created = ensure_legal_texts(request.user)
    if created:
        audit.log(request.user, "settings.legal_updated", "settings", None,
                  "%d texte(s) légaux par défaut créé(s)" % created, request=request)
        messages.success(request, _("%(n)s texte(s) créé(s). Relisez-les et adaptez-les : "
                                    "ils engagent l'association.") % {"n": created})
    else:
        messages.info(request, _("Tous les textes par défaut existent déjà."))
    return redirect("settings:settings_texts")


@administrator_required
def text_edit(request, slug: str):
    document = get_object_or_404(LegalDocument, slug=slug)
    form = LegalForm(request.POST or None, instance=document)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.updated_by = request.user
        saved.save()
        audit.log(request.user, "settings.legal_updated", "settings", saved,
                  "Texte légal mis à jour : %s (version %s)" % (saved.title, saved.version),
                  request=request)
        messages.success(request, _("« %(titre)s » mis à jour (version %(v)s).")
                         % {"titre": saved.title, "v": saved.version})
        return redirect("settings:settings_text", slug=slug)
    return render(request, "core/settings/text_edit.html", {
        "form": form, "document": document, "page_title": document.title,
        "tab": "brand", "tabs": _tabs("brand"),
    })
