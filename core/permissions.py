"""Système de droits : module × niveau (Aucun / Consulter / Modifier) + droits fins.

Le cache ``perm:<id>`` vit 300 s et est invalidé à chaque modification de rôle.
"""
from __future__ import annotations

from collections import OrderedDict

from django.core.cache import cache

LEVEL_NONE = 0
LEVEL_VIEW = 1
LEVEL_EDIT = 2

LEVEL_CHOICES = [
    (LEVEL_NONE, "Aucun"),
    (LEVEL_VIEW, "Consulter"),
    (LEVEL_EDIT, "Modifier"),
]
LEVEL_LABELS = {LEVEL_NONE: "Aucun", LEVEL_VIEW: "Consulter", LEVEL_EDIT: "Modifier"}

MODULES: OrderedDict[str, str] = OrderedDict(
    [
        ("dashboard", "Tableau de bord"),
        ("members", "Membres & invitations"),
        ("roles", "Rôles & droits"),
        ("documents", "Documents"),
        ("finance", "Trésorerie"),
        ("planning_salle", "Planning de la salle"),
        ("planning_menage", "Planning de ménage"),
        ("mail", "Messagerie interne"),
        ("audit", "Journal d'audit"),
        ("backup", "Sauvegarde & restauration"),
        ("settings_global", "Réglages de l'association"),
    ]
)

# clé → (libellé UI, module porteur, accordé automatiquement par « Modifier »)
FINE_PERMISSIONS: OrderedDict[str, tuple] = OrderedDict(
    [
        ("documents.import", ("Importer des documents", "documents", True)),
        ("documents.export", ("Exporter les documents", "documents", True)),
        ("documents.delete", ("Supprimer des documents", "documents", False)),
        ("documents.categories", ("Gérer les catégories et dossiers", "documents", False)),
        ("finance.lock", ("Clôturer et rouvrir un mois", "finance", False)),
        ("finance.import", ("Importer un relevé", "finance", True)),
        ("finance.export", ("Exporter la trésorerie", "finance", True)),
        ("mail.schedule", ("Programmer un envoi différé", "mail", True)),
        ("members.invite", ("Inviter un membre", "members", True)),
        ("settings.push", ("Régler les notifications et le push", "settings_global", True)),
    ]
)

DEFAULT_LEVELS = {
    "Administrateur": {mod: LEVEL_EDIT for mod in MODULES},
    "Utilisateur": {
        "dashboard": LEVEL_VIEW,
        "documents": LEVEL_EDIT,
        "planning_salle": LEVEL_EDIT,
        "planning_menage": LEVEL_EDIT,
        "mail": LEVEL_VIEW,
    },
}

BOARD_ROLES = [
    "Président·e",
    "Vice-président·e",
    "Trésorier·e",
    "Vice-trésorier·e",
    "Secrétaire",
    "Vice-secrétaire",
    "Membre du bureau",
]

# Trame de droits proposée par l'assistant d'installation pour les rôles du bureau.
BOARD_TEMPLATE = {
    "Président·e": {"dashboard": 2, "members": 2, "documents": 2, "finance": 1, "planning_salle": 2,
                    "planning_menage": 2, "mail": 2, "audit": 1, "backup": 1, "settings_global": 1,
                    "fine": ["members.invite", "documents.categories"]},
    "Vice-président·e": {"dashboard": 2, "members": 1, "documents": 2, "finance": 1, "planning_salle": 2,
                         "planning_menage": 2, "mail": 2, "fine": ["members.invite"]},
    "Trésorier·e": {"dashboard": 2, "documents": 2, "finance": 2, "mail": 2, "planning_salle": 1,
                    "planning_menage": 1, "fine": ["finance.lock", "finance.import"]},
    "Vice-trésorier·e": {"dashboard": 2, "documents": 2, "finance": 2, "mail": 2, "planning_salle": 1,
                         "planning_menage": 1, "fine": ["finance.lock", "finance.import"]},
    "Secrétaire": {"dashboard": 2, "members": 2, "documents": 2, "finance": 1, "mail": 2,
                   "planning_salle": 1, "planning_menage": 1, "fine": ["members.invite", "documents.categories"]},
    "Vice-secrétaire": {"dashboard": 2, "members": 1, "documents": 2, "mail": 2, "planning_salle": 1,
                        "planning_menage": 1},
    "Membre du bureau": {"dashboard": 1, "documents": 2, "planning_salle": 2, "planning_menage": 2,
                         "mail": 1, "finance": 1},
}

CACHE_TTL = 300
_CACHE_PREFIX = "perm:"


def cache_key(user) -> str:
    return "%s%s" % (_CACHE_PREFIX, getattr(user, "pk", "anon"))


def invalidate(user) -> None:
    """Invalide le cache des droits d'un membre (appelé à chaque changement de rôle)."""
    cache.delete(cache_key(user))


def invalidate_all() -> None:
    try:
        cache.clear()
    except Exception:  # pragma: no cover
        pass


def _load(user) -> dict:
    """Construit la carte des droits d'un membre (niveaux + droits fins)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return {"admin": False, "levels": {}, "fine": set()}
    if getattr(user, "status", "active") != "active" or not getattr(user, "is_active", True):
        # Un compte désactivé, en attente ou anonymisé n'a plus aucun droit (défense en profondeur).
        return {"admin": False, "levels": {}, "fine": set()}
    role = getattr(user, "role", None)
    if role is None:
        return {"admin": False, "levels": {}, "fine": set()}
    levels = {perm.codename: int(perm.level) for perm in role.permissions.all()}
    fine = set(role.fine_permissions or [])
    # « Modifier » sur le module accorde automatiquement les droits fins marqués auto.
    for key, (_label, module, auto) in FINE_PERMISSIONS.items():
        if auto and levels.get(module, LEVEL_NONE) >= LEVEL_EDIT:
            fine.add(key)
    return {"admin": bool(role.is_administrator), "levels": levels, "fine": fine}


def rights(user) -> dict:
    if user is None or not getattr(user, "is_authenticated", False):
        return {"admin": False, "levels": {}, "fine": set()}
    key = cache_key(user)
    data = cache.get(key)
    if data is None:
        data = _load(user)
        cache.set(key, data, CACHE_TTL)
    return data


def is_administrator(user) -> bool:
    return bool(rights(user)["admin"])


def level(user, module: str) -> int:
    if is_administrator(user):
        return LEVEL_EDIT
    if module == "roles" and not is_administrator(user):
        # « roles » n'est éditable que par un Administrateur.
        return LEVEL_NONE
    return int(rights(user)["levels"].get(module, LEVEL_NONE))


def can_view(user, module: str) -> bool:
    return level(user, module) >= LEVEL_VIEW


def can_edit(user, module: str) -> bool:
    return level(user, module) >= LEVEL_EDIT


def can(user, module: str, edit: bool = False) -> bool:
    return can_edit(user, module) if edit else can_view(user, module)


def fine(user, key: str) -> bool:
    if is_administrator(user):
        return True
    return key in rights(user)["fine"]


def summary(user) -> dict:
    """Résumé compact utilisé par la fiche membre et l'export des droits."""
    data = rights(user)
    return {
        "administrateur": data["admin"],
        "niveaux": {mod: data["levels"].get(mod, LEVEL_NONE) for mod in MODULES},
        "droits_fins": sorted(data["fine"]),
    }


def max_allowed_level(user) -> int:
    """Personne ne peut écrire un niveau supérieur à celui de son propre rôle."""
    if is_administrator(user):
        return LEVEL_EDIT
    levels = rights(user)["levels"]
    return max(levels.values()) if levels else LEVEL_NONE
