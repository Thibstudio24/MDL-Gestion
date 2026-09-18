"""Formulaires de la trésorerie."""
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.db import models
from django.utils.translation import gettext_lazy as _

from finance.models import MODES, Account, AccountOpening, Category, Entry


class LedgerFilterForm(forms.Form):
    """Filtres du grand livre (dates, compte, catégorie, mode, recherche)."""

    q = forms.CharField(label=_("Recherche"), required=False, max_length=120)
    account = forms.ModelChoiceField(label=_("Compte"), queryset=Account.objects.all(), required=False)
    category = forms.ModelChoiceField(label=_("Catégorie"), queryset=Category.objects.all(), required=False)
    mode = forms.ChoiceField(label=_("Mode de règlement"), choices=[("", _("Tous"))] + list(MODES), required=False)
    kind = forms.ChoiceField(label=_("Sens"), choices=[("", _("Tous")), ("D", _("Dépense")), ("R", _("Recette")),
                                                      ("T", _("Transfert"))], required=False)
    start = forms.DateField(label=_("Du"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label=_("Au"), required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def filter_queryset(self, queryset):
        data = self.cleaned_data
        if data.get("q"):
            term = data["q"]
            queryset = queryset.filter(models.Q(title__icontains=term) | models.Q(third_party__icontains=term)
                                       | models.Q(reference__icontains=term))
        for field in ("account", "category", "mode", "kind"):
            if data.get(field):
                queryset = queryset.filter(**{field: data[field]})
        if data.get("start"):
            queryset = queryset.filter(day__gte=data["start"])
        if data.get("end"):
            queryset = queryset.filter(day__lte=data["end"])
        return queryset



class EntryForm(forms.ModelForm):
    """Saisie d'une écriture : dépense, recette ou transfert."""

    class Meta:
        model = Entry
        fields = ["day", "title", "amount", "kind", "account", "to_account", "category", "subcategory",
                  "mode", "third_party", "reference", "note", "support_file"]
        widgets = {
            "day": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(active=True)
        self.fields["subcategory"].queryset = Category.objects.filter(active=True)
        self.fields["to_account"].required = False
        self.fields["title"].widget.attrs["placeholder"] = _("Ex. : Achat de matériel pour le tournoi")

    def clean(self):
        data = super().clean()
        if data.get("kind") == "T":
            if not data.get("to_account"):
                self.add_error("to_account", _("Choisissez le compte destinataire du transfert."))
            elif data.get("account") and data["to_account"].pk == data["account"].pk:
                self.add_error("to_account", _("Le compte destinataire doit être différent du compte émetteur."))
        if data.get("amount") is not None and data["amount"] <= Decimal("0"):
            self.add_error("amount", _("Le montant doit être strictement positif."))
        return data


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "type", "bank", "number", "iban", "order", "active", "is_safe", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 2})}


class OpeningForm(forms.ModelForm):
    class Meta:
        model = AccountOpening
        fields = ["account", "amount"]


class CashCountForm(forms.Form):
    day = forms.DateField(label=_("Date du comptage"), widget=forms.DateInput(attrs={"type": "date"}))
    account = forms.ModelChoiceField(label=_("Compte"), queryset=Account.objects.all())
    counted = forms.DecimalField(label=_("Montant compté"), max_digits=11, decimal_places=2,
                                 widget=forms.NumberInput(attrs={"step": "0.01"}))
    reason = forms.CharField(label=_("Motif de l'écart"), required=False, max_length=240,
                             help_text=_("Obligatoire dès qu'un écart existe (pièce perdue, erreur de caisse…)."))


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["label", "code", "kind", "parent", "color", "order", "active", "note"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"}), "note": forms.Textarea(attrs={"rows": 2})}


class ImportForm(forms.Form):
    file = forms.FileField(label=_("Fichier"),
                           widget=forms.FileInput(attrs={"accept": ".csv,.qif,.ofx"}),
                           help_text=_("CSV, QIF ou OFX exporté de votre banque."))
    account = forms.ModelChoiceField(label=_("Compte"), queryset=Account.objects.filter(active=True))
    mapping = forms.JSONField(label=_("Correspondance des colonnes"), required=False, widget=forms.HiddenInput())
    skip_duplicates = forms.BooleanField(label=_("Ignorer les doublons"), required=False, initial=True)


class BalanceForm(forms.Form):
    up_to = forms.DateField(label=_("Arrêté au"), widget=forms.DateInput(attrs={"type": "date"}))


class LockForm(forms.Form):
    month = forms.ChoiceField(label=_("Mois"))
    note = forms.CharField(label=_("Note"), required=False, max_length=240)

    def __init__(self, year, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from finance.services import months_for

        self.fields["month"].choices = [("%d-%d" % (item["month"], item["year"]), item["label"])
                                        for item in months_for(year)]


class DeleteReasonForm(forms.Form):
    reason = forms.CharField(label=_("Motif"), max_length=240,
                             help_text=_("Obligatoire : la suppression d'une écriture est toujours motivée."))
