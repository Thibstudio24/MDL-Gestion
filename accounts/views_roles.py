"""Rôles & droits (/roles/) : réservé aux Administrateurs."""
from __future__ import annotations

import json

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.forms import RoleForm, RoleRightsForm
from accounts.models import Role, RolePermission, User
from accounts.services import _apply_levels, _slug
from audit.services import log
from core import permissions
from core.decorators import administrator_required
from core.export import json_download
from core.permissions import FINE_PERMISSIONS, MODULES


@administrator_required
def list_view(request):
    roles = Role.objects.annotate(nb=Count("members")).order_by("order", "name")
    return render(request, "accounts/role_list.html", {
        "roles": roles, "modules": MODULES, "page_title": "Rôles & droits",
    })


@administrator_required
def detail(request, pk: int):
    role = get_object_or_404(Role, pk=pk)
    levels = {perm.codename: perm.level for perm in role.permissions.all()}
    fine = set(role.fine_permissions or [])
    form = RoleForm(request.POST or None, instance=role)
    rights = RoleRightsForm(request.POST or None, editor=request.user,
                            initial={**{"level-%s" % key: levels.get(key, 0) for key in MODULES},
                                     **{"fine-%s" % key: (key in fine) for key in FINE_PERMISSIONS}})
    if request.method == "POST" and form.is_valid() and rights.is_valid():
        previous = {"droits": {key: levels.get(key, 0) for key in MODULES}, "fins": sorted(fine)}
        saved = form.save()
        new_levels = {key: int(rights.cleaned_data.get("level-%s" % key) or 0) for key in MODULES}
        new_fine = [key for key in FINE_PERMISSIONS if rights.cleaned_data.get("fine-%s" % key)]
        if saved.is_administrator and saved.pk != role.pk:
            saved.is_administrator = True
        _apply_levels(saved, new_levels, new_fine)
        for member in saved.members.filter(status="active"):
            permissions.invalidate(member)
        log(request.user, "role.permissions_changed", "roles", saved, "Droits du rôle modifiés",
            previous=previous, current={"droits": new_levels, "fins": new_fine}, level="warn", request=request)
        messages.success(request, _("Droits enregistrés pour « %(role)s ».") % {"role": saved.name})
        return redirect("roles:roles_detail", pk=saved.pk)
    members = role.members.select_related("role").order_by("last_name")[:60]
    return render(request, "accounts/role_detail.html", {
        "role": role, "form": form, "rights": rights, "members": members,
        "modules": MODULES, "fine": FINE_PERMISSIONS, "levels": levels, "fine_checked": fine,
        "protected": role.is_system or role.is_administrator,
        "page_title": role.name,
    })


@administrator_required
@require_POST
def create(request):
    form = RoleForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, "%s : %s" % (field, error))
        return redirect("roles:roles_list")
    role = form.save(commit=False)
    role.slug = _slug(role.name)
    role.save()
    _apply_levels(role, {"dashboard": 1, "documents": 2, "planning_salle": 2, "planning_menage": 2, "mail": 1}, [])
    log(request.user, "role.created", "roles", role, "Rôle créé", request=request)
    messages.success(request, _("Rôle « %(role)s » créé : ajustez maintenant ses droits.") % {"role": role.name})
    return redirect("roles:roles_detail", pk=role.pk)


@administrator_required
@require_POST
def duplicate(request, pk: int):
    source = get_object_or_404(Role, pk=pk)
    name = (request.POST.get("name") or "%s (copie)" % source.name).strip()
    role = Role.objects.create(
        name=name, slug=_slug(name), description=source.description, color=source.color,
        icon=source.icon, home=source.home, order=source.order + 1,
        force_2fa=source.force_2fa, force_2fa_deadline_days=source.force_2fa_deadline_days,
    )
    _apply_levels(role, {perm.codename: perm.level for perm in source.permissions.all()},
                  list(source.fine_permissions or []))
    log(request.user, "role.created", "roles", role, "Rôle dupliqué depuis %s" % source.name, request=request)
    messages.success(request, _("Rôle dupliqué."))
    return redirect("roles:roles_detail", pk=role.pk)


@administrator_required
@require_POST
def delete(request, pk: int):
    role = get_object_or_404(Role, pk=pk)
    if role.is_system or role.is_administrator:
        messages.error(request, _("Ce rôle est protégé : il ne peut pas être supprimé."))
        return redirect("roles:roles_list")
    if role.members.exists():
        messages.error(request, _("Ce rôle compte encore %(n)s membre(s) : réassignez-les d'abord.")
                       % {"n": role.members.count()})
        return redirect("roles:roles_detail", pk=pk)
    name = role.name
    role.delete()
    log(request.user, "role.deleted", "roles", None, "Rôle supprimé : %s" % name, level="warn", request=request)
    messages.success(request, _("Rôle supprimé."))
    return redirect("roles:roles_list")


@administrator_required
@require_POST
def quick_level(request, pk: int):
    role = get_object_or_404(Role, pk=pk)
    module = request.POST.get("module")
    if module not in MODULES:
        messages.error(request, _("Module inconnu."))
        return redirect("roles:roles_detail", pk=pk)
    if module == "roles" and not role.is_administrator:
        messages.error(request, _("Le module « Rôles & droits » n'est éditable que pour le rôle Administrateur."))
        return redirect("roles:roles_detail", pk=pk)
    level = int(request.POST.get("level", 0))
    if not permissions.is_administrator(request.user) and level > permissions.max_allowed_level(request.user):
        messages.error(request, _("Vous ne pouvez pas accorder un niveau supérieur au vôtre."))
        return redirect("roles:roles_detail", pk=pk)
    previous = {perm.codename: perm.level for perm in role.permissions.all()}
    RolePermission.objects.update_or_create(role=role, codename=module, defaults={"level": level})
    for member in role.members.filter(status="active"):
        permissions.invalidate(member)
    log(request.user, "role.permissions_changed", "roles", role,
        "Niveau %(module)s → %(level)s" % {"module": module, "level": level},
        previous=previous, current={**previous, module: level}, level="warn", request=request)
    messages.success(request, _("%(module)s : %(label)s") % {"module": MODULES[module],
                                                            "label": dict(permissions.LEVEL_CHOICES)[level]})
    return redirect("roles:roles_detail", pk=pk)


@administrator_required
def export_rights(request):
    payload = {
        "version": 1,
        "roles": [
            {
                "name": role.name, "description": role.description, "color": role.color, "icon": role.icon,
                "home": role.home, "order": role.order, "force_2fa": role.force_2fa,
                "force_2fa_deadline_days": role.force_2fa_deadline_days,
                "niveaux": {perm.codename: perm.level for perm in role.permissions.all()},
                "droits_fins": list(role.fine_permissions or []),
            }
            for role in Role.objects.all()
        ],
    }
    log(request.user, "role.exported", "roles", None, "Configuration des droits exportée", request=request)
    return json_download("droits-mdl.json", payload)


@administrator_required
@require_POST
def import_rights(request):
    try:
        payload = json.loads(request.POST.get("payload") or "{}")
    except ValueError:
        messages.error(request, _("JSON invalide."))
        return redirect("roles:roles_list")
    imported = 0
    for item in payload.get("roles", []):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        role, _created = Role.objects.get_or_create(
            name=name,
            defaults={"slug": _slug(name), "order": int(item.get("order", 100))},
        )
        role.description = item.get("description", role.description)
        role.color = item.get("color", role.color)
        role.icon = item.get("icon", role.icon)
        role.home = item.get("home", role.home)
        role.force_2fa = bool(item.get("force_2fa", role.force_2fa))
        role.force_2fa_deadline_days = int(item.get("force_2fa_deadline_days", role.force_2fa_deadline_days))
        role.save()
        _apply_levels(role, {key: int(value) for key, value in (item.get("niveaux") or {}).items() if key in MODULES},
                      [key for key in (item.get("droits_fins") or []) if key in FINE_PERMISSIONS])
        imported += 1
    permissions.invalidate_all()
    log(request.user, "role.imported", "roles", None, "Configuration des droits importée (%d rôles)" % imported,
        level="warn", request=request)
    messages.success(request, _("%(n)s rôles importés.") % {"n": imported})
    return redirect("roles:roles_list")
