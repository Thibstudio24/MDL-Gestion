"""Modèles du noyau : réglages, années scolaires, textes légaux, installation."""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

CACHE_KEY = "core:setting"
CACHE_TTL = 60

_DEFAULTS = {
    "branding": {
        "nom": "MDL",
        "sigle": "MDL",
        "lycee": "",
        "ville": "",
        "contact": "",
        "logo": "",
        "couleur_principale": "#33556e",
        "palette_imposee": "",
        "mode_impose": "",
    },
    "theme": {"palette": "ardoise", "mode": "light", "densite": "confort"},
    "app": {
        "maintenance": False,
        "maintenance_message": "",
        "exclus_maintenance": [],
        "timezone": "Europe/Paris",
        "version": "1.0.0",
    },
    "securite": {
        "password_min_length": 10,
        "login_max_attempts": 5,
        "login_lockout_minutes": 15,
        "session_days": 14,
        "audit_keep_years": 5,
        "delai_2fa_jours": 14,
        "reauth_minutes": 10,
    },
    "quota": {
        "max_file_mb": 10,
        "total_mb": 400,
        "versions_kept": 3,
        "chores_photos_kept": 0,
        "mail_purge_years": 2,
        "alerte_pct": [80, 95],
        "purge_inactive_months": 0,
    },
    "bilan": {
        "auto": True,
        "mode": "jour",
        "jour": 1,
        "heure": "07:00",
        "categorie": "Bilans",
        "destinataires": "module",
        "notifier_roles": [],
        "notifier_users": [],
    },
    "notifications": {"matrice": {}, "silence": {"debut": "22:00", "fin": "07:00", "actif": False}},
    # Les deux sections ci-dessous doivent rester déclarées : Setting.data() ne
    # fusionne que les sections listées ici. Sans elles, les réglages SMTP et les
    # clés VAPID sont écrits en base mais invisibles à la relecture.
    "mail": {
        "enabled": False,
        "host": "",
        "port": 587,
        "use_ssl": False,
        "use_tls": True,
        "user": "",
        "password": "",
        "from": "",
        "reply_to": "",
        "rate_per_minute": 15,
        "fallback": "inapp",
    },
    "push": {
        "enabled": False,
        "public_key": "",
        "private_key": "",
        "claims_email": "",
    },
    "menage": {"rappel_heure": "19:30", "auto_publish": False, "max_refusals": 0, "min_people": 1},
    "salle": {
        "jour_debut": 1,
        "jour_fin": 5,
        "soir_active": True,
        "soir_debut": "18:00",
        "soir_fin": "21:00",
        "couverture_min": 1,
        "couverture_max": 2,
        "pas_minutes": 60,
        "day_start": "08:00",
        "day_end": "18:00",
    },
    "hub": {
        "url": "",
        "install_id": "",
        "telemetry": False,
        "update_channel": "stable",
        "update_check": True,
        "pinned_version": "",
    },
}


def new_install_id() -> str:
    return uuid.uuid4().hex


def new_intervention_code() -> str:
    return uuid.uuid4().hex[:16]


class Setting(models.Model):
    """Réglages modifiables par l'admin (surcharge de config/instance.json)."""

    values = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Réglages")
        verbose_name_plural = _("Réglages")

    def __str__(self) -> str:
        return "Réglages de l'association"

    # -- accès ------------------------------------------------------------- #
    @classmethod
    def instance(cls) -> Setting:
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create(values={})
        return obj

    @classmethod
    def data(cls) -> dict:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached
        try:
            values = cls.instance().values or {}
        except Exception:  # base pas encore migrée
            values = {}
        merged = {section: {**defaults, **(values.get(section) or {})} for section, defaults in _DEFAULTS.items()}
        cache.set(CACHE_KEY, merged, CACHE_TTL)
        return merged

    @classmethod
    def value(cls, section: str, key: str, default=None):
        return cls.data().get(section, {}).get(key, default)

    @classmethod
    def set(cls, section: str, key: str, value) -> None:
        obj = cls.instance()
        values = dict(obj.values or {})
        values.setdefault(section, {})
        values[section][key] = value
        obj.values = values
        obj.save(update_fields=["values", "updated_at"])
        cache.delete(CACHE_KEY)

    @classmethod
    def update_section(cls, section: str, payload: dict) -> None:
        obj = cls.instance()
        values = dict(obj.values or {})
        merged = dict(values.get(section) or {})
        merged.update(payload)
        values[section] = merged
        obj.values = values
        obj.save(update_fields=["values", "updated_at"])
        cache.delete(CACHE_KEY)

    @classmethod
    def flush(cls) -> None:
        cache.delete(CACHE_KEY)

    # -- lecture pratique --------------------------------------------------- #
    @classmethod
    def brand(cls) -> dict:
        return cls.data().get("branding", {})

    @classmethod
    def theme(cls) -> dict:
        return cls.data().get("theme", {})

    @classmethod
    def forced_theme(cls) -> dict:
        brand = cls.brand()
        return {
            "palette": (brand.get("palette_imposee") or "").strip(),
            "mode": (brand.get("mode_impose") or "").strip(),
            "seed": brand.get("couleur_principale") or "",
        }


class SchoolYear(models.Model):
    """Année scolaire : toutes les données métier y sont rattachées."""

    label = models.CharField(_("libellé"), max_length=32, unique=True)
    start_date = models.DateField(_("début"))
    end_date = models.DateField(_("fin"))
    is_current = models.BooleanField(_("année en cours"), default=False)
    is_locked = models.BooleanField(_("clôturée (lecture seule)"), default=False)
    opening_balances = models.JSONField(_("soldes d'ouverture"), default=dict, blank=True)
    note = models.TextField(_("note"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Année scolaire")
        verbose_name_plural = _("Années scolaires")
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return self.label

    def save(self, *args, **kwargs):
        if self.is_current:
            SchoolYear.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    @classmethod
    def current(cls) -> SchoolYear | None:
        return cls.objects.filter(is_current=True).first() or cls.objects.order_by("-start_date").first()

    @classmethod
    def get_or_current(cls):
        return cls.current()

    def months(self) -> list[tuple[int, int]]:
        """Liste des (année, mois) couverts, de septembre à août."""
        out: list[tuple[int, int]] = []
        cursor = date(self.start_date.year, self.start_date.month, 1)
        while cursor <= self.end_date:
            out.append((cursor.year, cursor.month))
            cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
        return out

    def month_label(self, year: int, month: int) -> str:
        return "%s %s" % (calendar.month_name[month][:3].capitalize(), str(year)[2:])

    def contains(self, day) -> bool:
        return self.start_date <= day <= self.end_date

    def days_left(self) -> int:
        return max(0, (self.end_date - timezone.localdate()).days)


class ClosureDay(models.Model):
    """Jour de fermeture (vacances, jour férié) retiré des calendriers."""

    year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="closure_days")
    day = models.DateField(_("jour"))
    reason = models.CharField(_("motif"), max_length=120, blank=True)

    class Meta:
        verbose_name = _("Jour de fermeture")
        verbose_name_plural = _("Jours de fermeture")
        ordering = ["day"]
        unique_together = [("year", "day")]

    def __str__(self) -> str:
        return "%s — %s" % (self.day.strftime("%d/%m/%Y"), self.reason or _("fermé"))


LEGAL_KINDS = [
    ("mentions", _("Mentions légales")),
    ("rgpd", _("Données personnelles (RGPD)")),
    ("reglement", _("Règlement intérieur")),
    ("charte", _("Charte d'utilisation")),
]


class LegalDocument(models.Model):
    """Textes légaux éditables, versionnés, avec acceptation horodatée."""

    kind = models.CharField(_("type"), max_length=20, choices=LEGAL_KINDS)
    title = models.CharField(_("titre"), max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    body = models.TextField(_("contenu Markdown"), blank=True)
    version = models.PositiveIntegerField(default=1)
    requires_acceptance = models.BooleanField(_("acceptation obligatoire"), default=False)
    published = models.BooleanField(_("publié"), default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("Texte légal")
        verbose_name_plural = _("Textes légaux")
        ordering = ["kind"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title) or self.kind
        if self.pk:
            previous = LegalDocument.objects.filter(pk=self.pk).values_list("body", flat=True).first()
            if previous is not None and previous != self.body:
                self.version = (self.version or 1) + 1
        super().save(*args, **kwargs)


class Installation(models.Model):
    """Identité de cette installation pour le canal éditeur (sortant uniquement)."""

    install_id = models.CharField(_("identifiant"), max_length=64, unique=True, default=new_install_id)
    secret = models.CharField(_("secret"), max_length=128, blank=True)
    public_key_pem = models.TextField(_("clé publique (Ed25519)"), blank=True)
    private_key_pem = models.TextField(_("clé privée (Ed25519)"), blank=True)
    version = models.CharField(_("version"), max_length=20, blank=True)
    enabled = models.BooleanField(_("canal activé"), default=False)
    registered_at = models.DateTimeField(null=True, blank=True)
    last_ping_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    pending_update = models.CharField(_("mise à jour proposée"), max_length=20, blank=True)
    interventions = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _("Installation")
        verbose_name_plural = _("Installation")

    def __str__(self) -> str:
        return "%s (%s)" % (self.install_id[:8], self.version or "?")

    @classmethod
    def get(cls) -> Installation:
        obj = cls.objects.first()
        if obj is None:
            from .crypto import generate_keypair

            pub, priv = generate_keypair()
            obj = cls.objects.create(
                install_id=uuid.uuid4().hex,
                secret=uuid.uuid4().hex + uuid.uuid4().hex[:8],
                public_key_pem=pub,
                private_key_pem=priv,
            )
        return obj


class Intervention(models.Model):
    """Intervention technique à distance : prévue puis confirmée, révocable."""

    STATUSES = [
        ("queued", _("en attente")),
        ("delivered", _("délivrée")),
        ("applied", _("appliquée")),
        ("revoked", _("révoquée")),
        ("failed", _("échouée")),
    ]
    ORIGINS = [("hub", "Hub"), ("token", _("Jeton hors ligne")), ("cli", "CLI")]

    code = models.CharField(_("code"), max_length=32, unique=True, default=new_intervention_code)
    token = models.TextField(_("jeton signé"), blank=True)
    action = models.CharField(_("action"), max_length=32)
    target = models.EmailField(_("cible"), blank=True)
    reason = models.CharField(_("motif"), max_length=240, blank=True)
    status = models.CharField(_("état"), max_length=16, choices=STATUSES, default="queued")
    result = models.TextField(_("résultat"), blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    origin = models.CharField(_("origine"), max_length=8, choices=ORIGINS, default="hub")

    class Meta:
        verbose_name = _("Intervention technique")
        verbose_name_plural = _("Interventions techniques")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return "%s → %s (%s)" % (self.action, self.target, self.get_status_display())

    @property
    def is_pending(self) -> bool:
        return self.status in ("queued", "delivered")

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timezone.now())

    @classmethod
    def pending(cls):
        return cls.objects.filter(status__in=["queued", "delivered"]).order_by("-created_at")


def reminder_time(hhmm: str, default: str = "19:30") -> time:
    """Parse « 19:30 » en ``datetime.time``."""
    raw = (hhmm or default).strip()
    try:
        hours, minutes = raw.split(":", 1)
        return time(max(0, min(23, int(hours))), max(0, min(59, int(minutes))))
    except (ValueError, AttributeError):
        hours, minutes = default.split(":")
        return time(int(hours), int(minutes))


def next_occurrence(hhmm: str, from_dt: datetime | None = None) -> datetime:
    """Prochaine occurrence d'une heure donnée (utilisée par les rappels)."""
    now = from_dt or timezone.localtime()
    target = reminder_time(hhmm)
    candidate = timezone.make_aware(datetime.combine(now.date(), target)) if timezone.is_naive(now) else \
        datetime.combine(now.date(), target, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate
