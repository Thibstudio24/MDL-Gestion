"""Décorateurs propres aux comptes (invitation valide, A2F, compte actif)."""
from __future__ import annotations

import functools

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.translation import gettext as _


def two_factor_required(view):
    """Bloque sur l'écran d'activation une fois le délai du rôle dépassé."""

    @functools.wraps(view)
    @login_required
    def inner(request, *args, **kwargs):
        user = request.user
        if user.two_factor_overdue and request.path not in (
            "/connexion/a2f/configurer/", "/deconnexion/", "/parametres/securite/"
        ):
            return redirect("twofa_setup")
        return view(request, *args, **kwargs)

    return inner


def active_member_required(view):
    @functools.wraps(view)
    @login_required
    def inner(request, *args, **kwargs):
        if not request.user.is_active:
            raise PermissionDenied(_("Ce compte n'est pas actif."))
        return view(request, *args, **kwargs)

    return inner
