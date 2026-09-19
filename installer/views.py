"""Assistant de première installation (quatre étapes, sans compte de démonstration)."""
from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from config import settings as instance
from installer import services


def _guard(view):
    """L'assistant disparaît dès qu'un compte existe."""

    def wrapper(request, *args, **kwargs):
        if services.is_installed():
            messages.info(request, _("L'application est déjà installée."))
            return redirect("auth:login")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def _guard_close(view):
    """Étapes de clôture : réservées à la session qui vient de créer le premier compte.

    L'étape 3 crée le compte puis redirige vers le récapitulatif : à ce moment un
    compte existe déjà, donc le gardien ordinaire renverrait vers la connexion et
    l'utilisateur ne verrait jamais l'étape 4 ni le bouton des référentiels.
    """

    def wrapper(request, *args, **kwargs):
        if not request.session.get("install_admin"):
            messages.info(request, _("L'application est déjà installée."))
            return redirect("auth:login")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


class IdentityForm(forms.Form):
    nom = forms.CharField(label=_("Nom de l'association"), max_length=120, initial="MDL du lycée")
    sigle = forms.CharField(label=_("Sigle"), max_length=20, required=False, initial="MDL")
    lycee = forms.CharField(label=_("Établissement"), max_length=160, required=False)
    ville = forms.CharField(label=_("Ville"), max_length=80, required=False)
    contact = forms.EmailField(label=_("Courriel de contact"), required=False)
    couleur_principale = forms.CharField(label=_("Couleur principale"), max_length=9,
                                         widget=forms.TextInput(attrs={"type": "color"}),
                                         initial="#33556e")


class AdminForm(forms.Form):
    first_name = forms.CharField(label=_("Prénom"), max_length=80)
    last_name = forms.CharField(label=_("Nom"), max_length=80)
    email = forms.EmailField(label=_("Courriel"), help_text=_("Servira d'identifiant de connexion."))
    password1 = forms.CharField(label=_("Mot de passe"), widget=forms.PasswordInput,
                                help_text=_("10 caractères minimum, pas de mot de passe courant."))
    password2 = forms.CharField(label=_("Confirmation"), widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        if data.get("password1") and data["password1"] != data.get("password2"):
            self.add_error("password2", _("Les deux mots de passe ne correspondent pas."))
        return data


@_guard
def welcome(request):
    """Étape 1 : prérequis techniques."""
    return render(request, "installer/welcome.html", {
        "page_title": _("Installation"), "checks": services.prerequisites(),
        "ready": services.prerequisites_ok(),
        "bloquants": services.blocking_failures(),
        "recommandes": services.recommended_failures(),
        "step": 1,
    })


def _ensure_secret_key(config: dict) -> str:
    """Garantit une clé secrète propre avant la première écriture de session.

    Sans cela l'installation peut aboutir avec « dev-insecure-change-me »,
    valeur présente dans le dépôt public : quiconque la connaît peut forger
    un cookie de session. La clé générée est écrite dans instance.json
    (droits 600) et appliquée au processus courant, pour que la session
    d'installation survive au redémarrage qui suivra.
    """
    from django.core.management.utils import get_random_secret_key

    security = dict(config.get("security") or {})
    actuelle = security.get("secret_key") or ""
    if actuelle and actuelle != instance.DEFAULT_SECRET_KEY:
        return actuelle
    nouvelle = get_random_secret_key()
    security["secret_key"] = nouvelle
    config["security"] = security
    settings.SECRET_KEY = nouvelle
    return nouvelle


def _ensure_secret_key_persisted() -> str:
    """Pose la clé secrète dans instance.json si elle manque encore.

    L'étape 2 le fait déjà, mais on peut atteindre l'étape 3 directement par son
    URL. Comme l'étape 3 ouvre la première session, la clé doit être sûre avant.
    Idempotent : une clé déjà en place n'est ni régénérée ni réécrite.
    """
    config = instance.read_instance()
    avant = (config.get("security") or {}).get("secret_key") or ""
    clé = _ensure_secret_key(config)
    if clé != avant:
        instance.write_instance(config)
    return clé


@_guard
def identity(request):
    """Étape 2 : identité de l'association (écrite dans config/instance.json et les réglages)."""
    form = IdentityForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        config = instance.read_instance() if hasattr(instance, "read_instance") else {}
        branding = dict(config.get("branding") or {})
        branding.update({"association": data["nom"], "sigle": data["sigle"], "school": data["lycee"],
                         "city": data["ville"], "contact": data["contact"],
                         "primary_color": data["couleur_principale"]})
        config["branding"] = branding
        _ensure_secret_key(config)
        instance.write_instance(config)
        request.session["install"] = data
        try:
            from core.models import Setting

            Setting.update_section("branding", {
                "nom": data["nom"], "sigle": data["sigle"], "lycee": data["lycee"],
                "ville": data["ville"], "contact": data["contact"],
                "couleur_principale": data["couleur_principale"]})
        except Exception:  # noqa: BLE001 - base non migrée : on retentera à l'étape 3
            pass
        messages.success(request, _("Identité enregistrée."))
        return redirect("installer:admin")
    return render(request, "installer/identity.html", {
        "page_title": _("Identité"), "form": form, "step": 2,
    })


@_guard
def administrator(request):
    """Étape 3 : création du premier compte administrateur."""
    from accounts.services import create_administrator

    form = AdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        # C'est ici que la première session est ouverte : la clé secrète ne doit
        # plus être celle du dépôt, même si l'étape 2 a été court-circuitée.
        _ensure_secret_key_persisted()
        try:
            user = create_administrator(email=data["email"], password=data["password1"],
                                        first_name=data["first_name"], last_name=data["last_name"])
        except Exception as exc:  # noqa: BLE001 - message lisible pour l'installateur
            form.add_error("email", str(exc))
            return render(request, "installer/admin.html", {
                "page_title": _("Administrateur"), "form": form, "step": 3})
        config = instance.read_instance()
        meta = dict(config.get("meta") or {})
        meta["installed"] = True
        meta["installed_at"] = timezone.now().isoformat()
        config["meta"] = meta
        instance.write_instance(config)
        request.session["install_admin"] = user.email
        messages.success(request, _("Compte administrateur créé."))
        return redirect("installer:done")
    return render(request, "installer/admin.html", {
        "page_title": _("Administrateur"), "form": form, "step": 3,
    })


@_guard_close
def done(request):
    """Étape 4 : récapitulatif et prochaines étapes."""
    from core import services

    return render(request, "installer/done.html", {
        "page_title": _("Installation terminée"), "step": 4,
        "email": request.session.get("install_admin", ""),
        "health": services.health(),
    })


@_guard_close
@require_POST
def storage_choice(request):
    """Choix du stockage des fichiers proposé à l'installation (serveur ou tiers S3)."""
    from core.forms_settings import StorageForm
    from core.models import Setting

    form = StorageForm(request.POST)
    if form.is_valid():
        Setting.update_section("stockage", dict(form.cleaned_data))
        if form.cleaned_data.get("provider") == "s3":
            messages.success(request, _("Stockage tiers enregistré. Vérifiez-le avec le bouton "
                                        "« Test » dans Réglages → Stockage."))
        else:
            messages.success(request, _("Les fichiers seront rangés sur le disque du serveur."))
    else:
        messages.error(request, _("Stockage non enregistré : %s") % _(" ; ").join(
            erreur[0] for erreurs in form.errors.values() for erreur in erreurs))
    return redirect("installer:done")


@_guard_close
@require_POST
def seed_defaults(request):
    """Crée les référentiels par défaut (rôles, catégories, comptes) sans données de démonstration."""
    from accounts.services import ensure_admin_role
    from documents.services import ensure_default_categories
    from finance.services import ensure_accounts, ensure_gap_category
    from finance.services import ensure_default_categories as finance_categories

    # Un seul rôle à l'installation : l'association crée ensuite les siens.
    # La trame du bureau reste disponible via `manage.py seed`.
    ensure_admin_role()
    ensure_default_categories()
    finance_categories()
    ensure_gap_category()
    ensure_accounts()
    messages.success(request, _("Référentiels par défaut créés."))
    return redirect("installer:done")
