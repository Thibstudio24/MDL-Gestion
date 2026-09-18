"""Décorateurs de vue : droits par module, administrateur, ré-authentification."""
from __future__ import annotations

import functools
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _

from core import permissions


def module_required(module: str, edit: bool = False):
    """Refus 403 avec message explicite si le niveau du module est insuffisant."""

    def wrapper(view):
        @functools.wraps(view)
        @login_required
        def inner(request, *args, **kwargs):
            allowed = permissions.can_edit(request.user, module) if edit else permissions.can_view(request.user, module)
            if not allowed:
                label = permissions.MODULES.get(module, module)
                messages.error(
                    request,
                    _("Votre rôle ne permet que de consulter %(module)s.") % {"module": label}
                    if not edit
                    else _("Votre rôle ne permet pas de modifier %(module)s.") % {"module": label},
                )
                raise PermissionDenied(_("Votre rôle ne permet pas d'accéder à %(module)s.") % {"module": label})
            return view(request, *args, **kwargs)

        return inner

    return wrapper


def administrator_required(view):
    @functools.wraps(view)
    @login_required
    def inner(request, *args, **kwargs):
        if not permissions.is_administrator(request.user):
            messages.error(request, _("Cette page est réservée aux administrateurs."))
            raise PermissionDenied(_("Réservé aux administrateurs."))
        return view(request, *args, **kwargs)

    return inner


def fine_required(key: str, module: str | None = None):
    """Vérifie un droit fin (documents.delete, finance.lock…)."""

    def wrapper(view):
        @functools.wraps(view)
        @login_required
        def inner(request, *args, **kwargs):
            if module and not permissions.can_view(request.user, module):
                raise PermissionDenied()
            if not permissions.fine(request.user, key):
                messages.error(request, _("Votre rôle ne dispose pas du droit « %(droit)s ».") % {"droit": key})
                raise PermissionDenied(_("Droit fin manquant : %s") % key)
            return view(request, *args, **kwargs)

        return inner

    return wrapper


def reauth_required(view):
    """Ré-authentification (mot de passe, 10 min) pour les actions sensibles."""

    @functools.wraps(view)
    @login_required
    def inner(request, *args, **kwargs):
        stamp = request.session.get("reauth_at")
        minutes = getattr(settings, "MDL_REAUTH_MINUTES", 10)
        fresh = False
        if stamp:
            try:
                fresh = timezone.now() - datetime.fromisoformat(stamp) < timedelta(minutes=minutes)
            except (ValueError, TypeError):
                fresh = False
        if not fresh:
            request.session["reauth_next"] = request.get_full_path()
            messages.info(request, _("Confirmez votre mot de passe pour cette opération sensible."))
            return redirect("reauth")
        return view(request, *args, **kwargs)

    return inner


def mark_reauthenticated(request) -> None:
    request.session["reauth_at"] = timezone.now().isoformat()


def require_POST(view):
    @functools.wraps(view)
    def inner(request, *args, **kwargs):
        if request.method != "POST":
            raise PermissionDenied(_("Méthode non autorisée."))
        return view(request, *args, **kwargs)

    return inner
