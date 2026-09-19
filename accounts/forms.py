"""Formulaires des comptes : connexion, A2F, invitation, profil, membres, rôles."""
from __future__ import annotations

from django import forms
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext as _

from accounts.models import Role, User
from core import permissions


class LoginForm(forms.Form):
    email = forms.EmailField(label="Adresse e-mail", widget=forms.EmailInput(attrs={"autofocus": True,
                                                                                   "autocomplete": "username"}))
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    remember = forms.BooleanField(label="Rester connecté sur cet appareil", required=False)


class SecondFactorForm(forms.Form):
    code = forms.CharField(label="Code à 6 chiffres", max_length=12,
                           widget=forms.TextInput(attrs={"autofocus": True, "inputmode": "numeric",
                                                         "autocomplete": "one-time-code"}))


class ReauthForm(forms.Form):
    password = forms.CharField(label="Confirmez votre mot de passe",
                               widget=forms.PasswordInput(attrs={"autofocus": True,
                                                                 "autocomplete": "current-password"}))


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Adresse e-mail du compte")


class PasswordResetForm(forms.Form):
    password1 = forms.CharField(label="Nouveau mot de passe", widget=forms.PasswordInput(attrs={"data-strength": "1"}))
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput())

    def clean(self):
        data = super().clean()
        if data.get("password1") and data["password1"] != data.get("password2"):
            raise forms.ValidationError(_("Les deux mots de passe ne correspondent pas."))
        return data


class InvitationForm(forms.Form):
    first_name = forms.CharField(label="Prénom", max_length=80)
    last_name = forms.CharField(label="Nom", max_length=80)
    email = forms.EmailField(label="Adresse e-mail")
    role = forms.ModelChoiceField(label="Rôle", queryset=Role.objects.all())

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        from core import permissions

        self.actor = actor
        if actor is not None and not permissions.is_administrator(actor):
            # Seul un administrateur peut inviter quelqu'un au rôle Administrateur.
            self.fields["role"].queryset = Role.objects.filter(is_administrator=False)
    display_function = forms.CharField(label="Fonction affichée", max_length=120, required=False)
    is_boarder = forms.BooleanField(label="Interne (hébergé au lycée)", required=False)
    days = forms.TypedChoiceField(label="Validité de l'invitation", coerce=int,
                                  choices=[(1, "1 jour"), (3, "3 jours"), (7, "7 jours (défaut)"), (30, "30 jours")],
                                  initial=7)
    message = forms.CharField(label="Message d'accompagnement", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existing = User.objects.filter(email__iexact=email, status="active").first()
        if existing:
            raise forms.ValidationError(_("Un compte actif utilise déjà cette adresse."))
        return email


class MemberForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "display_function", "phone", "gender",
                  "is_boarder", "role", "status", "photo"]
        widgets = {"photo": forms.ClearableFileInput(attrs={"accept": ".png,.jpg,.jpeg,.webp,.gif"})}

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        from core import permissions

        self.actor = actor
        self.fields["photo"].validators = [FileExtensionValidator(["png", "jpg", "jpeg", "webp", "gif"])]
        roles = Role.objects.all()
        if actor is not None and not permissions.is_administrator(actor):
            # Seul un administrateur peut attribuer le rôle Administrateur ; le
            # rôle actuel reste proposable pour ne pas casser l'édition d'un admin.
            roles = Role.objects.filter(is_administrator=False)
            if self.instance is not None and getattr(self.instance, "role_id", None):
                roles = roles | Role.objects.filter(pk=self.instance.role_id)
        self.fields["role"].queryset = roles

    def clean(self):
        data = super().clean()
        role = data.get("role")
        actuelle = getattr(self.instance, "role", None)
        if role is not None and role.is_administrator and (actuelle is None or actuelle.pk != role.pk):
            from core import permissions

            if self.actor is None or not permissions.is_administrator(self.actor):
                self.add_error("role", "Seul un Administrateur peut attribuer le rôle Administrateur.")
        return data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "display_function", "phone", "gender", "photo"]
        widgets = {"photo": forms.ClearableFileInput(attrs={"accept": ".png,.jpg,.jpeg,.webp,.gif"})}


class EmailChangeForm(forms.Form):
    email = forms.EmailField(label="Nouvelle adresse e-mail de connexion")
    password = forms.CharField(label="Mot de passe actuel", widget=forms.PasswordInput())


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(label="Mot de passe actuel", widget=forms.PasswordInput())
    new_password1 = forms.CharField(label="Nouveau mot de passe",
                                    widget=forms.PasswordInput(attrs={"data-strength": "1"}))
    new_password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput())

    def clean(self):
        data = super().clean()
        if data.get("new_password1") and data["new_password1"] != data.get("new_password2"):
            raise forms.ValidationError(_("Les deux mots de passe ne correspondent pas."))
        return data


def permissions_palette_choices():
    from core.theme import palette_choices

    return palette_choices()


class AppearanceForm(forms.Form):
    palette = forms.ChoiceField(label="Palette", choices=permissions_palette_choices(), required=False)
    mode = forms.ChoiceField(label="Mode", choices=[("light", "Clair"), ("dark", "Sombre"), ("auto", "Automatique")])
    density = forms.ChoiceField(label="Densité", choices=[("confort", "Confort"), ("compacte", "Compacte")])


class QuietHoursForm(forms.Form):
    actif = forms.BooleanField(label="Activer les heures de silence", required=False)
    debut = forms.CharField(label="Début", max_length=5, initial="22:00")
    fin = forms.CharField(label="Fin", max_length=5, initial="07:00")


class TwoFactorEnableForm(forms.Form):
    code = forms.CharField(label="Code affiché par votre application", max_length=8,
                           widget=forms.TextInput(attrs={"inputmode": "numeric", "autofocus": True}))


class WelcomeForm(forms.Form):
    receive_personal_email = forms.BooleanField(
        label="Recevoir les messages de l'association sur ma boîte e-mail", required=False
    )
    accept_charte = forms.BooleanField(label="J'accepte la charte", required=False)

    def __init__(self, *args, charte_required: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.charte_required = charte_required
        self.fields["accept_charte"].required = charte_required

    def clean_accept_charte(self):
        value = self.cleaned_data.get("accept_charte")
        if self.charte_required and not value:
            raise forms.ValidationError(_("L'acceptation de la charte est obligatoire."))
        return value


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name", "description", "color", "icon", "home", "force_2fa", "force_2fa_deadline_days", "order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["home"].choices = [(value, label) for value, label in self.fields["home"].choices]


class RoleRightsForm(forms.Form):
    """Grille modules × niveaux + droits fins, validée contre le plafond de l'éditeur."""

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        self.max_level = permissions.max_allowed_level(editor) if editor else 2
        self.is_admin_editor = permissions.is_administrator(editor) if editor else True
        for module, label in permissions.MODULES.items():
            if module == "roles" and not self.is_admin_editor:
                continue
            self.fields["level-%s" % module] = forms.TypedChoiceField(
                label=label, coerce=int, required=False, initial=0,
                choices=[(value, label) for value, label in permissions.LEVEL_CHOICES],
                widget=forms.RadioSelect,
            )
        for key, (label, _module, _auto) in permissions.FINE_PERMISSIONS.items():
            self.fields["fine-%s" % key] = forms.BooleanField(label=label, required=False)

    def clean(self):
        data = super().clean()
        if not self.is_admin_editor:
            for module in permissions.MODULES:
                field = "level-%s" % module
                if field in data and int(data.get(field) or 0) > self.max_level:
                    self.add_error(field, _("Vous ne pouvez pas accorder un niveau supérieur au vôtre."))
        return data


class AnonymizeForm(forms.Form):
    confirmation = forms.CharField(label="Saisissez les 3 premières lettres de votre nom", max_length=3)
