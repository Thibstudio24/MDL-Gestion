"""Documents : catégories, dossiers (2 niveaux), fichiers versionnés, corbeille, quota."""
from __future__ import annotations

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from core.permissions import LEVEL_CHOICES

ACCEPTED = ["pdf", "doc", "docx", "xls", "xlsx", "ods", "odt", "odp", "png", "jpg", "jpeg",
            "webp", "gif", "txt", "csv", "zip"]
REFUSED = ["exe", "dll", "sh", "bat", "js", "jar", "apk", "msi", "com", "scr", "cmd", "ps1", "vbs"]
PREVIEWABLE = ["pdf", "png", "jpg", "jpeg", "webp", "gif"]

DEFAULT_CATEGORIES = [
    ("Comptes rendus", "Comptes rendus de réunion du bureau et des assemblées.", "#33556e", "file"),
    ("Fiches clubs", "Un sous-dossier par club (créé à la main).", "#a76a43", "folder"),
    ("Documents administratifs", "Statuts, récépissés, assurances, conventions.", "#2c6f52", "shield"),
    ("Bilans", "Bilans de trésorerie générés automatiquement.", "#96700f", "chart"),
]


class Category(models.Model):
    name = models.CharField(_("nom"), max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.CharField(_("description"), max_length=240, blank=True)
    color = models.CharField(_("couleur"), max_length=9, default="#33556e")
    icon = models.CharField(_("icône"), max_length=24, default="folder")
    order = models.PositiveIntegerField(_("ordre"), default=100)
    locked_read = models.BooleanField(_("verrouillée en lecture"), default=False)
    archived = models.BooleanField(_("archivée"), default=False)
    allow_download = models.BooleanField(_("téléchargement autorisé"), default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Catégorie")
        verbose_name_plural = _("Catégories")
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or "categorie"
        super().save(*args, **kwargs)

    @property
    def document_count(self) -> int:
        return self.documents.filter(deleted_at__isnull=True).count()

    @property
    def size(self) -> int:
        return sum(version.size or 0 for version in DocumentFile.objects.filter(document__category=self))


class CategoryAccess(models.Model):
    """Restriction de visibilité par rôle (sinon : niveau du module documents)."""

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="accesses")
    role = models.ForeignKey("accounts.Role", on_delete=models.CASCADE, related_name="document_accesses")
    level = models.PositiveSmallIntegerField(_("niveau"), choices=LEVEL_CHOICES, default=1)
    can_delete = models.BooleanField(_("peut supprimer"), default=False)

    class Meta:
        verbose_name = _("Accès à une catégorie")
        verbose_name_plural = _("Accès aux catégories")
        unique_together = [("category", "role")]

    def __str__(self) -> str:
        return "%s — %s : %s" % (self.category.name, self.role.name, self.level)


class Folder(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="folders")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    name = models.CharField(_("nom"), max_length=140)
    description = models.CharField(_("description"), max_length=240, blank=True)
    locked_read = models.BooleanField(_("verrouillé en lecture"), default=False)
    order = models.PositiveIntegerField(_("ordre"), default=100)

    class Meta:
        verbose_name = _("Dossier")
        verbose_name_plural = _("Dossiers")
        ordering = ["order", "name"]
        unique_together = [("category", "parent", "name")]

    def __str__(self) -> str:
        return self.name

    @property
    def depth(self) -> int:
        return 1 if self.parent_id is None else 2

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.parent and self.parent.parent_id is not None:
            raise ValidationError(_("Deux niveaux de dossiers au maximum."))


class DocumentQuerySet(models.QuerySet):
    def live(self):
        return self.filter(deleted_at__isnull=True)

    def trashed(self):
        return self.filter(deleted_at__isnull=False)


class Document(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="documents")
    folder = models.ForeignKey(Folder, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    title = models.CharField(_("titre"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    tags = models.JSONField(_("étiquettes"), default=list, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="owned_documents")
    current = models.ForeignKey("DocumentFile", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    locked = models.BooleanField(_("verrouillé"), default=False)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    locked_at = models.DateTimeField(null=True, blank=True)
    downloads = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    offline_cacheable = models.BooleanField(_("consultable hors ligne"), default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    delete_reason = models.CharField(_("motif de suppression"), max_length=240, blank=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        verbose_name = _("Document")
        verbose_name_plural = _("Documents")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def ext(self) -> str:
        return self.current.ext if self.current else ""

    @property
    def size(self) -> int:
        return self.current.size if self.current else 0

    @property
    def is_previewable(self) -> bool:
        return self.ext in PREVIEWABLE

    @property
    def is_locked(self) -> bool:
        return bool(self.locked or self.category.locked_read or (self.folder and self.folder.locked_read))

    def purge_due(self) -> bool:
        return bool(self.deleted_at and self.deleted_at < timezone.now() - timezone.timedelta(days=30))


class DocumentFile(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    file = models.FileField(upload_to="documents/%Y/%m/",
                            validators=[FileExtensionValidator(ACCEPTED)])
    original_name = models.CharField(_("nom d'origine"), max_length=240, blank=True)
    ext = models.CharField(_("extension"), max_length=12, blank=True)
    size = models.PositiveIntegerField(_("taille (octets)"), default=0)
    sha256 = models.CharField(_("empreinte"), max_length=64, blank=True)
    version = models.PositiveIntegerField(_("version"), default=1)
    comment = models.CharField(_("commentaire"), max_length=240, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    uploaded_at = models.DateTimeField(default=timezone.now)
    is_current = models.BooleanField(_("version courante"), default=False)

    class Meta:
        verbose_name = _("Version de document")
        verbose_name_plural = _("Versions de document")
        ordering = ["-version"]

    def __str__(self) -> str:
        return "%s v%s" % (self.document.title, self.version)


class DocumentViewLog(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="view_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    action = models.CharField(_("action"), max_length=12, choices=[("view", _("consultation")),
                                                                   ("download", _("téléchargement"))])
    at = models.DateTimeField(default=timezone.now)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = _("Consultation")
        verbose_name_plural = _("Consultations")
        ordering = ["-at"]

    def __str__(self) -> str:
        return "%s — %s" % (self.document.title, self.action)
