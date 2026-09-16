"""Messagerie interne descendante et file d'attente SMTP (pas de remontée de messages)."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

KINDS = [("info", _("Information")), ("important", _("Important")), ("alert", _("Alerte")),
         ("bilan", _("Bilan")), ("planning", _("Planning")), ("menage", _("Ménage")),
         ("technique", _("Technique"))]
AUDIENCES = [("all", _("Tous les membres actifs")), ("board", _("Bureau uniquement")),
             ("role", _("Rôles choisis")), ("manual", _("Liste manuelle"))]
STATUSES = [("draft", _("Brouillon")), ("scheduled", _("Programmé")), ("sent", _("Envoyé")),
            ("cancelled", _("Annulé"))]
OUTBOX_STATUSES = [("queued", _("En attente")), ("sent", _("Envoyé")), ("failed", _("Échec")),
                   ("skipped", _("Ignoré"))]


class Broadcast(models.Model):
    """Un message du bureau vers les membres. Descendant uniquement."""

    subject = models.CharField(_("objet"), max_length=160)
    body = models.TextField(_("message"), help_text=_("Markdown léger accepté."))
    kind = models.CharField(_("type"), max_length=10, choices=KINDS, default="info")
    audience = models.CharField(_("destinataires"), max_length=8, choices=AUDIENCES, default="all")
    roles = models.ManyToManyField("accounts.Role", blank=True, related_name="broadcasts")
    requires_ack = models.BooleanField(_("accusé de lecture demandé"), default=False)
    notify_email = models.BooleanField(_("doublé par courriel"), default=True)
    scheduled_at = models.DateTimeField(_("envoi programmé"), null=True, blank=True)
    sent_at = models.DateTimeField(_("envoyé le"), null=True, blank=True)
    status = models.CharField(_("état"), max_length=10, choices=STATUSES, default="draft", db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="broadcasts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Diffusion")
        verbose_name_plural = _("Diffusions")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.subject

    @property
    def is_pending(self) -> bool:
        return self.status in ("draft", "scheduled")


class Recipient(models.Model):
    """Un destinataire d'une diffusion, avec lecture et accusé."""

    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages")
    read_at = models.DateTimeField(_("lu le"), null=True, blank=True)
    ack_at = models.DateTimeField(_("accusé le"), null=True, blank=True)
    archived_at = models.DateTimeField(_("archivé le"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Destinataire")
        verbose_name_plural = _("Destinataires")
        unique_together = [("broadcast", "user")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return "%s — %s" % (self.user, self.broadcast)


class Outbox(models.Model):
    """File d'attente SMTP en base : le cron vide la file, pas de Celery."""

    to_email = models.EmailField(_("destinataire"))
    recipient_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="+")
    subject = models.CharField(_("objet"), max_length=200)
    text_body = models.TextField(_("corps texte"))
    kind = models.CharField(_("type"), max_length=20, blank=True)
    urgent = models.BooleanField(_("urgent"), default=False)
    status = models.CharField(_("état"), max_length=8, choices=OUTBOX_STATUSES, default="queued", db_index=True)
    attempts = models.PositiveSmallIntegerField(_("tentatives"), default=0)
    error = models.CharField(_("erreur"), max_length=400, blank=True)
    queued_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Courriel en attente")
        verbose_name_plural = _("Courriels en attente")
        ordering = ["-urgent", "queued_at"]

    def __str__(self) -> str:
        return "%s — %s" % (self.to_email, self.subject)
