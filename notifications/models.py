"""Notifications in-app, abonnements push et préférences par membre."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

LEVELS = [("info", _("info")), ("success", _("succès")), ("warning", _("avertissement")), ("danger", _("danger"))]
CHANNELS = [("inapp", _("Dans l'app")), ("email", _("E-mail")), ("push", _("Push"))]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(_("événement"), max_length=32, db_index=True)
    title = models.CharField(_("titre"), max_length=160)
    body = models.TextField(_("corps"), blank=True)
    url = models.CharField(_("lien profond"), max_length=240, blank=True)
    level = models.CharField(_("niveau"), max_length=8, choices=LEVELS, default="info")
    email_sent = models.BooleanField(_("e-mail envoyé"), default=False)
    push_sent = models.BooleanField(_("push envoyé"), default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self) -> str:
        return "%s — %s" % (self.user.email, self.title)

    @property
    def is_read(self) -> bool:
        return bool(self.read_at)


class PushDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_devices")
    endpoint = models.URLField(max_length=500, unique=True)
    keys = models.JSONField(_("clés p256dh / auth"), default=dict, blank=True)
    ua = models.CharField(_("navigateur"), max_length=240, blank=True)
    label = models.CharField(_("étiquette"), max_length=80, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_success = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(default=0)
    disabled = models.BooleanField(_("désactivé"), default=False)

    class Meta:
        verbose_name = _("Appareil abonné")
        verbose_name_plural = _("Appareils abonnés")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return "%s — %s" % (self.user.email, self.label or self.endpoint[:40])


class NotificationPreference(models.Model):
    """Surcouche par membre : null = suivre le réglage général."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_prefs")
    kind = models.CharField(_("événement"), max_length=32)
    inapp = models.BooleanField(_("dans l'app"), null=True, blank=True, default=None)
    email = models.BooleanField(_("e-mail"), null=True, blank=True, default=None)
    push = models.BooleanField(_("push"), null=True, blank=True, default=None)

    class Meta:
        verbose_name = _("Préférence de notification")
        verbose_name_plural = _("Préférences de notification")
        unique_together = [("user", "kind")]

    def __str__(self) -> str:
        return "%s — %s" % (self.user.email, self.kind)
