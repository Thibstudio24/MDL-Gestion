"""Comptes, rôles, invitations, sessions, A2F, acceptations de textes."""
from __future__ import annotations

import secrets
import string
import uuid
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from accounts.managers import UserManager
from core.permissions import LEVEL_CHOICES, MODULES


def new_token():
    return uuid.uuid4()


STATUS_CHOICES = [
    ("pending", _("en attente d'invitation")),
    ("active", _("actif")),
    ("inactive", _("inactif")),
    ("anonymized", _("anonymisé")),
]
GENDER_CHOICES = [("f", _("elle")), ("m", _("il")), ("n", _("neutre"))]
HOME_CHOICES = [("dashboard", _("Tableau de bord")), ("planning", _("Mon planning")),
                ("documents", _("Documents")), ("messages", _("Messages"))]
INVITATION_CHANNELS = [("email", _("E-mail")), ("manual", _("Transmis à la main")), ("both", _("Les deux"))]


class Role(models.Model):
    """Un seul rôle par membre ; les droits sont portés par RolePermission + fine_permissions."""

    name = models.CharField(_("nom"), max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.CharField(_("description"), max_length=240, blank=True)
    color = models.CharField(_("couleur"), max_length=9, default="#33556e")
    icon = models.CharField(_("icône"), max_length=24, default="user")
    is_administrator = models.BooleanField(_("rôle Administrateur"), default=False)
    is_system = models.BooleanField(_("rôle système (protégé)"), default=False)
    is_default = models.BooleanField(_("rôle par défaut"), default=False)
    force_2fa = models.BooleanField(_("imposer l'A2F"), default=False)
    force_2fa_deadline_days = models.PositiveIntegerField(_("délai d'activation (jours)"), default=14)
    fine_permissions = models.JSONField(_("droits fins"), default=list, blank=True)
    home = models.CharField(_("écran d'accueil"), max_length=16, choices=HOME_CHOICES, default="dashboard")
    order = models.PositiveIntegerField(_("ordre"), default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Rôle")
        verbose_name_plural = _("Rôles")
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or "role-%d" % (self.pk or 0)
        super().save(*args, **kwargs)

    @property
    def member_count(self) -> int:
        return self.members.filter(status="active").count()

    def rights_summary(self) -> str:
        labels = {0: "—", 1: "C", 2: "M"}
        levels = {perm.codename: perm.level for perm in self.permissions.all()}
        return " · ".join("%s %s" % (MODULES[key][:12], labels[levels[key]]) for key in MODULES if key in levels)


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    codename = models.CharField(_("module"), max_length=32, choices=[(key, label) for key, label in MODULES.items()])
    level = models.PositiveSmallIntegerField(_("niveau"), choices=LEVEL_CHOICES, default=0)

    class Meta:
        verbose_name = _("Droit de module")
        verbose_name_plural = _("Droits de module")
        unique_together = [("role", "codename")]

    def __str__(self) -> str:
        return "%s : %s = %s" % (self.role.name, self.codename, self.level)


class User(AbstractBaseUser):
    """Membre de l'association. E-mail = identifiant de connexion."""

    email = models.EmailField(_("e-mail"), max_length=190, unique=True, db_index=True)
    first_name = models.CharField(_("prénom"), max_length=80, blank=True)
    last_name = models.CharField(_("nom"), max_length=80, blank=True)
    display_function = models.CharField(_("fonction affichée"), max_length=120, blank=True)
    phone = models.CharField(_("téléphone"), max_length=32, blank=True)
    gender = models.CharField(_("mention"), max_length=1, choices=GENDER_CHOICES, blank=True)
    photo = models.FileField(
        _("photo"), upload_to="avatars/%Y/", blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp", "gif"])],
    )
    role = models.ForeignKey(Role, verbose_name=_("rôle"), null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="members")
    status = models.CharField(_("statut"), max_length=12, choices=STATUS_CHOICES, default="pending")
    is_boarder = models.BooleanField(_("interne (hébergement au lycée)"), default=False)
    totp_secret = models.CharField(_("clé A2F"), max_length=64, blank=True)
    totp_enabled = models.BooleanField(_("A2F activée"), default=False)
    totp_confirmed_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(_("doit changer son mot de passe"), default=False)
    must_accept_charte = models.BooleanField(_("doit accepter la charte"), default=False)
    failed_logins = models.PositiveSmallIntegerField(_("tentatives échouées"), default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(_("dernière activité"), null=True, blank=True)
    prefs = models.JSONField(_("préférences"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("Membre")
        verbose_name_plural = _("Membres")
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return self.get_full_name() or self.email

    # -- compatibilité Django ------------------------------------------------ #
    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_staff(self) -> bool:
        return self.is_administrator_flag

    @property
    def is_superuser(self) -> bool:
        return False

    def has_perm(self, perm, obj=None) -> bool:  # pragma: no cover - non utilisé (droits maison)
        return False

    def has_module_perm(self, perm, obj=None) -> bool:  # pragma: no cover
        return False

    # -- affichage ----------------------------------------------------------- #
    def get_full_name(self) -> str:
        return ("%s %s" % (self.first_name, self.last_name)).strip()

    def get_short_name(self) -> str:
        return self.first_name or self.email

    @property
    def initials(self) -> str:
        return ((self.first_name[:1] or "") + (self.last_name[:1] or "")).upper() or "?"

    @property
    def is_administrator_flag(self) -> bool:
        return bool(self.role and self.role.is_administrator)

    @property
    def two_factor_on(self) -> bool:
        return bool(self.totp_enabled and self.totp_confirmed_at)

    # -- préférences --------------------------------------------------------- #
    def pref(self, key: str, default=None):
        return (self.prefs or {}).get(key, default)

    def set_pref(self, key: str, value) -> None:
        prefs = dict(self.prefs or {})
        prefs[key] = value
        self.prefs = prefs
        self.save(update_fields=["prefs", "updated_at"])

    @property
    def receive_personal_email(self) -> bool:
        return bool(self.pref("receive_personal_email", True))

    @property
    def email_choice_made(self) -> bool:
        return bool(self.pref("email_choice_made", False))

    @property
    def push_enabled(self) -> bool:
        return bool(self.pref("push_enabled", True))

    @property
    def quiet_hours(self) -> dict:
        return self.pref("quiet_hours", {"actif": False, "debut": "22:00", "fin": "07:00"})

    # -- sécurité ------------------------------------------------------------ #
    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def lock(self, minutes: int) -> None:
        self.locked_until = timezone.now() + timedelta(minutes=minutes)
        self.failed_logins = 0
        self.save(update_fields=["locked_until", "failed_logins", "updated_at"])

    def unlock(self) -> None:
        self.locked_until = None
        self.failed_logins = 0
        self.save(update_fields=["locked_until", "failed_logins", "updated_at"])

    def two_factor_deadline(self):
        if not (self.role and self.role.force_2fa):
            return None
        base = self.totp_confirmed_at or self.created_at or timezone.now()
        return base + timedelta(days=int(self.role.force_2fa_deadline_days or 0))

    @property
    def two_factor_pending(self) -> bool:
        """Vrai quand le rôle impose l'A2F et qu'elle n'est pas encore activée.

        C'est l'état d'un compte freshly créé dont le rôle exige l'A2F :
        l'inscription doit être demandée dès la première connexion.
        """
        return bool(self.role and self.role.force_2fa and not self.two_factor_on)

    @property
    def two_factor_overdue(self) -> bool:
        deadline = self.two_factor_deadline()
        return bool(deadline and not self.two_factor_on and deadline < timezone.now())

    def anonymize(self) -> None:
        """RGPD : pseudonymisation, historique conservé et lisible."""
        self.status = "anonymized"
        self.first_name = "Membre"
        self.last_name = "supprimé"
        self.display_function = ""
        self.email = "anonyme-%s@supprime.invalid" % self.pk
        self.phone = ""
        self.gender = ""
        if self.photo:
            self.photo.delete(save=False)
        self.totp_secret = ""
        self.totp_enabled = False
        self.totp_confirmed_at = None
        self.prefs = {}
        self.locked_until = None
        self.failed_logins = 0
        self.password = make_password(secrets.token_urlsafe(32))
        self.save()
        RecoveryCode.objects.filter(user=self).delete()
        AccountSession.objects.filter(user=self).update(revoked_at=timezone.now())

    def home_url(self) -> str:
        home = (self.role.home if self.role else "dashboard") or "dashboard"
        return {
            "dashboard": "/",
            "planning": "/planning/mes-disponibilites/",
            "documents": "/documents/",
            "messages": "/messages/",
        }.get(home, "/")


class RoleMembership(models.Model):
    """Historique des rôles (un changement = une clôture + une ouverture)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_memberships")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="memberships")
    since = models.DateTimeField(default=timezone.now)
    until = models.DateTimeField(null=True, blank=True)
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = _("Historique de rôle")
        verbose_name_plural = _("Historiques de rôle")
        ordering = ["-since"]

    def __str__(self) -> str:
        return "%s → %s" % (self.user, self.role.name)


class Invitation(models.Model):
    """Invitation à usage unique : lien + code court pour les élèves sans e-mail fiable."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="invitation")
    token = models.UUIDField(default=new_token, unique=True, editable=False)
    code = models.CharField(_("code court"), max_length=6, unique=True, blank=True)
    message = models.TextField(_("message d'accompagnement"), blank=True)
    channel = models.CharField(_("canal"), max_length=8, choices=INVITATION_CHANNELS, default="email")
    expires_at = models.DateTimeField(_("expire le"))
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered = models.BooleanField(_("transmise"), default=False)
    reminded_at = models.DateTimeField(null=True, blank=True)
    reminder_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("Invitation")
        verbose_name_plural = _("Invitations")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return "%s (%s)" % (self.user.email, self.code)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_code()
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timezone.now())

    @property
    def is_used(self) -> bool:
        return bool(self.accepted_at)

    @property
    def is_valid(self) -> bool:
        return not (self.is_expired or self.is_used)

    def accept_url(self) -> str:
        return "/inviter/%s/" % self.token

    def renew(self, days: int = 7) -> None:
        self.token = uuid.uuid4()
        self.code = generate_code()
        self.expires_at = timezone.now() + timedelta(days=days)
        self.accepted_at = None
        self.save(update_fields=["token", "code", "expires_at", "accepted_at"])


CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")


def generate_code() -> str:
    for _attempt in range(12):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not Invitation.objects.filter(code=code).exists():
            return code
    return secrets.token_hex(3).upper()


class RecoveryCode(models.Model):
    """Codes de récupération A2F : hachés (SHA-256), usage unique."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Code de récupération")
        verbose_name_plural = _("Codes de récupération")

    @property
    def is_used(self) -> bool:
        return bool(self.used_at)


class AccountSession(models.Model):
    """Sessions révocables appareil par appareil."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    session_key = models.CharField(max_length=64, unique=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=240, blank=True)
    device = models.CharField(_("appareil"), max_length=120, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    is_pwa = models.BooleanField(_("installée (PWA)"), default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Session")
        verbose_name_plural = _("Sessions")
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return "%s — %s" % (self.user.email, self.device or self.ip)


class LoginAttempt(models.Model):
    """Journal des connexions (compteur de verrouillage sur 15 minutes glissantes)."""

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_attempts")
    email = models.EmailField(db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=240, blank=True)
    success = models.BooleanField(default=False)
    reason = models.CharField(_("motif"), max_length=120, blank=True)
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("Tentative de connexion")
        verbose_name_plural = _("Tentatives de connexion")
        ordering = ["-at"]

    def __str__(self) -> str:
        return "%s %s" % (self.email, "OK" if self.success else self.reason)


class LegalAcceptance(models.Model):
    """Acceptation horodatée d'un texte (version + IP)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="legal_acceptances")
    document = models.ForeignKey("core.LegalDocument", on_delete=models.CASCADE, related_name="acceptances")
    version = models.PositiveIntegerField(default=1)
    accepted_at = models.DateTimeField(default=timezone.now)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = _("Acceptation")
        verbose_name_plural = _("Acceptations")
        unique_together = [("user", "document", "version")]
        ordering = ["-accepted_at"]

    def __str__(self) -> str:
        return "%s — %s v%s" % (self.user, self.document.title, self.version)


class UserProfileExtra(models.Model):
    """Informations libres (notes du bureau, promotion, année d'arrivée)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="extra")
    notes = models.TextField(_("notes"), blank=True)
    promotion = models.CharField(_("promotion"), max_length=20, blank=True)
    since_year = models.CharField(_("membre depuis"), max_length=12, blank=True)

    class Meta:
        verbose_name = _("Complément de fiche")
        verbose_name_plural = _("Compléments de fiche")

    def __str__(self) -> str:
        return "Complément — %s" % self.user
