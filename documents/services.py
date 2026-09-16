"""Services documents : dépôt, versions, corbeille, quota, verrouillage, visibilité."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from core import permissions
from core.models import Setting
from documents.models import ACCEPTED, REFUSED, Category, CategoryAccess, Document, DocumentFile


class UploadError(Exception):
    pass


def accepted_extensions() -> list[str]:
    return list(ACCEPTED)


def max_file_bytes() -> int:
    return int(Setting.value("quota", "max_file_mb", 10)) * 1024 * 1024


def validate_upload(name: str, size: int) -> str:
    """Refus explicites des exécutables + taille maximale par fichier."""
    ext = (Path(name).suffix or "").lstrip(".").lower()
    if ext in REFUSED:
        raise UploadError(
            _("Le format « .%(ext)s » n'est pas autorisé. Formats acceptés : %(liste)s.")
            % {"ext": ext, "liste": ", ".join("." + item for item in ACCEPTED)}
        )
    if ext not in ACCEPTED:
        raise UploadError(
            _("Le format « .%(ext)s » n'est pas autorisé. Formats acceptés : %(liste)s.")
            % {"ext": ext or "?", "liste": ", ".join("." + item for item in ACCEPTED)}
        )
    limit = max_file_bytes()
    if size > limit:
        raise UploadError(
            _("Fichier trop volumineux (%(taille)s Mo) : la limite est de %(limite)s Mo.")
            % {"taille": round(size / 1048576, 1), "limite": int(limit / 1048576)}
        )
    return ext


def quota_usage() -> dict:
    from core.services import quota_usage as global_usage

    return global_usage()


def check_quota(size: int) -> None:
    from core.services import check_quota as global_check

    ok, message = global_check(size)
    if not ok:
        raise UploadError(message)


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def store_version(document: Document, upload, user, comment: str = "") -> DocumentFile:
    """Crée une nouvelle version, la marque courante, purge au-delà du nombre conservé."""
    content = upload.read()
    ext = validate_upload(upload.name, len(content))
    check_quota(len(content))
    digest = sha256_of(content)
    version_number = (document.versions.count() + 1)
    record = DocumentFile(
        document=document, original_name=upload.name[:240], ext=ext, size=len(content),
        sha256=digest, version=version_number, comment=comment[:240], uploaded_by=user,
    )
    record.file.save("%s-v%d.%s" % (slugify(document.title)[:60] or "document", version_number, ext),
                     ContentFile(content), save=False)
    record.save()
    document.versions.filter(is_current=True).update(is_current=False)
    record.is_current = True
    record.save(update_fields=["is_current"])
    document.current = record
    document.updated_at = timezone.now()
    document.save(update_fields=["current", "updated_at"])
    purge_old_versions(int(Setting.value("quota", "versions_kept", 3)), document=document)
    return record


def purge_old_versions(kept: int, document: Document | None = None, dry_run: bool = False) -> int:
    kept = max(1, int(kept or 1))
    queryset = DocumentFile.objects.filter(is_current=False)
    if document is not None:
        queryset = queryset.filter(document=document)
    removed = 0
    for doc_id in set(queryset.values_list("document_id", flat=True)):
        versions = list(DocumentFile.objects.filter(document_id=doc_id, is_current=False).order_by("-version"))
        for stale in versions[max(0, kept - 1):]:
            removed += 1
            if not dry_run:
                if stale.file:
                    stale.file.delete(save=False)
                stale.delete()
    return removed


def soft_delete(document: Document, user, reason: str = "") -> None:
    document.deleted_at = timezone.now()
    document.deleted_by = user
    document.delete_reason = reason[:240]
    document.save(update_fields=["deleted_at", "deleted_by", "delete_reason"])


def restore(document: Document) -> None:
    document.deleted_at = None
    document.deleted_by = None
    document.delete_reason = ""
    document.save(update_fields=["deleted_at", "deleted_by", "delete_reason"])


def purge_trash(days: int = 30, dry_run: bool = False) -> int:
    limit = timezone.now() - timezone.timedelta(days=days)
    count = 0
    for document in Document.objects.filter(deleted_at__lt=limit):
        count += 1
        if not dry_run:
            for version in document.versions.all():
                if version.file:
                    version.file.delete(save=False)
            document.delete()
    return count


def restore_version(document: Document, version: DocumentFile, user) -> DocumentFile:
    """Restauration non destructive : recopie la version en nouvelle version."""
    content = version.file.read()
    record = DocumentFile(
        document=document, original_name=version.original_name, ext=version.ext, size=len(content),
        sha256=version.sha256, version=document.versions.count() + 1,
        comment=_("Restauration de la version %(v)s") % {"v": version.version}, uploaded_by=user,
    )
    record.file.save("%s-v%d.%s" % (slugify(document.title)[:60] or "document", record.version, record.ext),
                     ContentFile(content), save=False)
    record.save()
    document.versions.filter(is_current=True).update(is_current=False)
    record.is_current = True
    record.save(update_fields=["is_current"])
    document.current = record
    document.save(update_fields=["current", "updated_at"])
    return record


def ensure_default_categories(user=None) -> list[Category]:
    created = []
    for index, (name, description, color, icon) in enumerate(
        __import__("documents.models", fromlist=["DEFAULT_CATEGORIES"]).DEFAULT_CATEGORIES
    ):
        category, was_created = Category.objects.get_or_create(
            name=name, defaults={"description": description, "color": color, "icon": icon,
                                 "order": 10 + index * 10, "created_by": user},
        )
        if was_created:
            created.append(category)
    return created


def can_view_category(user, category: Category) -> bool:
    if not permissions.can_view(user, "documents"):
        return False
    restrictions = category.accesses.select_related("role")
    if not restrictions.exists():
        return not category.locked_read or permissions.fine(user, "documents.categories") \
            or permissions.can_edit(user, "documents")
    role = getattr(user, "role", None)
    if permissions.is_administrator(user):
        return True
    access = restrictions.filter(role=role).first()
    if access is None:
        return False
    if category.locked_read and not (access.level >= 2 and access.can_delete):
        return permissions.fine(user, "documents.categories")
    return access.level >= 1


def can_edit_category(user, category: Category) -> bool:
    if permissions.is_administrator(user):
        return True
    restrictions = category.accesses.select_related("role")
    if restrictions.exists():
        access = restrictions.filter(role=getattr(user, "role", None)).first()
        return bool(access and access.level >= 2)
    return permissions.can_edit(user, "documents")


def can_delete_document(user, document: Document) -> bool:
    if permissions.is_administrator(user):
        return True
    if not permissions.fine(user, "documents.delete"):
        return False
    access = document.category.accesses.filter(role=getattr(user, "role", None)).first()
    if access is not None:
        return bool(access.can_delete)
    return permissions.can_edit(user, "documents")


def media_path(document_file: DocumentFile) -> str:
    return document_file.file.name


def log_view(document: Document, user, action: str, request=None) -> None:
    from documents.models import DocumentViewLog

    DocumentViewLog.objects.create(document=document, user=user if getattr(user, "pk", None) else None,
                                   action=action, ip=getattr(request, "client_ip", None))
    if action == "download":
        Document.objects.filter(pk=document.pk).update(downloads=document.downloads + 1)
    else:
        Document.objects.filter(pk=document.pk).update(views=document.views + 1)
