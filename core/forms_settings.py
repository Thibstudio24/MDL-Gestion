"""Formulaires des Réglages de l'association."""
from __future__ import annotations

from django import forms

from core import theme
from core.models import ClosureDay, LegalDocument, SchoolYear

PALETTE_CHOICES = theme.palette_choices()
MODE_CHOICES = [("", "— laisser le choix aux membres —"), ("light", "Clair"), ("dark", "Sombre"), ("auto", "Automatique")]


class BrandForm(forms.Form):
    nom = forms.CharField(label="Nom de l'association", max_length=120)
    sigle = forms.CharField(label="Sigle", max_length=12, required=False)
    lycee = forms.CharField(label="Lycée", max_length=160, required=False)
    ville = forms.CharField(label="Ville", max_length=80, required=False)
    contact = forms.EmailField(label="Adresse de contact", required=False)
    logo = forms.CharField(label="Logo (URL ou chemin dans media/)", required=False,
                           widget=forms.TextInput(attrs={"placeholder": "media/branding/logo.png"}))
    couleur_principale = forms.CharField(label="Couleur principale", max_length=9,
                                         widget=forms.TextInput(attrs={"type": "color"}))
    palette_imposee = forms.ChoiceField(label="Palette imposée", choices=[("", "— aucune —")] + PALETTE_CHOICES,
                                        required=False)
    mode_impose = forms.ChoiceField(label="Mode imposé", choices=MODE_CHOICES, required=False)

    def clean_couleur_principale(self):
        value = (self.cleaned_data.get("couleur_principale") or "#33556e").strip()
        if not value.startswith("#") or len(value) not in (4, 7):
            raise forms.ValidationError("Saisissez une couleur au format #RRGGBB.")
        return value


class YearForm(forms.ModelForm):
    class Meta:
        model = SchoolYear
        fields = ["label", "start_date", "end_date", "is_current", "note"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}),
                   "end_date": forms.DateInput(attrs={"type": "date"}),
                   "note": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("end_date") and data["start_date"] >= data["end_date"]:
            raise forms.ValidationError("La date de fin doit suivre la date de début.")
        return data


class ClosureDayForm(forms.ModelForm):
    class Meta:
        model = ClosureDay
        fields = ["day", "reason"]
        widgets = {"day": forms.DateInput(attrs={"type": "date"})}


class QuotaForm(forms.Form):
    max_file_mb = forms.IntegerField(label="Taille maximale par fichier (Mo)", min_value=1, max_value=500)
    total_mb = forms.IntegerField(label="Quota global (Mo)", min_value=10, max_value=2048)
    versions_kept = forms.IntegerField(label="Versions conservées par document", min_value=1, max_value=20)
    chores_photos_kept = forms.IntegerField(label="Photos de ménage conservées après validation (0 = supprimées)",
                                            min_value=0, max_value=12)
    mail_purge_years = forms.IntegerField(label="Purger les e-mails lus après (années)", min_value=0, max_value=10)
    purge_inactive_months = forms.IntegerField(label="Purger les comptes inactifs après (mois, 0 = jamais)",
                                               min_value=0, max_value=120)


class SecurityForm(forms.Form):
    password_min_length = forms.IntegerField(label="Longueur minimale du mot de passe", min_value=8, max_value=64)
    login_max_attempts = forms.IntegerField(label="Tentatives avant verrouillage", min_value=3, max_value=20)
    login_lockout_minutes = forms.IntegerField(label="Durée du verrouillage (minutes)", min_value=1, max_value=240)
    session_days = forms.IntegerField(label="Durée de session (jours)", min_value=1, max_value=90)
    audit_keep_years = forms.IntegerField(label="Conservation du journal d'audit (années)", min_value=1, max_value=20)
    delai_2fa_jours = forms.IntegerField(label="Délai d'activation de l'A2F (jours)", min_value=0, max_value=180)


class SmtpForm(forms.Form):
    enabled = forms.BooleanField(label="Envoyer les e-mails par SMTP", required=False)
    host = forms.CharField(label="Serveur SMTP", max_length=160, required=False)
    port = forms.IntegerField(label="Port", min_value=1, max_value=65535, required=False)
    use_ssl = forms.BooleanField(label="SSL (port 465)", required=False)
    use_tls = forms.BooleanField(label="STARTTLS (port 587)", required=False)
    user = forms.CharField(label="Identifiant (l'adresse complète)", max_length=160, required=False)
    password = forms.CharField(label="Mot de passe", max_length=200, required=False,
                               widget=forms.PasswordInput(render_value=True, attrs={"autocomplete": "new-password"}))
    mail_from = forms.EmailField(label="Adresse d'envoi", required=False)
    reply_to = forms.EmailField(label="Adresse de réponse", required=False)
    rate_per_minute = forms.IntegerField(label="E-mails par minute (lissage)", min_value=1, max_value=60, required=False)
    fallback = forms.ChoiceField(label="Canal de secours si l'envoi échoue",
                                 choices=[("inapp", "Seulement dans l'app"), ("email", "Réessayer par e-mail")],
                                 required=False)


class PushForm(forms.Form):
    enabled = forms.BooleanField(label="Notifications push activées", required=False)
    public_key = forms.CharField(label="Clé publique VAPID", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    private_key = forms.CharField(label="Clé privée VAPID", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    claims_email = forms.EmailField(label="E-mail de contact VAPID", required=False)


class MaintenanceForm(forms.Form):
    maintenance = forms.BooleanField(label="Activer le mode maintenance", required=False)
    maintenance_message = forms.CharField(label="Message affiché", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    exclus_maintenance = forms.CharField(label="Comptes exclus (e-mails séparés par des virgules)", required=False)


class UpdateForm(forms.Form):
    update_check = forms.BooleanField(label="Vérifier automatiquement les mises à jour", required=False)
    update_channel = forms.ChoiceField(label="Canal", choices=[("stable", "Stable"), ("beta", "Bêta")])
    pinned_version = forms.CharField(label="Épingler une version (ex. 1.0.0)", required=False)


class TelemetryForm(forms.Form):
    telemetry = forms.BooleanField(label="Envoyer des compteurs anonymes à l'éditeur (opt-in)", required=False)
    hub_url = forms.URLField(label="Adresse du hub éditeur", required=False, assume_scheme="https")


class LegalForm(forms.ModelForm):
    class Meta:
        model = LegalDocument
        fields = ["title", "body", "requires_acceptance", "published"]
        widgets = {"body": forms.Textarea(attrs={"rows": 18})}


class BalanceScheduleForm(forms.Form):
    MODES = [
        ("jour", "Chaque mois, le jour choisi"),
        ("dernier", "Le dernier jour du mois"),
        ("ouvrable", "Le premier jour ouvré du mois"),
        ("trimestriel", "Tous les 3 mois, le jour choisi"),
    ]
    auto = forms.BooleanField(label="Générer automatiquement le bilan", required=False)
    mode = forms.ChoiceField(label="Échéance", choices=MODES)
    jour = forms.IntegerField(label="Jour du mois (1-28)", min_value=1, max_value=28)
    heure = forms.TimeField(label="Heure", input_formats=["%H:%M"])
    categorie = forms.CharField(label="Catégorie Documents de rangement", max_length=80)
    # Les destinataires ne se choisissent plus : le bilan va aux seuls membres
    # qui peuvent consulter la trésorerie, et la catégorie de documents
    # « Bilans » exige ce même droit (Category.module_gate = "finance").
