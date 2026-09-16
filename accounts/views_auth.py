"""Écrans d'authentification : connexion, A2F, invitation, bienvenue, ré-authentification."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import logout as django_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from accounts import services, twofa
from accounts.forms import (
    LoginForm, PasswordResetForm, PasswordResetRequestForm, ReauthForm, SecondFactorForm, WelcomeForm,
)
from accounts.models import Invitation, User
from audit.services import log
from core.decorators import mark_reauthenticated
from core.models import LegalDocument

RESET_SALT = "mdl-password-reset"
RESET_MAX_AGE = 3 * 3600


def _installer_open() -> bool:
    from config.settings import installed

    return not installed()


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.user.home_url())
    if _installer_open() and request.path.startswith("/connexion/"):
        return redirect("installer_root")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user, error = services.authenticate(
            request, form.cleaned_data["email"], form.cleaned_data["password"]
        )
        if user is None:
            form.add_error(None, error)
        elif user.two_factor_on:
            request.session["pre_2fa_user"] = user.pk
            request.session["remember"] = bool(form.cleaned_data.get("remember"))
            return redirect("auth:twofa")
        else:
            services.start_session(request, user, remember=bool(form.cleaned_data.get("remember")),
                                   pwa=request.headers.get("sec-fetch-mode") == "cors")
            if user.two_factor_overdue:
                return redirect("auth:twofa_setup")
            if user.must_change_password or user.must_accept_charte or not user.email_choice_made:
                return redirect("auth:welcome")
            return redirect(user.home_url())
    return render(request, "accounts/login.html", {
        "form": form,
        "page_title": "Espace des membres",
        "bare": True,
    })


@require_http_methods(["GET", "POST"])
def second_factor(request):
    user_id = request.session.get("pre_2fa_user")
    if not user_id:
        return redirect("login")
    user = get_object_or_404(User, pk=user_id)
    form = SecondFactorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if services.check_second_factor(user, form.cleaned_data["code"]):
            request.session.pop("pre_2fa_user", None)
            services.start_session(request, user, remember=bool(request.session.get("remember", True)))
            if user.two_factor_overdue:
                return redirect("auth:twofa_setup")
            return redirect(user.home_url())
        form.add_error("code", _("Code refusé : vérifiez l'heure de votre appareil ou utilisez un code de récupération."))
    return render(request, "accounts/twofa.html", {"form": form, "page_title": "Authentification à deux facteurs"})


@login_required
@require_http_methods(["GET", "POST"])
def twofa_setup(request):
    user = request.user
    secret = request.session.get("totp_pending") or twofa.generate_secret()
    request.session["totp_pending"] = secret
    form = SecondFactorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if twofa.verify(secret, form.cleaned_data["code"], user=user):
            user.totp_secret = secret
            user.totp_enabled = True
            user.totp_confirmed_at = timezone.now()
            user.save(update_fields=["totp_secret", "totp_enabled", "totp_confirmed_at", "updated_at"])
            request.session.pop("totp_pending", None)
            codes = twofa.generate_recovery_codes(user)
            log(user, "auth.2fa_enabled", "members", user, "A2F activée", request=request)
            return render(request, "accounts/twofa_codes.html", {
                "codes": codes, "page_title": "Codes de récupération",
            })
        form.add_error("code", _("Code invalide : réessayez avec le code affiché actuellement."))
    uri = twofa.provisioning_uri(secret, user.email)
    return render(request, "accounts/twofa_setup.html", {
        "form": form, "secret": secret, "qr": twofa.qr_svg(uri), "uri": uri,
        "page_title": "Activer l'authentification à deux facteurs",
        "deadline": user.two_factor_deadline(),
        "overdue": user.two_factor_overdue,
    })


@login_required
def twofa_disable(request):
    if request.method != "POST":
        return redirect("settings_security")
    user = request.user
    user.totp_enabled = False
    user.totp_confirmed_at = None
    user.totp_secret = ""
    user.save(update_fields=["totp_enabled", "totp_confirmed_at", "totp_secret", "updated_at"])
    log(user, "auth.2fa_disabled", "members", user, "A2F désactivée par le membre", level="warn", request=request)
    messages.success(request, _("Authentification à deux facteurs désactivée."))
    return redirect("settings_security")


@require_http_methods(["GET", "POST"])
def welcome(request):
    if not request.user.is_authenticated:
        return redirect("login")
    user = request.user
    charte = LegalDocument.objects.filter(kind="charte", requires_acceptance=True, published=True).first()
    form = WelcomeForm(request.POST or None, charte_required=bool(charte))
    if request.method == "POST" and form.is_valid():
        prefs = dict(user.prefs or {})
        prefs["receive_personal_email"] = bool(form.cleaned_data["receive_personal_email"])
        prefs["email_choice_made"] = True
        user.prefs = prefs
        if charte and form.cleaned_data.get("accept_charte"):
            user.must_accept_charte = False
            services.record_legal_acceptance(user, "charte", request=request)
        user.save(update_fields=["prefs", "must_accept_charte", "updated_at"])
        messages.success(request, _("Réglages enregistrés. Bienvenue !"))
        return redirect(user.home_url())
    return render(request, "accounts/welcome.html", {
        "form": form, "charte": charte, "page_title": "Bienvenue",
    })


def logout_view(request):
    if request.user.is_authenticated:
        log(request.user, "auth.logout", "members", request.user, "Déconnexion", request=request)
        django_logout(request)
    messages.info(request, _("Vous êtes déconnecté."))
    return redirect("login")


@require_http_methods(["GET", "POST"])
@login_required
def reauth(request):
    form = ReauthForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if request.user.check_password(form.cleaned_data["password"]):
            mark_reauthenticated(request)
            log(request.user, "auth.reauth", "members", request.user, "Ré-authentification", request=request)
            return redirect(request.session.pop("reauth_next", "/"))
        form.add_error("password", _("Mot de passe incorrect."))
    return render(request, "accounts/reauth.html", {"form": form, "page_title": "Confirmation requise"})


@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email, status="active").first()
        if user:
            token = signing.dumps({"uid": user.pk, "email": user.email}, salt=RESET_SALT)
            link = "%s%s" % (str(getattr(__import__("django.conf", fromlist=["settings"]).settings, "BASE_URL", "")).rstrip("/"),
                             reverse("password_reset_confirm", args=[token]))
            try:
                from mail.services import queue_email

                queue_email(
                    to_email=user.email, recipient_user=user,
                    subject="Réinitialisation de votre mot de passe",
                    text_body=(
                        "Bonjour %s,\n\nPour choisir un nouveau mot de passe, ouvrez ce lien (valable 3 heures) :\n%s\n\n"
                        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n\n— MDL Gestion"
                    ) % (user.first_name or "Bonjour", link),
                    kind="password_reset", urgent=True,
                )
            except Exception:
                pass
        messages.info(request, _("Si un compte correspond à cette adresse, un lien vient d'être envoyé."))
        return redirect("login")
    return render(request, "accounts/password_reset.html", {"form": form, "page_title": "Mot de passe oublié"})


@require_http_methods(["GET", "POST"])
def password_reset_confirm(request, token: str):
    try:
        payload = signing.loads(token, max_age=RESET_MAX_AGE, salt=RESET_SALT)
    except signing.BadSignature:
        return render(request, "accounts/token_invalid.html", {
            "reason": _("Ce lien est expiré ou a déjà été utilisé. Demandez-en un nouveau."),
            "page_title": "Lien invalide",
        }, status=400)
    user = get_object_or_404(User, pk=payload["uid"])
    if user.email != payload.get("email"):
        return render(request, "accounts/token_invalid.html", {
            "reason": _("Ce lien ne correspond plus au compte."), "page_title": "Lien invalide",
        }, status=400)
    form = PasswordResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        password = form.cleaned_data["password1"]
        try:
            validate_password(password, user)
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error("password1", message)
        else:
            user.set_password(password)
            user.must_change_password = False
            user.status = "active" if user.status == "pending" else user.status
            user.save()
            services.revoke_all_sessions(user)
            log(user, "auth.password_changed", "members", user, "Mot de passe réinitialisé par lien", level="warn")
            messages.success(request, _("Mot de passe mis à jour : vous pouvez vous connecter."))
            return redirect("login")
    return render(request, "accounts/password_reset_confirm.html", {
        "form": form, "user": user, "page_title": "Nouveau mot de passe",
    })


def invitation_accept(request, token):
    invitation = _find_invitation(token)
    return _invitation_flow(request, invitation)


def invitation_code(request, code: str):
    invitation = Invitation.objects.filter(code__iexact=code.strip()).first()
    return _invitation_flow(request, invitation, invalid_code=code)


def _find_invitation(token: str):
    try:
        return Invitation.objects.filter(token=token).first()
    except (ValueError, ValidationError):
        return None


def _invitation_flow(request, invitation, invalid_code: str = ""):
    if invitation is None:
        return render(request, "accounts/invitation_invalid.html", {
            "reason": _("Ce lien n'existe pas. Vérifiez l'adresse ou demandez un renvoi au bureau."),
            "code": invalid_code, "page_title": "Invitation introuvable",
        }, status=404)
    if invitation.is_used:
        return render(request, "accounts/invitation_invalid.html", {
            "reason": _("Cette invitation a déjà été utilisée. Connectez-vous avec votre mot de passe."),
            "page_title": "Invitation déjà utilisée",
        }, status=410)
    if invitation.is_expired:
        return render(request, "accounts/invitation_invalid.html", {
            "reason": _("Cette invitation est expirée depuis le %(date)s. Un ayant droit peut la renvoyer.")
            % {"date": invitation.expires_at.strftime("%d/%m/%Y")},
            "page_title": "Invitation expirée",
        }, status=410)

    user = invitation.user
    charte = LegalDocument.objects.filter(kind="charte", requires_acceptance=True, published=True).first()
    if charte and not user.legal_acceptances.filter(document=charte).exists():
        user.must_accept_charte = True
    form = PasswordResetForm(request.POST or None)
    accept = request.POST.get("accept_charte") == "on" if request.method == "POST" else False
    email_choice = request.POST.get("receive_email")
    if request.method == "POST" and form.is_valid():
        password = form.cleaned_data["password1"]
        try:
            validate_password(password, user)
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error("password1", message)
        else:
            receive = None if email_choice is None else email_choice == "on"
            ok, error = services.accept_invitation(
                invitation, password, accept_charte=accept or not charte, receive_email=receive, request=request
            )
            if ok:
                services.start_session(request, invitation.user, remember=True)
                messages.success(request, _("Bienvenue %(prenom)s ! Votre compte est activé.")
                                 % {"prenom": invitation.user.first_name or ""})
                return redirect("auth:welcome" if not invitation.user.email_choice_made else invitation.user.home_url())
            form.add_error(None, error)
    return render(request, "accounts/invitation_accept.html", {
        "form": form, "invitation": invitation, "user": user, "charte": charte,
        "page_title": "Choisir mon mot de passe",
    })
