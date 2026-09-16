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
* PWA : `manifest.webmanifest` dynamique, service worker (coquille + repli hors ligne),
  page `/hors-ligne/`, icônes générées sans Pillow.

### Comptes, droits, sécurité
* E-mail comme identifiant, invitation à usage unique (lien + code court 6 caractères),
  verrouillage 5 tentatives / 15 minutes, sessions 14 jours révocables, ré-authentification.
* A2F TOTP (RFC 6238) avec QR SVG inline et 10 codes de récupération hachés.
* Droits par module × niveau + 10 droits fins, cache 300 s invalidé à chaque changement de rôle.
* RGPD : anonymisation, export JSON des données d'un compte, textes légaux versionnés.

### Modules métier
* Documents : catégories, dossiers (2 niveaux), versions (3 conservées), corbeille 30 jours,
  quota avec alertes 80/95 %, verrouillage en lecture, médias servis par une vue privée.
* Trésorerie : grand livre unique, transferts neutres, comptage de caisse avec écart justifié,
  clôtures mensuelles bloquantes, import avec mapping et détection de doublons, bilan annuel
  Excel, export du grand livre en Excel / CSV / PDF.
* Planning de la salle : une campagne par période (trimestre, semestre ou année), créneaux
  typés du lundi au dimanche avec capacité, réponses disponible / si besoin / indisponible,
  contrôle de couverture, relance des non-répondants, clôture, export CSV et PDF A4 paysage
  (grille + synthèse par membre).
* Planning de ménage : 5 tâches types, allocation déterministe et équitable, preuve photo
  exigée, validation ou renvoi motivé, photos purgées 180 jours après validation.
* Messagerie : diffusions descendantes, accusés de lecture, envoi programmé, file `Outbox`
  en base vidée par le cron (15 e-mails/minute par défaut, 5 essais avant abandon).

### Exploitation
* Assistant d'installation web en 4 étapes (identité, base, administrateur, récapitulatif) ;
  aucun compte de démonstration n'est créé.
* 5 commandes de gestion idempotentes : `mdl_cron` (file SMTP, diffusions, rappels, bilan,
  purges), `mdl_backup`, `mdl_health`, `mdl_purge`, `seed` (référentiels seuls).
* Canal éditeur (`core/views_devhub.py`, monté sur `/aide-intervention/`) : jeton
  d'intervention borné dans le temps, télémétrie opt-in, contrôle des mises à jour.
