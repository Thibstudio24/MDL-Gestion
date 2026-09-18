"""Trésorerie : grand livre unique, comptes, coffre, clôtures, imports, bilans."""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

KIND_CHOICES = [("D", _("Dépense")), ("R", _("Recette")), ("T", _("Transfert interne")),
                ("A", _("Ajustement d'écart"))]
ACCOUNT_TYPES = [("bank", _("Compte bancaire")), ("safe", _("Coffre-fort")), ("other", _("Autre"))]
MODES = [("especes", _("Espèces")), ("cheque", _("Chèque")), ("virement", _("Virement")),
         ("prelevement", _("Prélèvement")), ("carte", _("Carte")), ("cheques-vacances", _("Chèques-vacances")),
         ("autre", _("Autre"))]
SOURCES = [("manuel", _("Saisie manuelle")), ("import", _("Import")), ("coffre", _("Coffre")),
           ("reglage", _("Régularisation"))]
SAFE_MOVEMENTS = [("in", _("Argent mis dans le coffre")), ("bank", _("Dépôt à la banque")),
                  ("misc", _("Autre mouvement"))]

DEFAULT_EXPENSES = ["Fournitures", "Événements & animations", "Communication", "Documentation",
                    "Déplacements", "Restauration", "Autres"]
DEFAULT_INCOMES = ["Cotisations", "Subvention lycée", "Subvention mairie/collectivité",
                   "Vente d'événement", "Partenariat", "Divers"]
MONTHS = [("9", _("septembre")), ("10", _("octobre")), ("11", _("novembre")), ("12", _("décembre")),
          ("1", _("janvier")), ("2", _("février")), ("3", _("mars")), ("4", _("avril")),
          ("5", _("mai")), ("6", _("juin")), ("7", _("juillet")), ("8", _("août"))]


class Account(models.Model):
    name = models.CharField(_("nom"), max_length=120, unique=True)
    type = models.CharField(_("type"), max_length=8, choices=ACCOUNT_TYPES, default="bank")
    bank = models.CharField(_("banque"), max_length=120, blank=True)
    number = models.CharField(_("numéro"), max_length=60, blank=True)
    iban = models.CharField(_("IBAN"), max_length=40, blank=True)
    order = models.PositiveIntegerField(_("ordre"), default=100)
    active = models.BooleanField(_("actif"), default=True)
    is_safe = models.BooleanField(_("coffre (solde calculé)"), default=False)
    note = models.CharField(_("note"), max_length=240, blank=True)

    class Meta:
        verbose_name = _("Compte")
        verbose_name_plural = _("Comptes")
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def iban_masked(self) -> str:
        value = (self.iban or "").replace(" ", "")
        if len(value) <= 8:
            return value
        return "%s…%s" % (value[:4], value[-4:])


class AccountOpening(models.Model):
    """Solde d'ouverture par compte et par année scolaire."""

    year = models.ForeignKey("core.SchoolYear", on_delete=models.CASCADE, related_name="openings")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="openings")
    amount = models.DecimalField(_("montant"), max_digits=11, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = _("Solde d'ouverture")
        verbose_name_plural = _("Soldes d'ouverture")
        unique_together = [("year", "account")]

    def __str__(self) -> str:
        return "%s — %s" % (self.year.label, self.account.name)


class Category(models.Model):
    """Catégorie d'écriture (dépense ou recette), avec sous-catégorie optionnelle."""

    label = models.CharField(_("libellé"), max_length=120)
    code = models.CharField(_("code"), max_length=20, blank=True)
    kind = models.CharField(_("sens"), max_length=1, choices=[("D", _("Dépense")), ("R", _("Recette"))],
                            default="D")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    color = models.CharField(_("couleur"), max_length=9, default="#33556e")
    order = models.PositiveIntegerField(_("ordre"), default=100)
    active = models.BooleanField(_("active"), default=True)
    note = models.CharField(_("note"), max_length=240, blank=True)

    class Meta:
        verbose_name = _("Catégorie")
        verbose_name_plural = _("Catégories")
        ordering = ["kind", "order", "label"]

    def __str__(self) -> str:
        return self.label


class MonthLock(models.Model):
    """Verrou dur sur un mois : personne ne modifie, pas même l'admin sans réouverture."""

    year = models.ForeignKey("core.SchoolYear", on_delete=models.CASCADE, related_name="month_locks")
    month = models.PositiveSmallIntegerField(_("mois"), choices=MONTHS)
    year_number = models.PositiveIntegerField(_("année civile"))
    locked_at = models.DateTimeField(default=timezone.now)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    note = models.CharField(_("note"), max_length=240, blank=True)
    balance_document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="+")

    class Meta:
        verbose_name = _("Clôture mensuelle")
        verbose_name_plural = _("Clôtures mensuelles")
        unique_together = [("year", "month", "year_number")]
        ordering = ["-year_number", "-month"]

    def __str__(self) -> str:
        return "%s — %02d/%d" % (self.year.label, self.month, self.year_number)


class Entry(models.Model):
    """Grand livre : une seule table pour les écritures."""

    year = models.ForeignKey("core.SchoolYear", on_delete=models.PROTECT, related_name="entries")
    day = models.DateField(_("date"), db_index=True)
    title = models.CharField(_("libellé"), max_length=200)
    amount = models.DecimalField(_("montant"), max_digits=11, decimal_places=2)
    kind = models.CharField(_("sens"), max_length=1, choices=KIND_CHOICES, default="D", db_index=True)
    account = models.ForeignKey(Account, verbose_name=_("compte"), on_delete=models.PROTECT, related_name="entries")
    to_account = models.ForeignKey(Account, verbose_name=_("compte destinataire"), null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="incoming")
    category = models.ForeignKey(Category, verbose_name=_("catégorie"), null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="entries")
    subcategory = models.ForeignKey(Category, verbose_name=_("sous-catégorie"), null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="sub_entries")
    mode = models.CharField(_("mode de règlement"), max_length=20, choices=MODES, blank=True)
    third_party = models.CharField(_("tiers"), max_length=160, blank=True)
    reference = models.CharField(_("référence de pièce"), max_length=80, blank=True)
    note = models.TextField(_("note"), blank=True)
    support_file = models.FileField(_("justificatif"), upload_to="finance/%Y/%m/", blank=True,
                                    validators=[FileExtensionValidator(["pdf", "png", "jpg", "jpeg", "webp"])])
    support_document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="+")
    safe_movement = models.CharField(_("mouvement de coffre"), max_length=6, choices=SAFE_MOVEMENTS, blank=True)
    source = models.CharField(_("origine"), max_length=10, choices=SOURCES, default="manuel")
    import_batch = models.ForeignKey("ImportBatch", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="entries")
    month_lock = models.ForeignKey(MonthLock, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    transferred_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="transfer_pair")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="entries")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    delete_reason = models.CharField(_("motif de suppression"), max_length=240, blank=True)

    class Meta:
        verbose_name = _("Écriture")
        verbose_name_plural = _("Écritures")
        ordering = ["-day", "-id"]
        indexes = [models.Index(fields=["year", "day", "kind"])]

    def __str__(self) -> str:
        return "%s — %s — %s" % (self.day.strftime("%d/%m/%Y"), self.title, self.amount)

    @property
    def signed(self) -> Decimal:
        if self.kind == "R":
            return self.amount
        if self.kind == "D":
            return -self.amount
        return Decimal("0.00")


class CashCount(models.Model):
    """Comptage de caisse : théorique calculé, écart justifié, ajustement automatique."""

    year = models.ForeignKey("core.SchoolYear", on_delete=models.CASCADE, related_name="cash_counts")
    day = models.DateField(_("date"))
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="cash_counts")
    expected = models.DecimalField(_("théorique"), max_digits=11, decimal_places=2, default=Decimal("0.00"))
    counted = models.DecimalField(_("compté"), max_digits=11, decimal_places=2, default=Decimal("0.00"))
    reason = models.CharField(_("motif de l'écart"), max_length=240, blank=True)
    adjustment = models.ForeignKey(Entry, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Comptage de caisse")
        verbose_name_plural = _("Comptages de caisse")
        ordering = ["-day"]

    def __str__(self) -> str:
        return "Comptage du %s" % self.day.strftime("%d/%m/%Y")

    @property
    def delta(self) -> Decimal:
        return self.counted - self.expected


class ImportBatch(models.Model):
    file_name = models.CharField(_("fichier"), max_length=240)
    year = models.ForeignKey("core.SchoolYear", on_delete=models.CASCADE, related_name="import_batches")
    rows_total = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    rows_error = models.PositiveIntegerField(default=0)
    report = models.JSONField(_("rapport"), default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        verbose_name = _("Import")
        verbose_name_plural = _("Imports")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return "%s (%s lignes)" % (self.file_name, self.rows_created)


class BalanceRun(models.Model):
    """Un classeur par année scolaire, régénéré à chaque échéance."""

    STATUSES = [("ok", _("généré")), ("partial", _("partiel")), ("failed", _("échoué"))]

    year = models.ForeignKey("core.SchoolYear", on_delete=models.CASCADE, related_name="balance_runs")
    up_to_month = models.PositiveSmallIntegerField(_("mois d'arrêt"), default=1)
    auto = models.BooleanField(_("généré par le cron"), default=False)
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    workbook = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    months = models.JSONField(_("mois inclus"), default=list, blank=True)
    stats = models.JSONField(_("statistiques"), default=dict, blank=True)
    status = models.CharField(_("état"), max_length=10, choices=STATUSES, default="ok")
    message = models.CharField(_("message"), max_length=240, blank=True)

    class Meta:
        verbose_name = _("Génération de bilan")
        verbose_name_plural = _("Générations de bilan")
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return "Bilan %s (jusqu'à %02d)" % (self.year.label, self.up_to_month)
