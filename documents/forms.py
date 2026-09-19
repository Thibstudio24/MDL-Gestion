"""Formulaires documents."""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext as _

from documents.models import Category, CategoryAccess, Document, Folder
from documents.services import UploadError, validate_upload


class MultipleFileInput(forms.ClearableFileInput):
    """Champ de dépôt multiple (glisser-déposer pris en charge par app.js)."""

    allow_multiple_selected = True

    def __init__(self, attrs=None):
        super(forms.ClearableFileInput, self).__init__(dict(attrs or {}, multiple=True))


class MultipleFileField(forms.FileField):
    """Valide chaque fichier d'un dépôt multiple."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return [single(data, initial)]


class UploadForm(forms.Form):
    category = forms.ModelChoiceField(label="Catégorie", queryset=Category.objects.filter(archived=False))
    folder = forms.ModelChoiceField(label="Dossier", queryset=Folder.objects.all(), required=False)
    title = forms.CharField(label="Titre", max_length=200, required=False)
    description = forms.CharField(label="Description", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    tags = forms.CharField(label="Étiquettes (séparées par des virgules)", required=False)
    comment = forms.CharField(label="Commentaire de version", max_length=240, required=False)
    files = MultipleFileField(
        label="Fichiers",
        help_text="Formats acceptés : pdf, doc, docx, xls, xlsx, ods, odt, odp, png, jpg, jpeg, webp, gif, txt, csv, zip.",
    )

    def clean_files(self):
        files = self.cleaned_data.get("files") or []
        if not files:
            raise forms.ValidationError(_("Déposez au moins un fichier."))
        for upload in files:
            try:
                validate_upload(upload.name, upload.size)
            except UploadError as exc:
                raise forms.ValidationError(str(exc)) from exc
        return files

    def clean_tags(self):
        raw = self.cleaned_data.get("tags") or ""
        return [item.strip() for item in raw.split(",") if item.strip()][:20]


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "description", "category", "folder", "tags"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"].widget = forms.TextInput()

    def clean_tags(self):
        value = self.cleaned_data.get("tags")
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()][:20]
        return list(value or [])


class ReplaceForm(forms.Form):
    file = forms.FileField(label="Nouveau fichier")
    comment = forms.CharField(label="Commentaire", max_length=240, required=False)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        try:
            validate_upload(upload.name, upload.size)
        except UploadError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return upload


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "color", "icon", "order", "locked_read", "archived", "allow_download"]
        widgets = {"description": forms.TextInput()}


class CategoryDeleteForm(forms.Form):
    mode = forms.ChoiceField(label="Que faire des fichiers ?",
                             choices=[("reclass", "Reclasser dans une autre catégorie"),
                                      ("delete", "Supprimer les fichiers")])
    target = forms.ModelChoiceField(label="Catégorie de destination", queryset=Category.objects.all(),
                                    required=False)
    confirmation = forms.CharField(label="Saisissez RECLASSER ou SUPPRIMER", max_length=20)

    def clean(self):
        data = super().clean()
        if data.get("mode") == "reclass" and not data.get("target"):
            self.add_error("target", _("Choisissez la catégorie de destination."))
        if data.get("mode") == "delete" and data.get("confirmation", "").upper() != "SUPPRIMER":
            self.add_error("confirmation", _("Saisissez SUPPRIMER pour confirmer."))
        if data.get("mode") == "reclass" and data.get("confirmation", "").upper() != "RECLASSER":
            self.add_error("confirmation", _("Saisissez RECLASSER pour confirmer."))
        return data


class FolderForm(forms.ModelForm):
    class Meta:
        model = Folder
        fields = ["category", "parent", "name", "description", "locked_read", "order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le formulaire de la page Catégories n'envoie que les champs visibles :
        # ordre, parent et verrou restent optionnels avec leurs valeurs par défaut.
        self.fields["order"].required = False
        self.fields["order"].initial = 100
        self.fields["parent"].required = False
        self.fields["locked_read"].required = False

    def clean_order(self):
        return self.cleaned_data.get("order") or 100

    def clean(self):
        data = super().clean()
        parent = data.get("parent")
        if parent is not None and parent.parent_id is not None:
            self.add_error("parent", _("Deux niveaux de dossiers au maximum."))
        return data


class CategoryAccessForm(forms.ModelForm):
    class Meta:
        model = CategoryAccess
        fields = ["role", "level", "can_delete"]
