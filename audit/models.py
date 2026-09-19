"""Journal d'audit : jamais modifiable ni supprimable depuis l'interface."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

LEVELS = [("info", _("info")), ("warn", _("avertissement")), ("danger", _("danger"))]
ORIGINS = [("web", "Web"), ("cli", "CLI"), ("hub", "Hub"), ("cron", "Cron")]

ACTIONS = [
    "auth.login", "auth.logout", "auth.login_failed", "auth.locked", "auth.password_changed",
    "auth.password_reset", "auth.reauth", "auth.2fa_enabled", "auth.2fa_disabled", "auth.2fa_recovery_used",
    "member.created", "member.updated", "member.invited", "member.invitation_resent", "member.invitation_revoked",
    "member.role_changed", "member.deactivated", "member.reactivated", "member.anonymized",
    "member.deleted", "settings.site_reset",
    "member.unlocked", "member.exported", "member.2fa_reset",
    "role.created", "role.updated", "role.deleted", "role.permissions_changed", "role.exported", "role.imported",
    "document.uploaded", "document.updated", "document.version_restored", "document.deleted",
    "document.restored", "document.purged", "document.viewed", "document.downloaded",
    "document.category_created", "document.category_updated", "document.category_deleted",
    "document.category_locked", "document.category_forced", "document.quota_alert",
    "finance.entry_created", "finance.entry_updated", "finance.entry_deleted", "finance.entry_duplicated",
    "finance.month_locked", "finance.month_unlocked", "finance.cash_count", "finance.import",
    "finance.import_reverted", "finance.balance_generated", "finance.balance_failed",
    "finance.account_updated", "finance.exported",
    "planning.campaign_created", "planning.campaign_updated", "planning.campaign_closed",
    "planning.campaign_deleted",
    "planning.availability_saved", "planning.published", "planning.reminder_sent",
    "planning.swap_requested", "planning.swap_answered", "planning.slot_assigned",
    "chores.campaign_created", "chores.campaign_published", "chores.campaign_deleted",
    "chores.response_saved", "chores.generated", "chores.task_added", "chores.task_deleted",
    "chores.assignment_updated", "chores.assignment_validated", "chores.assignment_redo", "chores.proof_deleted",
    "mail.broadcast_created", "mail.broadcast_sent", "mail.broadcast_scheduled", "mail.broadcast_cancelled",
    "mail.reminder_sent", "mail.read", "mail.test_sent", "mail.outbox_drained",
    "settings.brand_updated", "settings.quota_updated", "settings.security_updated", "settings.smtp_updated",
    "settings.push_updated", "settings.matrix_updated", "settings.year_created", "settings.year_locked",
    "settings.year_unlocked", "settings.legal_updated", "settings.maintenance", "settings.backup_created",
    "settings.backup_restored", "settings.backup_deleted", "settings.update_applied",
    "settings.audit_cleared",
    "devhub.intervention_applied", "devhub.intervention_revoked", "devhub.token_applied", "devhub.ping",
]


ACTION_CHOICES = [(code, code) for code in ACTIONS]


class AuditEntry(models.Model):
    at = models.DateTimeField(_("horodatage"), default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_label = models.CharField(_("auteur figé"), max_length=190, blank=True)
    action = models.CharField(_("action"), max_length=64, choices=ACTION_CHOICES, db_index=True)
    module = models.CharField(_("module"), max_length=32, blank=True)
    model_name = models.CharField(_("modèle"), max_length=64, blank=True)
    object_id = models.CharField(_("objet"), max_length=64, blank=True)
    object_repr = models.CharField(_("libellé de l'objet"), max_length=240, blank=True)
    message = models.CharField(_("message"), max_length=400, blank=True)
    changes = models.JSONField(_("avant / après"), default=dict, blank=True)
    level = models.CharField(_("gravité"), max_length=8, choices=LEVELS, default="info")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=240, blank=True)
    origin = models.CharField(_("origine"), max_length=8, choices=ORIGINS, default="web")

    class Meta:
        verbose_name = _("Ligne d'audit")
        verbose_name_plural = _("Journal d'audit")
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["module", "action"]), models.Index(fields=["level"])]

    def __str__(self) -> str:
        return "%s — %s — %s" % (self.at.strftime("%d/%m/%Y %H:%M"), self.action, self.actor_label)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Une ligne d'audit ne peut pas être modifiée.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Une ligne d'audit ne peut pas être supprimée depuis l'interface.")
