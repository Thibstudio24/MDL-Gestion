"""Services des comptes : authentification verrouillable, invitations, rôles, interventions."""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login as django_login
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.models import (
    AccountSession,
    Invitation,
    LoginAttempt,
    Role,
    RoleMembership,
    RolePermission,
    User,
)
from accounts.twofa import verify
from audit.services import log
from core import permissions
from core.models import Setting
from core.permissions import BOARD_TEMPLATE, DEFAULT_LEVELS


# --------------------------------------------------------------------------- #
# Authentification
# --------------------------------------------------------------------------- #
def client_ip(request) -> str:
    if request is None:
        return ""
    return getattr(request, "client_ip", None) or request.META.get("REMOTE_ADDR", "")


def recent_failures(email: str, ip: str, minutes: int = 15) -> int:
    limit = timezone.now() - timedelta(minutes=minutes)
    return LoginAttempt.objects.filter(email__iexact=email, success=False, at__gte=limit).count() + \
        LoginAttempt.objects.filter(ip=ip, success=False, at__gte=limit).count()


def authenticate(request, email: str, password: str):
    """Retourne (user, erreur). Verrouillage : 5 tentatives → 15 minutes (compte et IP)."""
    email = (email or "").strip().lower()
    ip = client_ip(request)
    max_attempts = int(getattr(settings, "MDL_LOGIN_MAX_ATTEMPTS", 5))
    lock_minutes = int(getattr(settings, "MDL_LOGIN_LOCKOUT_MINUTES", 15))

    user = User.objects.filter(email__iexact=email).select_related("role").first()
    if user and user.is_locked:
        minutes_left = max(1, int((user.locked_until - timezone.now()).total_seconds() // 60) + 1)
        _record(None, email, ip, request, False, "verrouillé")
        return None, _("Le compte est temporairement verrouillé : réessayez dans %(n)s minutes.") % {"n": minutes_left}

    if recent_failures(email, ip) >= max_attempts * 2:
        _record(None, email, ip, request, False, "trop de tentatives")
        return None, _("Trop de tentatives depuis cette adresse : réessayez dans %(n)s minutes.") % {"n": lock_minutes}

    if user is None:
        _record(None, email, ip, request, False, "compte inconnu")
        return None, _("Identifiants invalides.")
    if user.status == "pending":
        _record(user, email, ip, request, False, "invitation non acceptée")
        return None, _("Votre invitation n'a pas encore été acceptée : choisissez d'abord votre mot de passe.")
    if user.status == "anonymized":
        _record(user, email, ip, request, False, "compte anonymisé")
        return None, _("Ce compte a été anonymisé.")
    if user.status == "inactive":
        _record(user, email, ip, request, False, "compte désactivé")
        return None, _("Ce compte est désactivé : contactez le bureau.")
    if not user.check_password(password or ""):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= max_attempts:
            user.lock(lock_minutes)
            log(user, "auth.locked", "members", user, "Compte verrouillé après %(n)s tentatives" % {"n": max_attempts},
                level="warn", request=request)
            _record(user, email, ip, request, False, "verrouillage")
            return None, _("Trop de tentatives : compte verrouillé %(n)s minutes.") % {"n": lock_minutes}
        user.save(update_fields=["failed_logins", "updated_at"])
        _record(user, email, ip, request, False, "mot de passe invalide")
        log(user, "auth.login_failed", "members", user, "Échec de connexion", level="warn", request=request)
        return None, _("Identifiants invalides.")

    user.failed_logins = 0
    user.locked_until = None
    user.last_seen = timezone.now()
    user.save(update_fields=["failed_logins", "locked_until", "last_seen", "updated_at"])
    _record(user, email, ip, request, True, "")
    return user, None


def _record(user, email, ip, request, success: bool, reason: str) -> None:
    LoginAttempt.objects.create(
        user=user, email=email[:190], ip=ip or None,
        user_agent=(getattr(request, "user_agent", "") or "")[:240],
        success=success, reason=reason[:120],
    )


def start_session(request, user, remember: bool = True, pwa: bool = False) -> None:
    if not remember:
        request.session.set_expiry(0)
    else:
        request.session.set_expiry(int(getattr(settings, "SESSION_COOKIE_AGE", 1209600)))
    django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    register_session(request, user, pwa=pwa)
    log(user, "auth.login", "members", user, "Connexion réussie", request=request)


def register_session(request, user, pwa: bool = False) -> None:
    key = request.session.session_key or ""
    if not key:
        return
    device = _device_label(getattr(request, "user_agent", ""))
    AccountSession.objects.update_or_create(
        session_key=key[:64],
        defaults={
            "user": user,
            "ip": client_ip(request) or None,
            "user_agent": (getattr(request, "user_agent", "") or "")[:240],
            "device": device,
            "last_seen": timezone.now(),
            "is_pwa": pwa,
        },
    )


def _device_label(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "iphone" in ua or "ipad" in ua:
        return "iPhone / iPad"
    if "android" in ua:
        return "Android"
    if "firefox" in ua:
        return "Firefox"
    if "chrome" in ua:
        return "Chrome"
    if "safari" in ua:
        return "Safari"
    return "Navigateur"


def revoke_session(user, session_key: str) -> int:
    from django.contrib.sessions.models import Session

    AccountSession.objects.filter(user=user, session_key=session_key).update(revoked_at=timezone.now())
    return Session.objects.filter(session_key=session_key).delete()[0]


def revoke_all_sessions(user, keep: str | None = None) -> int:
    from django.contrib.sessions.models import Session

    keys = list(AccountSession.objects.filter(user=user, revoked_at__isnull=True)
                .exclude(session_key=keep or "").values_list("session_key", flat=True))
    AccountSession.objects.filter(session_key__in=keys).update(revoked_at=timezone.now())
    return Session.objects.filter(session_key__in=keys).delete()[0]


def require_two_factor(user) -> bool:
    return bool(user.two_factor_on or user.two_factor_overdue)


def check_second_factor(user, code: str) -> bool:
    if verify(user.totp_secret, code, user=user):
        return True
    from accounts.twofa import use_recovery_code

    return use_recovery_code(user, code)


# --------------------------------------------------------------------------- #
# Invitations
# --------------------------------------------------------------------------- #
DEFAULT_VALIDITY_DAYS = 7
VALIDITY_CHOICES = [(1, "1 jour"), (3, "3 jours"), (7, "7 jours (défaut)"), (30, "30 jours")]


def create_member(*, email: str, first_name: str, last_name: str, role: Role,
                  display_function: str = "", days: int = DEFAULT_VALIDITY_DAYS,
                  message: str = "", channel: str = "email", actor=None,
                  boarder: bool = False, password: str | None = None) -> tuple[User, Invitation]:
    """Crée un compte « en attente » + son invitation (usage unique)."""
    email = (email or "").strip().lower()
    with transaction.atomic():
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email, password=password, first_name=first_name, last_name=last_name,
                display_function=display_function, role=role, status="pending" if password is None else "active",
                is_boarder=boarder, must_change_password=bool(password),
            )
            RoleMembership.objects.create(user=user, role=role, changed_by=actor)
        else:
            user.first_name = first_name or user.first_name
            user.last_name = last_name or user.last_name
            user.display_function = display_function or user.display_function
            user.role = role
            user.is_boarder = boarder
            if user.status == "inactive":
                user.status = "pending"
            user.save()
        invitation = Invitation.objects.filter(user=user).first()
        if invitation is None:
            invitation = Invitation.objects.create(
                user=user, message=message, channel=channel,
                expires_at=timezone.now() + timedelta(days=days), created_by=actor,
            )
        else:
            invitation.renew(days)
            invitation.message = message
            invitation.channel = channel
            invitation.save(update_fields=["token", "code", "expires_at", "message", "channel", "accepted_at"])
    log(actor, "member.invited", "members", user,
        "Invitation envoyée à %(email)s (valable %(n)s jours)" % {"email": email, "n": days}, request=None)
    return user, invitation


def create_administrator(*, email: str, password: str, first_name: str, last_name: str) -> User:
    """Premier compte de l'installation : administrateur actif, sans invitation ni démo."""
    email = (email or "").strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        raise ValueError(_("Un compte existe déjà avec ce courriel."))
    if len(password or "") < int(Setting.value("securite", "password_min_length", 10)):
        raise ValueError(_("Le mot de passe doit comporter au moins %(n)s caractères.")
                         % {"n": Setting.value("securite", "password_min_length", 10)})
    role = ensure_admin_role()
    with transaction.atomic():
        # receive_personal_email et email_choice_made sont des propriétés en lecture
        # seule adossées au champ JSON « prefs » : elles s'écrivent par ce champ.
        user = User.objects.create_user(
            email=email, password=password, first_name=first_name, last_name=last_name,
            display_function="Administrateur", role=role, status="active",
            prefs={"receive_personal_email": True, "email_choice_made": True},
        )
        RoleMembership.objects.create(user=user, role=role)
    log(None, "member.created", "members", user, "Premier administrateur créé : %s" % email)
    return user


def accept_invitation(invitation: Invitation, password: str, *, accept_charte: bool = False,
                      receive_email: bool | None = None, request=None) -> tuple[bool, str]:
    if not invitation.is_valid:
        return False, _("Cette invitation n'est plus valable : demandez un renvoi au bureau.")
    user = invitation.user
    if not accept_charte and user.must_accept_charte:
        return False, _("Vous devez accepter la charte pour continuer.")
    user.set_password(password)
    user.status = "active"
    user.must_change_password = False
    invitation.accepted_at = timezone.now()
    invitation.delivered = True
    invitation.save(update_fields=["accepted_at", "delivered"])
    prefs = dict(user.prefs or {})
    if receive_email is not None:
        prefs["receive_personal_email"] = bool(receive_email)
        prefs["email_choice_made"] = True
    user.prefs = prefs
    if not user.email_choice_made and receive_email is None:
        user.must_accept_charte = bool(user.must_accept_charte and not accept_charte)
    user.save()
    if accept_charte:
        record_legal_acceptance(user, "charte", request=request)
    log(user, "member.updated", "members", user, "Invitation acceptée, compte activé", request=request)
    return True, ""


def record_legal_acceptance(user, kind: str, request=None) -> None:
    from accounts.models import LegalAcceptance
    from core.models import LegalDocument

    document = LegalDocument.objects.filter(kind=kind, published=True).first()
    if document is None:
        return
    LegalAcceptance.objects.get_or_create(
        user=user, document=document, version=document.version,
        defaults={"ip": client_ip(request) if request else None},
    )


def remind_invitations() -> int:
    """Relance automatique à J-1 (et signalement à l'expiration)."""
    soon = timezone.now() + timedelta(days=1)
    soon_start = soon - timedelta(hours=2)
    sent = 0
    for invitation in Invitation.objects.filter(accepted_at__isnull=True, expires_at__gte=soon_start,
                                                expires_at__lte=soon).select_related("user"):
        if invitation.reminded_at and (timezone.now() - invitation.reminded_at) < timedelta(hours=12):
            continue
        try:
            from mail.services import queue_email
            from notifications.services import notify

            queue_email(
                to_email=invitation.user.email,
                recipient_user=invitation.user,
                subject="Ton invitation expire demain",
                text_body=render_invitation_email(invitation, reminder=True),
                kind="invitation",
            )
            notify(invitation.user, "invitation", "Ton invitation expire demain",
                   "Ouvre le lien reçu pour choisir ton mot de passe.", url=invitation.accept_url())
        except Exception:
            continue
        invitation.reminded_at = timezone.now()
        invitation.reminder_count += 1
        invitation.save(update_fields=["reminded_at", "reminder_count"])
        sent += 1
    return sent


def render_invitation_email(invitation, reminder: bool = False) -> str:
    user = invitation.user
    from core.models import Setting

    brand = Setting.brand()
    nom = brand.get("nom") or "MDL"
    lycee = brand.get("lycee") or ""
    jours = max(0, (invitation.expires_at - timezone.now()).days)
    base = str(getattr(settings, "BASE_URL", "")).rstrip("/")
    lien = "%s%s" % (base, invitation.accept_url())
    sujet = "Ton invitation expire demain" if reminder else "Invitation à rejoindre la %s" % nom
    return (
        "%(prenom)s,\n\n"
        "le bureau de la %(nom)s%(lycee)s t'invite à rejoindre l'association en tant que %(fonction)s.\n\n"
        "Clique sur ce lien pour choisir ton mot de passe (valable %(jours)s jours) :\n%(lien)s\n\n"
        "Si le lien ne s'ouvre pas, communique ce code à l'administration : %(code)s\n\n"
        "Ce lien est personnel et à usage unique.\n\n— %(nom)s\n%(sujet)s"
    ) % {
        "prenom": user.first_name or "Bonjour",
        "nom": nom,
        "lycee": (" du %s" % lycee) if lycee else "",
        "fonction": user.display_function or (user.role.name if user.role else "membre"),
        "jours": jours,
        "lien": lien,
        "code": invitation.code,
        "sujet": sujet,
    }


# --------------------------------------------------------------------------- #
# Rôles
# --------------------------------------------------------------------------- #
def ensure_admin_role() -> Role:
    """Le seul rôle créé à l'installation : l'association compose ensuite les siens."""
    admin, _created = Role.objects.get_or_create(
        name="Administrateur",
        defaults={"slug": "administrateur", "is_administrator": True, "is_system": True, "order": 1,
                  "description": "Tous les droits, partout.", "force_2fa": True, "color": "#33556e"},
    )
    if not admin.is_administrator:
        admin.is_administrator = True
        admin.is_system = True
        admin.save(update_fields=["is_administrator", "is_system"])
    _apply_levels(admin, DEFAULT_LEVELS["Administrateur"], [])
    return admin


def ensure_base_roles() -> None:
    """Administrateur + Utilisateur avec des droits réels (jamais « tout à zéro »).

    Réservé à `manage.py seed`, qui est un choix explicite : l'assistant
    d'installation ne crée que le rôle administrateur.
    """
    ensure_admin_role()

    user_role, _created = Role.objects.get_or_create(
        name="Utilisateur",
        defaults={"slug": "utilisateur", "is_system": True, "is_default": True, "order": 50,
                  "description": "Saisie courante : documents, plannings, ménage, messages.",
                  "color": "#2c6f52"},
    )
    _apply_levels(user_role, DEFAULT_LEVELS["Utilisateur"], [])


def _apply_levels(role: Role, levels: dict, fine: list) -> None:
    for module, level in levels.items():
        RolePermission.objects.update_or_create(role=role, codename=module, defaults={"level": int(level)})
    for module in permissions.MODULES:
        if module not in levels:
            RolePermission.objects.filter(role=role, codename=module).delete()
    role.fine_permissions = list(fine or [])
    role.save(update_fields=["fine_permissions"])
    permissions.invalidate_all()


def create_board_roles(mapping: dict | None = None) -> list[Role]:
    """Crée les rôles du bureau à partir de la trame proposée (modifiable ensuite)."""
    created = []
    for index, name in enumerate(permissions.BOARD_ROLES):
        template = dict(BOARD_TEMPLATE.get(name, {"dashboard": 1, "documents": 2, "mail": 1}))
        if mapping and name in mapping:
            template.update(mapping[name])
        fine = template.pop("fine", [])
        role, _was_created = Role.objects.get_or_create(
            name=name, defaults={"slug": _slug(name), "order": 10 + index, "description": "Rôle du bureau.",
                                 "color": "#a76a43"}
        )
        _apply_levels(role, template, fine)
        created.append(role)
    return created


def _slug(value: str) -> str:
    from django.utils.text import slugify

    slug = slugify(value.replace("·", "").replace("é", "e"))
    return slug or "role"


def change_role(user: User, role: Role, actor=None) -> None:
    """Réassignation + historique RoleMembership + invalidation du cache des droits."""
    previous = user.role
    RoleMembership.objects.filter(user=user, until__isnull=True).update(until=timezone.now(), changed_by=actor)
    user.role = role
    user.save(update_fields=["role", "updated_at"])
    RoleMembership.objects.create(user=user, role=role, changed_by=actor)
    permissions.invalidate(user)
    log(actor, "member.role_changed", "members", user,
        "Rôle modifié : %(avant)s → %(apres)s" % {"avant": previous.name if previous else "—", "apres": role.name},
        previous={"role": previous.name if previous else None}, current={"role": role.name}, level="warn")


def last_administrator(user: User) -> bool:
    """Le rôle Administrateur ne peut être supprimé/dégradé s'il ne reste qu'un admin actif."""
    if not (user.role and user.role.is_administrator):
        return False
    return User.objects.filter(status="active", role__is_administrator=True).count() <= 1


def active_administrators() -> int:
    return User.objects.filter(status="active", role__is_administrator=True).count()


# --------------------------------------------------------------------------- #
# Interventions techniques (hub / jeton)
# --------------------------------------------------------------------------- #
def apply_remote_action(action: str, target: str, actor=None) -> dict:
    from notifications.services import notify

    target = (target or "").strip().lower()
    if action == "health":
        from core.services import health

        return {"ok": True, "message": "état de santé lu", "data": health()}
    user = User.objects.filter(email__iexact=target).first()
    if user is None:
        return {"ok": False, "error": "compte introuvable : %s" % target}
    if action == "reset_password":
        password = secrets.token_urlsafe(9) + "Aa1"
        user.set_password(password)
        user.must_change_password = True
        user.save()
        try:
            from mail.services import queue_email

            queue_email(
                to_email=user.email, recipient_user=user,
                subject="Réinitialisation de votre mot de passe",
                text_body=(
                    "Bonjour %(prenom)s,\n\nUn nouveau mot de passe provisoire a été généré pour votre compte "
                    "%(email)s :\n\n%(password)s\n\nConnectez-vous puis changez-le immédiatement.\n\n— %(nom)s"
                ) % {"prenom": user.first_name or "Bonjour", "email": user.email, "password": password,
                     "nom": "MDL Gestion"},
                kind="security", urgent=True,
            )
        except Exception as exc:
            return {"ok": False, "error": "mot de passe changé mais e-mail impossible : %s" % exc}
        notify(user, "security", "Votre mot de passe a été réinitialisé",
               "Un mot de passe provisoire vient de vous être envoyé par e-mail.", url="/parametres/securite/")
        revoke_all_sessions(user)
        log(actor, "auth.password_reset", "members", user,
            "Mot de passe réinitialisé à distance (provisoire, non affiché)", level="danger")
        return {"ok": True, "message": "mot de passe provisoire envoyé à l'intéressé"}
    if action == "disable_2fa":
        user.totp_secret = ""
        user.totp_enabled = False
        user.totp_confirmed_at = None
        user.save(update_fields=["totp_secret", "totp_enabled", "totp_confirmed_at", "updated_at"])
        notify(user, "security", "Votre A2F a été désactivée",
               "L'authentification à deux facteurs a été coupée sur votre compte.", url="/parametres/securite/")
        log(actor, "auth.2fa_disabled", "members", user, "A2F coupée à distance", level="danger")
        return {"ok": True, "message": "A2F désactivée pour %s" % user.email}
    if action == "resend_invite":
        invitation = getattr(user, "invitation", None)
        if invitation is None:
            return {"ok": False, "error": "aucune invitation pour ce compte"}
        invitation.renew()
        try:
            from mail.services import queue_email

            queue_email(to_email=user.email, recipient_user=user,
                        subject="Invitation à rejoindre l'association",
                        text_body=render_invitation_email(invitation), kind="invitation")
        except Exception:
            pass
        log(actor, "member.invitation_resent", "members", user, "Invitation renvoyée à distance", level="warn")
        return {"ok": True, "message": "invitation renvoyée (%s)" % invitation.code}
    return {"ok": False, "error": "action non prise en charge : %s" % action}


def set_password_by_admin(user: User, actor=None) -> str:
    """Mot de passe provisoire généré, envoyé par e-mail, jamais affiché à l'administrateur."""
    password = secrets.token_urlsafe(9) + "Aa1"
    user.set_password(password)
    user.must_change_password = True
    user.save()
    try:
        from mail.services import queue_email

        queue_email(to_email=user.email, recipient_user=user,
                    subject="Réinitialisation de votre mot de passe",
                    text_body="Bonjour %s,\n\nVotre nouveau mot de passe provisoire : %s\n\nChangez-le dès la connexion."
                    % (user.first_name or "Bonjour", password), kind="security", urgent=True)
    except Exception:
        pass
    revoke_all_sessions(user)
    log(actor, "auth.password_reset", "members", user, "Mot de passe réinitialisé par un administrateur",
        level="danger")
    return password
