"""Contexte commun : association, thème, navigation filtrée par droits."""
from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from core import permissions
from core.models import Setting

NAV_GROUPS = [
    ("vie", [
        ("dashboard", "dashboard", "Tableau de bord", "home"),
        ("documents", "documents:documents_list", "Documents", "folder"),
        ("finance", "finance:finance_list", "Trésorerie", "coins"),
        ("planning_salle", "plannings:planning_list", "Planning de la salle", "calendar"),
        ("planning_menage", "chores:chores_list", "Planning de ménage", "broom"),
        ("mail", "mail:mail_inbox", "Messages", "mail"),
    ]),
    ("admin", [
        ("members", "members:members_list", "Membres", "users"),
        ("roles", "roles:roles_list", "Rôles & droits", "shield"),
        ("settings_global", "settings:settings_brand", "Réglages de l'asso", "sliders"),
        ("audit", "audit:audit_list", "Journal d'audit", "list"),
        ("backup", "settings:settings_backup", "Sauvegarde", "save"),
        ("centrale", "centrale:index", "Centrale", "grid"),
    ]),
]


def _brand() -> dict:
    try:
        return Setting.brand()
    except Exception:
        return settings._INSTANCE.get("branding", {}) if hasattr(settings, "_INSTANCE") else {}


def _logo_url(valeur: str) -> str:
    """Transforme le logo enregistré en URL servable.

    Le logo est téléversé dans media/branding/ et seul son chemin relatif est
    conservé en base. Or media/ n'est monté qu'en DEBUG : en production, c'est
    la route /fichiers/ qui sert les médias. Une URL absolue saisie avant
    l'arrivée du téléversement reste utilisable telle quelle.
    """
    if not valeur:
        return ""
    if valeur.startswith(("http://", "https://", "/")):
        return valeur
    return "/fichiers/%s" % valeur.lstrip("/")


def association(request):
    brand = _brand()
    nom = brand.get("nom") or "MDL"
    lycee = brand.get("lycee") or ""
    return {
        "asso_nom": nom,
        "asso_sigle": brand.get("sigle") or nom[:4].upper(),
        "asso_lycee": lycee,
        "asso_ville": brand.get("ville") or "",
        "asso_contact": brand.get("contact") or "",
        "asso_logo": _logo_url(brand.get("logo") or ""),
        "asso_couleur": brand.get("couleur_principale") or "#33556e",
        "asso_titre": ("%s — %s" % (nom, lycee)) if lycee else nom,
        "version": getattr(settings, "VERSION", ""),
        "maintenance_active": bool(settings.MAINTENANCE),
    }


def theme(request):
    forced = {}
    try:
        forced = Setting.forced_theme()
    except Exception:
        forced = {}
    user = getattr(request, "user", None)
    prefs = getattr(user, "prefs", None) or {} if getattr(user, "is_authenticated", False) else {}
    palette = forced.get("palette") or prefs.get("palette") or "ardoise"
    mode = forced.get("mode") or prefs.get("mode") or "light"
    density = prefs.get("density") or "confort"
    try:
        year = None
        from core.models import SchoolYear

        year = SchoolYear.current()
    except Exception:
        year = None
    return {
        "palette": palette,
        "mode": mode,
        "density": density,
        "theme_impose": bool(forced.get("palette") or forced.get("mode")),
        "palette_seed": forced.get("seed") or "",
        "current_year": year,
        "years_available": _years(),
    }


def _years():
    try:
        from core.models import SchoolYear

        return list(SchoolYear.objects.order_by("-start_date")[:8])
    except Exception:
        return []


def nav(request):
    user = getattr(request, "user", None)
    groups = []
    for group_key, entries in NAV_GROUPS:
        items = []
        for module, url_name, label, icon in entries:
            if module == "centrale":
                if not permissions.is_administrator(user):
                    continue
            elif not permissions.can_view(user, module):
                continue
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                continue
            items.append({
                "module": module,
                "url": url,
                "label": label,
                "icon": icon,
                "active": request.path.startswith(url) if url != "/" else request.path == "/",
                "can_edit": permissions.can_edit(user, module),
            })
        if items:
            groups.append({"key": group_key, "items": items})
    pending = 0
    try:
        from core.models import Intervention

        pending = Intervention.pending().count()
    except Exception:
        pending = 0
    unread = 0
    try:
        from mail.services import unread_count

        unread = unread_count(user)
    except Exception:
        unread = 0
    unread_notifs = 0
    try:
        from notifications.models import Notification

        if user is not None and getattr(user, "is_authenticated", False):
            unread_notifs = Notification.objects.filter(user=user, read_at__isnull=True).count()
    except Exception:
        unread_notifs = 0
    return {"nav_groups": groups, "nav_pending_interventions": pending, "nav_unread": unread,
            "nav_unread_notifs": unread_notifs}
