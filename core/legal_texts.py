"""Textes légaux par défaut : RGPD, charte, mentions, règlement.

Générés à la demande (bouton Réglages → Textes, bouton de l'assistant,
`manage.py seed`) : ils ne sont jamais imposés par-dessus un texte déjà
écrit par l'association. La charte exige une acceptation horodatée.
"""
from __future__ import annotations

MENTIONS = """# Mentions légales

## Éditeur
Le présent site est édité par **{nom}** ({sigle}){lycee}{ville} — contact :
**{contact}**.

Directeur de la publication : le bureau de l'association, représenté par son ou sa
président·e en exercice.

## Hébergement
**alwaysdata** — 62 rue Tiquetonne, 75002 Paris, France — <https://www.alwaysdata.com>.
Les fichiers (documents, photos) sont hébergés chez alwaysdata ou, si l'association l'a
choisi dans Réglages → Stockage, chez le fournisseur tiers indiqué aux membres
(Backblaze, Cloudflare ou équivalent).

## Objet
{nom} est la maison des lycéens de {lycee_nom} : le site organise la vie de
l'association (membres, documents, trésorerie, plannings, ménage, messages).

## Propriété et responsabilités
Les contenus déposés restent la propriété de leurs auteurs ; l'association ne revendique
aucun droit au-delà de l'organisation de ses activités. Les espaces sont réservés aux
membres : toute connexion est authentifiée et journalisée.
"""

RGPD = """# Politique de protection des données personnelles (RGPD)

## Responsable du traitement
**{nom}** ({contact}) détermine les finalités ci-dessous. Aucune donnée n'est vendue ni
louée ; il n'existe aucun traitement automatisé produisant des effets juridiques.

## Données traitées, finalités et bases légales
- **Comptes membres** (nom, prénom, courriel, rôle, historique de rôles) : gestion des
  adhésions et des droits d'accès — *exécution du contrat d'adhésion*.
- **Trésorerie** (écritures, relevés importés, pièces) : tenue de la comptabilité —
  *obligation légale*.
- **Documents** (fichiers déposés, métadonnées, journalisations de consultation) :
  organisation de la vie associative — *intérêt légitime*.
- **Plannings et ménage** (disponibilités, tâches attribuées, photos de tâche faite) :
  organisation des obligations des membres — *intérêt légitime* ; la photo est un simple
  justificatif.
- **Messagerie interne et notifications** : communication du bureau — *intérêt légitime*.
- **Sécurité** (journal des connexions, journal d'audit, tentatives échouées) :
  protection du site — *intérêt légitime*.

## Destinataires
Seuls les membres habilités par rôle (bureau, administrateurs) accèdent aux données,
chacun dans la limite de ses droits. L'hébergeur (alwaysdata, France) et, le cas
échéant, le fournisseur de stockage choisi par l'association, en sont destinataires
techniques.

## Durées de conservation
- Comptes et profils : durée de l'adhésion, puis suppression ou anonymisation à la
  demande ; un compte supprimé ne laisse **aucune trace nominative**.
- Pièces et écritures comptables : **10 ans** (obligation légale).
- Journal d'audit : **5 ans**.
- Photos de tâche de ménage : **supprimées immédiatement après validation** de la tâche.
- Journaux de connexion et tentatives : **1 an**.
- Sauvegardes : durée de conservation choisie par l'association, 30 jours pour la
  corbeille de documents.

## Vos droits
Vous pouvez exercer vos droits d'**accès**, de **rectification**, d'**effacement**, de
**limitation**, d'**opposition** et de **portabilité**, ainsi que définir des directives
post-mortem, en écrivant à {contact}. L'outil offre en outre, dans « Mes paramètres » :
l'**export JSON** de vos données, l'**anonymisation** et la **suppression définitive** de
votre compte. Réponse sous un mois.

## Cookies et traceurs
Un unique cookie technique de session (connexion) ; aucun cookie publicitaire, aucun
traceur d'audience.

## Sécurité
Mots de passe hachés, verrouillage après tentatives répétées, authentification à deux
facteurs disponible, médias servis par des vues authentifiées, journalisation des accès.

## Réclamation
Sans réponse satisfaisante, vous pouvez saisir la **CNIL** (cnil.fr, 3 place de Fontenoy,
75007 Paris).
"""

REGLEMENT = """# Règlement intérieur — extrait relatif à l'outil numérique

Le présent extrait vaut annexe au règlement intérieur de **{nom}** ; il encadre l'usage
de la plateforme de gestion.

## Accès selon les rôles
Chaque membre reçoit un compte personnel dont l'étendue dépend de son rôle (membre,
bureau, administration). Les habilitations sont attribuées par un administrateur et
peuvent être retirées à tout moment (départ, exclusion, fin de mandat).

## Obligations des membres
- Répondre aux campagnes (disponibilités, ménage) dans les délais fixés par le bureau ;
- justifier ses tâches de ménage par une photo, laquelle est supprimée après validation ;
- tenir ses informations à jour et signaler toute perte d'accès.

## Vie associative
Les documents déposés restent consultables selon les catégories définies par le bureau ;
la trésorerie est réservée aux rôles habilités ; les décisions engageant l'association ne
se prennent pas dans la messagerie interne.

## Sanctions
Le non-respect de la charte d'utilisation ou du règlement peut entraîner la suspension du
compte, puis les sanctions prévues aux statuts.
"""

CHARTE = """# Charte d'utilisation de la plateforme

La présente charte s'impose à tout membre disposant d'un compte sur la plateforme de
**{nom}**. Son acceptation est enregistrée avec horodatage ; toute nouvelle version
publiée doit être acceptée à la connexion suivante.

## 1. Compte et authentification
Le compte est **strictement personnel**. Le mot de passe ne se partage jamais, ni avec un
ami ni avec un membre du bureau ; toute perte ou usurpation soupçonnée se signale
immédiatement au contact de l'association. L'authentification à deux facteurs est
fortement recommandée, et peut être imposée par rôle.

## 2. Bons usages
- Ne déposer que des documents et photos **utiles à la vie associative** ;
- ne pas déposer de données sensibles sans nécessité (santé, opinions, etc.) ;
- la messagerie interne sert aux activités de l'association : ton courtois, pas de
  prosélytisme ni de contenu offensant ;
- ne pas tenter d'accéder à des espaces non ouverts à son rôle, ni d'extraire des données
  en masse.

## 3. Données des autres membres
Ce que l'on voit dans l'outil (coordonnées, tâches, messages) est **confidentiel** :
interdiction de le copier, diffuser ou réutiliser hors des besoins de l'association, y
après son départ.

## 4. Photos et droit à l'image
Les photos déposées (tâche de ménage, pièces) ne servent qu'à leur objet et sont
supprimées dès qu'elles ne sont plus nécessaires ; aucune n'est publiée hors de la
plateforme sans accord séparé.

## 5. Sanctions et évolution
Tout manquement peut entraîner la suspension du compte. Les modifications de la charte
sont publiées en nouvelle version : l'usage continu du service après acceptation vaut
adhésion à la version en vigueur.
"""


def _corps(modele: str, branding: dict) -> str:
    return modele.format(
        nom=branding.get("nom") or "l'association",
        sigle=branding.get("sigle") or "MDL",
        lycee=(" — lycée %s" % branding["lycee"]) if branding.get("lycee") else "",
        lycee_nom=branding.get("lycee") or "l'établissement",
        ville=(" — %s" % branding["ville"]) if branding.get("ville") else "",
        contact=branding.get("contact") or "le bureau de l'association",
    )


def textes_par_defaut() -> list[dict]:
    """Les quatre textes, personnalisés avec la marque de l'association."""
    from core.models import Setting

    marque = Setting.data().get("branding", {})
    return [
        {"kind": "mentions", "title": "Mentions légales", "slug": "mentions-legales",
         "requires_acceptance": False, "body": _corps(MENTIONS, marque)},
        {"kind": "rgpd", "title": "Données personnelles (RGPD)", "slug": "rgpd",
         "requires_acceptance": False, "body": _corps(RGPD, marque)},
        {"kind": "reglement", "title": "Règlement intérieur (extrait numérique)",
         "slug": "reglement-interieur", "requires_acceptance": False,
         "body": _corps(REGLEMENT, marque)},
        {"kind": "charte", "title": "Charte d'utilisation", "slug": "charte-utilisation",
         "requires_acceptance": True, "body": _corps(CHARTE, marque)},
    ]


def ensure_legal_texts(actor=None) -> int:
    """Crée les textes manquants ; ne touche jamais à un texte existant."""
    from core.models import LegalDocument

    created = 0
    for texte in textes_par_defaut():
        if LegalDocument.objects.filter(slug=texte["slug"]).exists():
            continue
        LegalDocument.objects.create(**texte, published=True, updated_by=actor)
        created += 1
    return created
