"""Écrans documents : navigation, dépôt, versions, corbeille, catégories, aperçu privé."""
from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from audit.services import log
from core import permissions
from core.decorators import fine_required, module_required, reauth_required
from documents import services
from documents.forms import (
    CategoryAccessForm,
    CategoryDeleteForm,
    CategoryForm,
    DocumentForm,
    FolderForm,
    ReplaceForm,
    UploadForm,
)
from documents.models import ACCEPTED, Category, Document, DocumentFile, Folder


def _visible_categories(user):
    return [category for category in Category.objects.filter(archived=False)
            if services.can_view_category(user, category)]


def _documents_for(user, category=None, folder=None):
    queryset = Document.objects.live().select_related("category", "folder", "current", "owner")
    if category is not None:
        queryset = queryset.filter(category=category)
    if folder is not None:
        queryset = queryset.filter(folder=folder)
    allowed = [category.pk for category in _visible_categories(user)]
    return queryset.filter(category_id__in=allowed)


@module_required("documents")
def list_view(request):
    categories = _visible_categories(request.user)
    category = None
    folder = None
    if request.GET.get("categorie"):
        category = get_object_or_404(Category, pk=request.GET["categorie"])
        if not services.can_view_category(request.user, category):
            raise PermissionDenied(_("Cette catégorie est verrouillée en lecture."))
    if request.GET.get("dossier"):
        folder = get_object_or_404(Folder, pk=request.GET["dossier"])
        category = folder.category
    queryset = _documents_for(request.user, category, folder)
    query = request.GET.get("q", "").strip()
    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(description__icontains=query)
                                   | Q(tags__icontains=query))
    if request.GET.get("etiquette"):
        queryset = queryset.filter(tags__icontains=request.GET["etiquette"])
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    usage = services.quota_usage()
    form = UploadForm(initial={"category": category}) if permissions.can_edit(request.user, "documents") else None
    if form is not None:
        form.fields["category"].queryset = Category.objects.filter(archived=False)
        form.fields["folder"].queryset = Folder.objects.filter(category=category) if category else Folder.objects.all()
    return render(request, "documents/list.html", {
        "page_obj": page, "categories": categories, "category": category, "folder": folder,
        "folders": Folder.objects.filter(category=category, parent__isnull=True) if category else [],
        "form": form, "query": query, "usage": usage,
        "accepted": ACCEPTED,
        "can_edit": permissions.can_edit(request.user, "documents"),
        "can_delete": permissions.fine(request.user, "documents.delete"),
        "can_manage_categories": permissions.fine(request.user, "documents.categories"),
        "page_title": "Documents",
    })


@module_required("documents", edit=True)
@require_POST
def upload(request):
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        for _field, errors in form.errors.items():
            for error in errors:
                messages.error(request, "%s" % error)
        return redirect("documents:documents_list")
    category = form.cleaned_data["category"]
    if not services.can_edit_category(request.user, category):
        messages.error(request, _("Cette catégorie est verrouillée en lecture."))
        return redirect("documents:documents_list")
    created = []
    for upload_file in form.cleaned_data["files"]:
        title = form.cleaned_data["title"] or Path(upload_file.name).stem.replace("-", " ").replace("_", " ")
        document = Document.objects.create(
            category=category, folder=form.cleaned_data["folder"], title=title[:200],
            description=form.cleaned_data["description"], tags=form.cleaned_data["tags"], owner=request.user,
        )
        try:
            services.store_version(document, upload_file, request.user, form.cleaned_data["comment"])
        except services.UploadError as exc:
            document.delete()
            messages.error(request, str(exc))
            continue
        log(request.user, "document.uploaded", "documents", document,
            "Document déposé : %s" % document.title, request=request)
        created.append(document)
    if created:
        messages.success(request, _("%(n)s document(s) déposé(s).") % {"n": len(created)})
        if len(created) == 1:
            return redirect("documents:detail", pk=created[0].pk)
    return redirect("documents:documents_list")


@module_required("documents")
def detail(request, pk: int):
    document = get_object_or_404(Document.objects.select_related("category", "folder", "current", "owner"), pk=pk)
    if document.deleted_at is not None and not permissions.can_edit(request.user, "documents"):
        raise Http404
    if not services.can_view_category(request.user, document.category):
        raise PermissionDenied(_("Cette catégorie est verrouillée en lecture."))
    services.log_view(document, request.user, "view", request)
    replace_form = ReplaceForm() if permissions.can_edit(request.user, "documents") else None
    edit_form = DocumentForm(instance=document) if permissions.can_edit(request.user, "documents") else None
    return render(request, "documents/detail.html", {
        "document": document, "versions": document.versions.all(),
        "replace_form": replace_form, "edit_form": edit_form,
        "can_edit": permissions.can_edit(request.user, "documents"),
        "can_delete": services.can_delete_document(request.user, document),
        "logs": document.view_logs.select_related("user")[:20],
        "page_title": document.title,
    })


@module_required("documents", edit=True)
@require_POST
def replace(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    if document.is_locked and not permissions.fine(request.user, "documents.categories"):
        messages.error(request, _("Ce document est verrouillé : seul un gestionnaire de catégories peut forcer."))
        return redirect("documents:detail", pk=pk)
    form = ReplaceForm(request.POST, request.FILES)
    if not form.is_valid():
        for error in form.errors.get("file", []):
            messages.error(request, error)
        return redirect("documents:detail", pk=pk)
    try:
        record = services.store_version(document, form.cleaned_data["file"], request.user,
                                        form.cleaned_data["comment"])
    except services.UploadError as exc:
        messages.error(request, str(exc))
        return redirect("documents:detail", pk=pk)
    log(request.user, "document.updated", "documents", document,
        "Nouvelle version %s" % record.version, request=request)
    messages.success(request, _("Version %(v)s déposée.") % {"v": record.version})
    return redirect("documents:detail", pk=pk)


@module_required("documents", edit=True)
@require_POST
def edit(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    form = DocumentForm(request.POST, instance=document)
    if form.is_valid():
        previous = {"titre": document.title, "categorie": document.category.name}
        saved = form.save()
        log(request.user, "document.updated", "documents", saved, "Document modifié",
            previous=previous, current={"titre": saved.title, "categorie": saved.category.name}, request=request)
        messages.success(request, _("Document enregistré."))
    else:
        for error in form.errors.values():
            messages.error(request, error[0])
    return redirect("documents:detail", pk=pk)


@module_required("documents", edit=True)
@require_POST
def restore_version(request, pk: int, version_id: int):
    document = get_object_or_404(Document, pk=pk)
    version = get_object_or_404(DocumentFile, pk=version_id, document=document)
    record = services.restore_version(document, version, request.user)
    log(request.user, "document.version_restored", "documents", document,
        "Version %s restaurée en version %s" % (version.version, record.version), request=request)
    messages.success(request, _("Version %(v)s recopiée en version %(new)s.")
                     % {"v": version.version, "new": record.version})
    return redirect("documents:detail", pk=pk)


@fine_required("documents.delete", "documents")
@require_POST
def soft_delete(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    if not services.can_delete_document(request.user, document):
        raise PermissionDenied(_("Droit de suppression manquant."))
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, _("Un motif est obligatoire pour supprimer un document."))
        return redirect("documents:detail", pk=pk)
    services.soft_delete(document, request.user, reason)
    messages.success(request, _("Document mis à la corbeille (30 jours avant purge)."))
    return redirect("documents:documents_list")


@module_required("documents", edit=True)
@require_POST
def restore_document(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    services.restore(document, request.user)
    messages.success(request, _("Document restauré."))
    return redirect("documents:trash")


@module_required("documents")
def trash(request):
    allowed = [category.pk for category in _visible_categories(request.user)]
    queryset = Document.objects.trashed().filter(category_id__in=allowed).select_related("category", "owner")
    return render(request, "documents/trash.html", {
        "documents": queryset[:100], "page_title": "Corbeille",
        "can_edit": permissions.can_edit(request.user, "documents"),
    })


@module_required("documents", edit=True)
@require_POST
def empty_trash(request):
    count = services.purge_trash(0)
    log(request.user, "document.purged", "documents", None, "Corbeille vidée (%d documents)" % count,
        level="warn", request=request)
    messages.success(request, _("Corbeille vidée : %(n)s document(s) supprimé(s).") % {"n": count})
    return redirect("documents:trash")


@module_required("documents")
def download(request, pk: int, version_id: int | None = None):
    document = get_object_or_404(Document.objects.select_related("category"), pk=pk)
    if not services.can_view_category(request.user, document.category):
        raise PermissionDenied(_("Cette catégorie est verrouillée en lecture."))
    if not document.category.allow_download and not permissions.can_edit(request.user, "documents"):
        raise PermissionDenied(_("Le téléchargement n'est pas autorisé pour cette catégorie."))
    version = document.current if version_id is None else get_object_or_404(
        DocumentFile, pk=version_id, document=document)
    if version is None or not version.file:
        raise Http404
    services.log_view(document, request.user, "download", request)
    response = FileResponse(version.file.open("rb"), as_attachment=True,
                            filename=version.original_name or ("%s.%s" % (document.title, version.ext)))
    response["X-Content-Type-Options"] = "nosniff"
    return response


@module_required("documents")
def preview(request, pk: int):
    document = get_object_or_404(Document.objects.select_related("category"), pk=pk)
    if not services.can_view_category(request.user, document.category):
        raise PermissionDenied(_("Cette catégorie est verrouillée en lecture."))
    if not document.is_previewable or not document.current:
        return redirect("documents:download", pk=pk)
    services.log_view(document, request.user, "view", request)
    response = FileResponse(document.current.file.open("rb"))
    response["Content-Disposition"] = 'inline; filename="%s"' % (document.current.original_name or "apercu")
    response["X-Content-Type-Options"] = "nosniff"
    return response


# --------------------------------------------------------------------------- #
# Catégories et dossiers (droit fin documents.categories)
# --------------------------------------------------------------------------- #
@fine_required("documents.categories", "documents")
def categories(request):
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save(commit=False)
        category.created_by = category.created_by or request.user
        category.save()
        log(request.user, "document.category_created", "documents", category,
            "Catégorie enregistrée : %s" % category.name, request=request)
        messages.success(request, _("Catégorie enregistrée."))
        return redirect("documents:categories")
    return render(request, "documents/categories.html", {
        "categories": Category.objects.annotate(), "form": form,
        "folders": Folder.objects.select_related("category", "parent"),
        "root_folders": Folder.objects.filter(parent__isnull=True).select_related("category"),
        "page_title": "Catégories et dossiers",
    })


@fine_required("documents.categories", "documents")
def category_edit(request, pk: int):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    access_form = CategoryAccessForm(request.POST or None)
    delete_form = CategoryDeleteForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("save") and form.is_valid():
            previous = {"nom": category.name, "verrou": category.locked_read}
            saved = form.save()
            log(request.user, "document.category_updated", "documents", saved, "Catégorie modifiée",
                previous=previous, current={"nom": saved.name, "verrou": saved.locked_read}, request=request)
            messages.success(request, _("Catégorie enregistrée."))
            return redirect("documents:category_edit", pk=pk)
        if request.POST.get("access") and access_form.is_valid():
            access_form.save()
            messages.success(request, _("Accès par rôle enregistré."))
            return redirect("documents:category_edit", pk=pk)
        if request.POST.get("supprimer") and delete_form.is_valid():
            return _delete_category(request, category, delete_form.cleaned_data)
    return render(request, "documents/category_edit.html", {
        "category": category, "form": form, "access_form": access_form, "delete_form": delete_form,
        "accesses": category.accesses.select_related("role"),
        "documents": category.documents.live()[:50],
        "page_title": category.name,
    })


@reauth_required
def _delete_category(request, category: Category, data: dict):
    if data["mode"] == "reclass":
        target = data["target"]
        count = category.documents.count()
        category.documents.update(category=target)
        category.folders.update(category=target)
        category.delete()
        log(request.user, "document.category_deleted", "documents", None,
            "Catégorie « %s » supprimée, %d documents reclassés dans « %s »" % (category.name, count, target.name),
            level="danger", request=request)
        messages.success(request, _("Catégorie supprimée : %(n)s document(s) reclassé(s).") % {"n": count})
    else:
        count = category.documents.count()
        for document in category.documents.all():
            for version in document.versions.all():
                if version.file:
                    version.file.delete(save=False)
            document.delete()
        category.folders.all().delete()
        category.delete()
        log(request.user, "document.category_deleted", "documents", None,
            "Catégorie « %s » supprimée avec %d documents" % (category.name, count), level="danger", request=request)
        messages.success(request, _("Catégorie et fichiers supprimés (%(n)s documents).") % {"n": count})
    return redirect("documents:categories")


@fine_required("documents.categories", "documents")
@require_POST
def category_toggle_lock(request, pk: int):
    category = get_object_or_404(Category, pk=pk)
    category.locked_read = not category.locked_read
    category.save(update_fields=["locked_read"])
    log(request.user, "document.category_locked" if category.locked_read else "document.category_updated",
        "documents", category,
        "Catégorie %s" % ("verrouillée en lecture" if category.locked_read else "déverrouillée"),
        level="warn", request=request)
    messages.success(request, _("Verrouillage mis à jour."))
    return redirect("documents:category_edit", pk=pk)


@fine_required("documents.categories", "documents")
@require_POST
def folder_create(request):
    form = FolderForm(request.POST)
    if form.is_valid():
        folder = form.save()
        log(request.user, "document.category_created", "documents", folder,
            "Dossier créé : %s" % folder.name, request=request)
        messages.success(request, _("Dossier « %(nom)s » créé.") % {"nom": folder.name})
    else:
        for error in form.errors.values():
            messages.error(request, error[0])
    return redirect("documents:categories")


@fine_required("documents.categories", "documents")
@require_POST
def folder_delete(request, pk: int):
    folder = get_object_or_404(Folder, pk=pk)
    folder.documents.update(folder=None)
    for child in folder.children.all():
        child.documents.update(folder=None)
        child.delete()
    name = folder.name
    folder.delete()
    log(request.user, "document.category_deleted", "documents", None, "Dossier supprimé : %s" % name,
        level="warn", request=request)
    messages.success(request, _("Dossier supprimé, documents replacés à la racine."))
    return redirect("documents:categories")


@fine_required("documents.categories", "documents")
@require_POST
def force_locked(request, pk: int):
    """Forçage d'une catégorie verrouillée : tracé."""
    document = get_object_or_404(Document, pk=pk)
    document.locked = False
    document.locked_by = None
    document.locked_at = None
    document.save(update_fields=["locked", "locked_by", "locked_at"])
    log(request.user, "document.category_forced", "documents", document,
        "Verrou forcé par un gestionnaire de catégories", level="danger", request=request)
    messages.warning(request, _("Verrou forcé : l'action est journalisée."))
    return redirect("documents:detail", pk=pk)
