"""Page Settings du membre (/parametres/) : 6 onglets + Charte & mentions."""
from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts import services, twofa
from accounts.forms import (
    AnonymizeForm, AppearanceForm, EmailChangeForm, PasswordChangeForm, ProfileForm, QuietHoursForm,
)
from accounts.models import AccountSession, LoginAttempt, Role
from audit.services import log
from core import permissions, theme
from core.decorators import reauth_required
from core.export import json_download, user_export
from core.models import LegalDocument, Setting
from core.rich import render as render_markdown

TABS = [
    ("profil", "Profil", "settings_me:settings_profile"),
    ("apparence", "Apparence", "settings_me:settings_appearance"),
    ("notifications", "Notifications & e-mails", "settings_me:settings_notifications_me"),
    ("securite", "Sécurité", "settings_me:settings_security"),
    ("application", "Application (PWA)", "settings_me:settings_application"),
    ("donnees", "Mes données", "settings_me:settings_data"),
    ("charte", "Charte & mentions", "settings_me:settings_charte"),
]


def _tabs(active: str) -> list[dict]:
    from django.urls import reverse

    return [{"key": key, "label": label, "url": reverse(name), "active": key == active} for key, label, name in TABS]


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    email_form = EmailChangeForm(request.POST or None) if request.POST.get("email") else EmailChangeForm()
    if request.method == "POST" and form.is_valid() and "email" not in request.POST:
        form.save()
        messages.success(request, _("Profil enregistré."))
        return redirect("settings_me:settings_profile")
    if request.method == "POST" and request.POST.get("email") and email_form.is_valid():
        if not request.user.check_password(email_form.cleaned_data["password"]):
            email_form.add_error("password", _("Mot de passe incorrect."))
        else:
            new_email = email_form.cleaned_data["email"].strip().lower()
            if User_exists(new_email, request.user):
                email_form.add_error("email", _("Cette adresse est déjà utilisée."))
            else:
                old = request.user.email
                request.user.email = new_email
                request.user.save(update_fields=["email", "updated_at"])
                log(request.user, "member.updated", "members", request.user,
                    "Adresse e-mail de connexion modifiée", previous={"email": old},
                    current={"email": new_email}, level="warn", request=request)
                try:
                    from mail.services import queue_email

                    for address in {old, new_email}:
                        queue_email(to_email=address, recipient_user=request.user,
                                    subject="Votre adresse de connexion a changé",
                                    text_body="La nouvelle adresse de connexion du compte %s est %s." % (old, new_email),
                                    kind="security", urgent=True)
                except Exception:
                    pass
                messages.success(request, _("Adresse mise à jour : un e-mail de confirmation part sur les deux boîtes."))
                return redirect("settings_me:settings_profile")
    return render(request, "accounts/settings/profile.html", {
        "form": form, "email_form": email_form, "tabs": _tabs("profil"), "tab": "profil",
        "page_title": "Mon profil",
    })


def User_exists(email: str, exclude) -> bool:
    from accounts.models import User

    return User.objects.filter(email__iexact=email).exclude(pk=exclude.pk).exists()


@login_required
def appearance(request):
    forced = Setting.forced_theme()
    prefs = dict(request.user.prefs or {})
    form = AppearanceForm(request.POST or None, initial={
        "palette": prefs.get("palette", "ardoise"), "mode": prefs.get("mode", "light"),
        "density": prefs.get("density", "confort"),
    })
    if request.method == "POST" and form.is_valid() and not (forced.get("palette") or forced.get("mode")):
        prefs.update({
            "palette": form.cleaned_data["palette"], "mode": form.cleaned_data["mode"],
            "density": form.cleaned_data["density"],
        })
        request.user.prefs = prefs
        request.user.save(update_fields=["prefs", "updated_at"])
        messages.success(request, _("Apparence enregistrée."))
        return redirect("settings_me:settings_appearance")
    previews = [{"key": key, "label": label, "svg": theme.preview_svg(key, forced.get("mode") or prefs.get("mode", "light")),
                 "active": (forced.get("palette") or prefs.get("palette", "ardoise")) == key}
                for key, label in theme.palette_choices()]
    return render(request, "accounts/settings/appearance.html", {
        "form": form, "previews": previews, "forced": forced, "tabs": _tabs("apparence"), "tab": "apparence",
        "page_title": "Apparence",
    })


@login_required
def notifications_me(request):
    from notifications.services import EVENTS, matrix_for_user, save_user_matrix

    user = request.user
    matrix = matrix_for_user(user)
    quiet = QuietHoursForm(request.POST or None, initial=user.quiet_hours)
    if request.method == "POST":
        payload = {}
        for key in request.POST:
            if key.startswith("evt-"):
                kind, channel = key[4:].rsplit("-", 1)
                payload.setdefault(kind, {})[channel] = True
        for event in EVENTS:
            payload.setdefault(event["key"], {})
            if event["mandatory"]:
                payload[event["key"]]["inapp"] = True
        save_user_matrix(user, payload)
        if quiet.is_valid():
            prefs = dict(user.prefs or {})
            prefs["quiet_hours"] = {"actif": bool(quiet.cleaned_data["actif"]),
                                    "debut": quiet.cleaned_data["debut"], "fin": quiet.cleaned_data["fin"]}
            prefs["receive_personal_email"] = request.POST.get("receive_email") == "on"
            user.prefs = prefs
            user.save(update_fields=["prefs", "updated_at"])
        messages.success(request, _("Préférences enregistrées."))
        return redirect("settings_me:settings_notifications_me")
    devices = []
    try:
        from notifications.models import PushDevice

        devices = PushDevice.objects.filter(user=user).order_by("-created_at")
    except Exception:
        devices = []
    return render(request, "accounts/settings/notifications.html", {
        "events": EVENTS, "matrix": matrix, "quiet_form": quiet, "devices": devices,
        "user": user, "tabs": _tabs("notifications"), "tab": "notifications", "page_title": "Notifications & e-mails",
    })


@login_required
def security(request):
    user = request.user
    password_form = PasswordChangeForm(request.POST or None)
    if request.method == "POST" and password_form.is_valid():
        if not user.check_password(password_form.cleaned_data["old_password"]):
            password_form.add_error("old_password", _("Mot de passe actuel incorrect."))
        else:
            new_password = password_form.cleaned_data["new_password1"]
            try:
                validate_password(new_password, user)
            except ValidationError as exc:
                for message in exc.messages:
                    password_form.add_error("new_password1", message)
            else:
                user.set_password(new_password)
                user.must_change_password = False
                user.save()
                update_session_auth_hash(request, user)
                log(user, "auth.password_changed", "members", user, "Mot de passe modifié", level="warn", request=request)
                try:
                    from mail.services import queue_email

                    queue_email(to_email=user.email, recipient_user=user, subject="Un mot de passe a été changé",
                                text_body="Le mot de passe de votre compte %s vient d'être modifié." % user.email,
                                kind="security", urgent=True)
                except Exception:
                    pass
                messages.success(request, _("Mot de passe mis à jour."))
                return redirect("settings_me:settings_security")
    sessions = AccountSession.objects.filter(user=user, revoked_at__isnull=True).order_by("-last_seen")[:12]
    attempts = LoginAttempt.objects.filter(email__iexact=user.email).order_by("-at")[:12]
    return render(request, "accounts/settings/security.html", {
        "password_form": password_form, "sessions": sessions, "attempts": attempts,
        "twofa": user.two_factor_on, "codes_left": twofa.recovery_codes_left(user),
        "current_session": request.session.session_key,
        "tabs": _tabs("securite"), "tab": "securite", "page_title": "Sécurité",
    })


@login_required
@require_POST
def session_revoke(request, pk: int):
    session = get_object_or_404(AccountSession, pk=pk, user=request.user)
    services.revoke_session(request.user, session.session_key)
    messages.success(request, _("Session révoquée."))
    return redirect("settings_me:settings_security")


@login_required
@require_POST
def sessions_revoke_all(request):
    count = services.revoke_all_sessions(request.user, keep=request.session.session_key)
    messages.success(request, _("%(n)s sessions fermées.") % {"n": count})
    return redirect("settings_me:settings_security")


@login_required
def application(request):
    devices = []
    try:
        from notifications.models import PushDevice

        devices = PushDevice.objects.filter(user=request.user)
    except Exception:
        devices = []
    from django.conf import settings as django_settings

    return render(request, "accounts/settings/application.html", {
        "devices": devices, "tabs": _tabs("application"), "tab": "application",
        "push_ready": bool(getattr(django_settings, "VAPID_PUBLIC_KEY", "")
                           or Setting.value("push", "public_key", "")),
        "page_title": "Application (PWA)",
    })


@login_required
def data(request):
    form = AnonymizeForm(request.POST or None)
    preview = None
    if request.method == "POST" and request.POST.get("preview"):
        preview = user_export(request.user)
    return render(request, "accounts/settings/data.html", {
        "form": form, "preview": json.dumps(preview, ensure_ascii=False, indent=2, default=str)[:4000] if preview else "",
        "acceptances": request.user.legal_acceptances.select_related("document").all(),
        "tabs": _tabs("donnees"), "tab": "donnees", "page_title": "Mes données",
    })


@login_required
def data_export(request):
    payload = user_export(request.user)
    log(request.user, "member.exported", "members", request.user, "Export RGPD téléchargé par le membre", request=request)
    return json_download("mes-donnees-%s.json" % timezone.localdate().strftime("%Y%m%d"), payload)


@reauth_required
@login_required
@require_POST
def anonymize(request):
    form = AnonymizeForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Confirmation invalide."))
        return redirect("settings_me:settings_data")
    expected = (request.user.last_name or request.user.email)[:3].lower()
    if form.cleaned_data["confirmation"].strip().lower() != expected:
        messages.error(request, _("Saisissez exactement les 3 premières lettres de votre nom (%(letters)s).")
                       % {"letters": expected})
        return redirect("settings_me:settings_data")
    user = request.user
    log(user, "member.anonymized", "members", user, "Compte anonymisé à la demande du membre", level="danger", request=request)
    services.revoke_all_sessions(user)
    user.anonymize()
    from django.contrib.auth import logout as django_logout

    django_logout(request)
    messages.info(request, _("Votre compte a été anonymisé. L'historique reste lisible sous un nom pseudonymisé."))
    return redirect("login")


@login_required
def charte(request):
    documents = LegalDocument.objects.filter(published=True)
    return render(request, "accounts/settings/charte.html", {
        "documents": documents,
        "rendered": {doc.slug: render_markdown(doc.body) for doc in documents},
        "acceptances": request.user.legal_acceptances.select_related("document").all(),
        "tabs": _tabs("charte"), "tab": "charte", "page_title": "Charte & mentions",
    })


@login_required
@require_POST
def charte_accept(request, slug: str):
    document = get_object_or_404(LegalDocument, slug=slug, published=True)
    services.record_legal_acceptance(request.user, document.kind, request=request)
    if document.kind == "charte":
        request.user.must_accept_charte = False
        request.user.save(update_fields=["must_accept_charte", "updated_at"])
    messages.success(request, _("« %(titre)s » accepté (version %(v)s).")
                     % {"titre": document.title, "v": document.version})
    return redirect("settings_me:settings_charte")


@login_required
@require_POST
def prefs(request):
    """Endpoint JSON appelé par app.js (palette, mode, densité)."""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"ok": False}, status=400)
    allowed = {"palette", "mode", "density", "sidebar"}
    prefs_data = dict(request.user.prefs or {})
    for key, value in payload.items():
        if key in allowed:
            prefs_data[key] = value
    request.user.prefs = prefs_data
    request.user.save(update_fields=["prefs", "updated_at"])
    permissions.invalidate(request.user)
    return JsonResponse({"ok": True, "prefs": prefs_data})
