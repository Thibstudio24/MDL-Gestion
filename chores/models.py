"""Planning de ménage : campagnes, tâches attribuées, preuves photographiques."""
from __future__ import annotations

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

STATUSES = [("todo", _("à faire")), ("done", _("fait, à valider")), ("validated", _("validé")),
            ("redo", _("à refaire"))]
CHOICES = [("accept", _("J'accepte")), ("decline", _("Je ne peux pas"))]
DAYS = [(1, _("lundi")), (2, _("mardi")), (3, _("mercredi")), (4, _("jeudi")), (5, _("vendredi")),
        (6, _("samedi")), (0, _("dimanche"))]
WEEKS = [("Q1", _("Premier trimestre")), ("Q2", _("Deuxième trimestre")), ("Q3", _("Troisième trimestre")),
         ("AN", _("Année entière"))]
DEFAULT_TASKS = ["Vider les poubelles", "Passer le balai", "Nettoyer les tables", "Ranger le matériel",
                 "Vérifier les fenêtres fermées"]


class Campaign(models.Model):
    label = models.CharField(_("libellé"), max_length=140)
    description = models.TextField(_("description"), blank=True)
    year = models.ForeignKey("core.SchoolYear", on_delete=models.CASCADE, related_name="chore_campaigns")
    week = models.CharField(_("période"), max_length=2, choices=WEEKS, default="Q1")
    start_date = models.DateField(_("début de la semaine"))
    end_date = models.DateField(_("fin de la semaine"))
    deadline = models.DateField(_("date limite de réponse"), null=True, blank=True)
    published = models.BooleanField(_("publiée"), default=False)
    closed = models.BooleanField(_("clôturée"), default=False)
    reminder_sent_at = models.DateTimeField(_("rappel envoyé le"), null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Campagne de ménage")
        verbose_name_plural = _("Campagnes de ménage")
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return self.label

    @property
    def is_open(self) -> bool:
        today = timezone.localdate()
        return self.published and not self.closed and today <= (self.deadline or self.end_date)


class Assignment(models.Model):
    """Une tâche attribuée à un membre pour une semaine donnée."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="assignments")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chore_assignments")
    week = models.CharField(_("semaine"), max_length=2, choices=WEEKS, default="Q1")
    weekday = models.PositiveSmallIntegerField(_("jour"), choices=DAYS, default=1)
    zone = models.CharField(_("lieu"), max_length=120, default="Local MDL")
    task = models.CharField(_("tâche"), max_length=160)
    status = models.CharField(_("état"), max_length=10, choices=STATUSES, default="todo", db_index=True)
    done_at = models.DateTimeField(_("fait le"), null=True, blank=True)
    proof = models.FileField(_("photo de preuve"), upload_to="menage/%Y/%m/", blank=True,
                             validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])])
    note = models.CharField(_("note"), max_length=240, blank=True)
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Tâche de ménage")
        verbose_name_plural = _("Tâches de ménage")
        ordering = ["weekday", "member__last_name"]

    def __str__(self) -> str:
        return "%s — %s (%s)" % (self.member, self.task, self.get_status_display())

    @property
    def is_late(self) -> bool:
        return self.status in ("todo", "redo") and timezone.localdate() > self.campaign.end_date


class Response(models.Model):
    """Réponse d'un membre à une campagne (accepte ou décline)."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="responses")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chore_responses")
    choice = models.CharField(_("réponse"), max_length=8, choices=CHOICES, default="accept")
    note = models.CharField(_("note"), max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Réponse de ménage")
        verbose_name_plural = _("Réponses de ménage")
        unique_together = [("campaign", "member")]

    def __str__(self) -> str:
        return "%s — %s" % (self.member, self.get_choice_display())
