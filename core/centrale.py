"""Contrôle à distance par la centrale super-admin (kill-switch RGPD).

La centrale (votre instance, hébergée chez vous) signe des jetons Ed25519 avec
SA clé privée ; chaque instance vérifie avec la clé publique ci-dessous,
embarquée dans le code : personne ne peut forger un ordre de blocage, de
déblocage ou de réinitialisation de mot de passe.

Règle des 14 jours : une instance configurée pour rejoindre la centrale mais
qui ne la contacte plus (site trafiqué, hub coupé…) se verrouille d'elle-même
14 jours après le dernier contact. Pour la rouvrir sans réseau : la centrale
envoie par courriel un fichier de déblocage signé, à importer sur l'écran de
verrouillage.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core import crypto

CONTACT_DEBLOCAGE = "informatique.mdl33@gmail.com"
DELAI_SANS_CENTRALE_JOURS = 14

# Clé publique Ed25519 de la centrale super-admin (la clé privée ne vit QUE sur
# le serveur de la centrale, jamais dans ce dépôt).
CENTRALE_PUBLIC_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAvxXKGTxRohsnvwES+2v3r3SSdHDHca/sGlX80OulGGA=
-----END PUBLIC KEY-----
"""

def verifier_jeton(token: str, install_id: str) -> dict:
    """Côté instance : valide un ordre venu de la centrale."""
    return crypto.verify(token, CENTRALE_PUBLIC_PEM, install_id)


def hub_configure() -> bool:
    return bool(getattr(settings, "HUB_URL", ""))


def etat_verrou(install) -> tuple[bool, str]:
    """Une instance se verrouille si la centrale l'ordonne ou si elle ne la
    contacte plus depuis 14 jours (et qu'aucun fichier de déblocage récent ne
    la couvre)."""
    if install.locked:
        return True, install.lock_reason or "blocage ordonné par la centrale"
    if not hub_configure():
        return False, ""
    maintenant = timezone.now()
    if install.grace_until and install.grace_until > maintenant:
        return False, ""
    reference = install.last_ping_at or install.created_at
    if reference is None:
        return False, ""
    if maintenant - reference > timedelta(days=DELAI_SANS_CENTRALE_JOURS):
        return True, ("aucun contact avec la centrale depuis plus de %d jours"
                      % DELAI_SANS_CENTRALE_JOURS)
    return False, ""


def appliquer_jeton(token: str, actor=None) -> dict:
    """Côté instance : vérifie puis exécute un ordre de la centrale."""
    from accounts.services import apply_remote_action
    from core.models import Installation

    resultat = verifier_jeton(token, Installation.get().install_id)
    if not resultat["ok"]:
        return resultat
    return apply_remote_action(resultat["action"], resultat["target"] or resultat["reason"],
                               actor=actor, code=resultat["code"])
