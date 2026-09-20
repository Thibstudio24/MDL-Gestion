# Journal des versions

## 1.0.0

Première version livrée d'un bloc.

### Socle
* `settings.py` multi-bases (SQLite / PostgreSQL / MariaDB) lit `config/instance.json`, les
  variables `MDL_*` étant prioritaires.
* Middlewares : mur de connexion strict, en-têtes de sécurité (CSP, HSTS, Permissions-Policy),
  mode maintenance, contexte d'audit.
* Thème généré dynamiquement par `/theme.css` : 6 palettes × clair/sombre/auto + palette dérivée
  « couleurs du lycée », densité confort/compacte, feuille d'impression dédiée.
* Marque de l'association : nom, sigle, lycée, ville, contact, couleur, et logo téléversé
  depuis l'ordinateur ou le téléphone (1 Mo, rangé dans `media/branding/`).
* PWA : `manifest.webmanifest` dynamique, service worker (coquille + repli hors ligne),
  page `/hors-ligne/`, icônes générées sans Pillow.

### Comptes, droits, sécurité
* E-mail comme identifiant, invitation à usage unique (lien + code court 6 caractères),
  verrouillage 5 tentatives / 15 minutes, sessions 14 jours révocables, ré-authentification.
* A2F TOTP (RFC 6238) avec QR SVG inline et 10 codes de récupération hachés. Un rôle peut
  l'imposer (`force_2fa`) : l'inscription est alors demandée dès la première connexion,
  reportable jusqu'au délai fixé, obligatoire ensuite.
* Droits par module × niveau + 10 droits fins, cache 300 s invalidé à chaque changement de rôle.
  Le rôle Administrateur ne peut être attribué (invitation ou changement de rôle) que par un
  administrateur ; les autres rôles ne voient même pas l'option.
* RGPD : anonymisation, export JSON des données d'un compte, textes légaux versionnés, et
  suppression définitive d'un compte sans laisser de traces (admin, confirmation tapée).
* Cloche de notifications : widget déroulant des non-lues (un clic = marqué lu + ouverture de
  la page concernée, « Tout marquer lu »), compteur propre aux notifications ; le chiffre à
  côté de « Messages » compte les courriels non lus (la source était inversée auparavant).
* Réglages → Sauvegarde : « Zone dangereuse » — réinitialisation complète du site à l'état
  neuf (admin ré-authentifié, confirmation tapée), retour à l'assistant d'installation.

### Modules métier
* Documents : catégories, dossiers (2 niveaux), versions (3 conservées), corbeille 30 jours,
  quota avec alertes 80/95 %, verrouillage en lecture, médias servis par une vue privée.
  Une catégorie peut exiger un module en plus de Documents (`module_gate`) : « Bilans »
  exige la trésorerie.
* Trésorerie : grand livre unique, transferts neutres, comptage de caisse avec écart justifié,
  clôtures mensuelles bloquantes, import avec mapping et détection de doublons, bilan annuel
  Excel, export du grand livre en Excel / CSV / PDF. Les destinataires du bilan ne se
  choisissent pas : ils découlent du droit de consulter la trésorerie.
* Planning de la salle : une campagne par période (trimestre, semestre ou année), créneaux
  typés du lundi au dimanche avec capacité, réponses disponible / si besoin / indisponible,
  contrôle de couverture, relance des non-répondants, clôture, export CSV et PDF A4 paysage
  (grille + synthèse par membre).
* Planning de ménage : 5 tâches types, allocation déterministe et équitable, preuve photo
  exigée, validation ou renvoi motivé, photos purgées 180 jours après validation.
* Messagerie : diffusions descendantes, accusés de lecture, envoi programmé, file `Outbox`
  en base vidée par le cron (15 e-mails/minute par défaut, 5 essais avant abandon).
  Les réglages SMTP saisis à l'écran sont écrits dans `config/instance.json` (section
  `mail`, fichier en droits 600) et appliqués immédiatement, sans redémarrage ; le
  formulaire réaligne le port sur le mode coché (SSL 465 / STARTTLS 587) ; bouton
  « Vider la file maintenant » et erreur exacte du serveur affichée dans la file.
  Les courriels unitaires (invitation, réinitialisation, alerte de sécurité, rappel
  d'expiration) tentent un envoi immédiat et restent en file en cas d'échec ; une
  pompe de fond vide la file automatiquement toutes les ~15 s, sans cron ni bouton
  (statut « sending » réservant chaque courriel : aucun double envoi) ; au moment
  de l'envoi le mode est déduit du port (465 SSL, sinon STARTTLS), donc un vieux
  réglage incohérent ne bloque plus rien.
* Liens absolus dans les courriels (`https://site/page`) : invitation,
  réinitialisation de mot de passe et notifications avec lien (bilan,
  messagerie…) ; l'adresse de base est auto-détectée à la première visite et
  mémorisée dans `app.base_url` (prioritaire si posée à la main, repli sur le
  premier hôte de `app.allowed_hosts`).
* Une panne de notification in-app ou de push n'est plus jamais affichée comme
  « SMTP indisponible » : l'alerte avec code à transmettre n'apparaît que si le
  courriel n'a réellement pas pu être mis en file ou a échoué (détail dans
  Réglages → Envois) ; en file, un simple avis annonce le départ automatique.
  SQLite : timeout 20 s pour absorber les écritures concurrentes de la pompe.

* Ménage : les membres déclarent leurs jours de présence et les tâches qu'ils ne peuvent pas
  faire (respectées par l'attribution, au membre le moins chargé) ; le bureau choisit les tâches
  de la campagne (ajout/retrait avant publication, cinq tâches types pré-remplies) et réarrange
  chaque attribution (autre membre et/ou autre jour) après publication.

* Réinitialisation du site vraiment totale : après le vidage de toutes les tables, le fichier
  SQLite est reconstruit (VACUUM) et, si un stockage tiers est configuré, le bucket S3 est purgé ;
  la réinitialisation reste tracée dans le journal de la nouvelle installation.

* Stockage des fichiers au choix : disque du serveur (défaut) ou fournisseur tiers compatible
  S3 sans dépendance (client SigV4 maison, conforme au vecteur officiel AWS) — Backblaze B2
  10 Go gratuits sans CB, R2, Supabase… Choix à l'installation et dans Réglages → Stockage,
  avec test de connexion ; les fichiers déjà sur le disque restent servis. La région B2 est
  détectée depuis l'endpoint (sinon HTTP 403) et l'erreur exacte du fournisseur est affichée.
* Documents : la création de dossier n'exige plus de champs invisibles (« Ce champ est
  obligatoire » alors que tout était rempli) et propose un dossier parent ; la trame du bureau
  inclut le droit fin « Supprimer des documents » (corbeille 30 jours) et la fiche d'un document
  explique comment l'obtenir.

* Le site ne recrée plus jamais d'année scolaire à l'insu de l'association : après une
  réinitialisation (ou sur une installation neuve), trésorerie, plannings et ménage affichent une
  page « Aucune année scolaire » qui renvoie vers Réglages → Années scolaires. Fini l'année de
  test qui « réapparaît » après réinitialisation.

* Textes légaux générables en un clic (Réglages → Textes, bouton de l'assistant ou `seed`) :
  politique RGPD complète (finalités, bases légales, durées dont 10 ans comptables et photos de
  ménage supprimées après validation, droits, CNIL), charte d'utilisation à acceptation
  horodatée, mentions légales et extrait de règlement, personnalisés avec la marque de
  l'association ; un texte déjà écrit n'est jamais écrasé.

* Centrale super-admin : ce site peut superviser d'autres instances MDL Gestion (menu
  Centrale, admins) — heartbeat signé sha256 (install_id, secret, corps, horodatage ±5 min),
  compteurs et version par instance, raccordement/débranchement journalisés. Nouveau script
  `scripts/nouvelle_instance.sh <dépôt-github> <cible>` : clone le dépôt préféré, installe,
  migre, crée le super-admin (`manage.py mdl_admin`) et imprime install_id + secret à coller
  dans la centrale (`manage.py mdl_hub_infos`).
* Contrôle à distance depuis la centrale (ordres signés Ed25519 avec la clé privée de la
  centrale, livrés au heartbeat suivant) : réinitialisation du mot de passe d'un administrateur
  distant (le mot de passe provisoire choisi s'affiche pour transmission), blocage d'une
  instance (RGPD, non-conformité), déblocage, désactivation du 2FA. Toute action est journalisée.
* Filet de sécurité « kill-switch » côté instance : 14 jours sans contact avec la centrale
  configurée (ou blocage ordonné) verrouillent le site ; tout est renvoyé vers l'écran public
  `/deblocage/` (motif + contact informatique.mdl33@gmail.com). Déblocage possible hors ligne :
  la centrale télécharge un **fichier de déblocage signé** (`{"jeton": …}`), envoyé par courriel
  à l'association qui l'importe sur cet écran — valable même sans connexion rétablie.
  Clé privée de la centrale : `manage.py mdl_centrale_init --cle-privee "…"` (jamais dans le dépôt).

### Exploitation
* Assistant d'installation web en 4 étapes (identité, base, administrateur, récapitulatif) ;
  aucun compte de démonstration n'est créé. La clé secrète est générée à l'étape 2
  (50 caractères, `config/instance.json` en 600) ; seuls la base et les migrations sont
  bloquants à l'étape 1, et l'alerte nomme le contrôle en échec au lieu d'un conseil figé.
* 5 commandes de gestion idempotentes : `mdl_cron` (file SMTP, diffusions, rappels, bilan,
  purges), `mdl_backup`, `mdl_health`, `mdl_purge`, `seed` (référentiels seuls).
* Journal d'audit : 98 actions déclarées, jamais modifiable ligne à ligne, purge automatique
  après N années et vidage complet par l'administrateur.
* Suppressions disponibles partout où l'on peut créer : rôles, membres (désactivation et
  anonymisation), sauvegardes, campagnes de planning de salle et de ménage, écritures,
  dossiers, documents, créneaux, fermetures exceptionnelles.
* Canal éditeur (`core/views_devhub.py`, monté sur `/aide-intervention/`) : jeton
  d'intervention borné dans le temps, télémétrie opt-in, contrôle des mises à jour.
