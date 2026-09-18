"""Planning de la salle : campagnes de disponibilités, créneaux, réponses des membres."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

WEEKS = [("Q1", _("Premier trimestre")), ("Q2", _("Deuxième trimestre")), ("Q3", _("Troisième trimestre")),
         ("S1", _("Premier semestre")), ("S2", _("Second semestre")), ("AN", _("Année entière"))]
CHOICES = [("yes", _("Disponible")), ("maybe", _("Si besoin")), ("no", _("Indisponible"))]
DAYS = [(1, _("lundi")), (2, _("mardi")), (3, _("mercredi")), (4, _("jeudi")), (5, _("vendredi")),
        (6, _("samedi")), (0, _("dimanche"))]


class Campaign(models.Model):
    """Une campagne = une période pendant laquelle les membres indiquent leurs disponibilités."""

    label = models.CharField(_("libellé"), max_length=140)
    description = models.TextField(_("description"), blank=True)
    year = models.ForeignKey("core.SchoolYear", on_delete=models.CASCADE, related_name="planning_campaigns")
    week = models.CharField(_("période"), max_length=2, choices=WEEKS, default="Q1")
    start_date = models.DateField(_("ouverture"))
    end_date = models.DateField(_("clôture des réponses"))
    slot_duration = models.PositiveSmallIntegerField(_("durée d'un créneau (minutes)"), default=60)
    published = models.BooleanField(_("publiée"), default=False)
    closed = models.BooleanField(_("clôturée"), default=False)
    reminder_sent_at = models.DateTimeField(_("rappel envoyé le"), null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Campagne de disponibilités")
        verbose_name_plural = _("Campagnes de disponibilités")
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return self.label

    @property
    def is_open(self) -> bool:
        today = timezone.localdate()
        return self.published and not self.closed and self.start_date <= today <= self.end_date


class Slot(models.Model):
    """Un créneau à couvrir : jour, heure, capacité."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="slots")
    weekday = models.PositiveSmallIntegerField(_("jour"), choices=DAYS)
    start_time = models.TimeField(_("début"))
    end_time = models.TimeField(_("fin"))
    capacity = models.PositiveSmallIntegerField(_("nombre de gérants"), default=1)
    label = models.CharField(_("intitulé"), max_length=140, blank=True,
                             help_text=_("Ex. : permanence midi, ouverture du foyer."))
    order = models.PositiveIntegerField(_("ordre"), default=100)

    class Meta:
        verbose_name = _("Créneau")
        verbose_name_plural = _("Créneaux")
        ordering = ["weekday", "start_time"]

    def __str__(self) -> str:
        return "%s %s–%s" % (self.get_weekday_display().capitalize(),
                             self.start_time.strftime("%H:%M"), self.end_time.strftime("%H:%M"))


class Availability(models.Model):
    """Réponse d'un membre à un créneau."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="availabilities")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availabilities")
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name="availabilities")
    choice = models.CharField(_("réponse"), max_length=6, choices=CHOICES, default="yes")
    note = models.CharField(_("note"), max_length=240, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Disponibilité")
        verbose_name_plural = _("Disponibilités")
        unique_together = [("campaign", "member", "slot")]
        ordering = ["slot__weekday", "slot__start_time"]

    def __str__(self) -> str:
        return "%s — %s — %s" % (self.member, self.slot, self.get_choice_display())
