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
  clôtures mensuelles bloquantes, import avec mapping et détection de doublons, bilan annuel Excel.
* Planning de la salle : campagnes, deux grilles Q1/Q2, plage du soir réservée aux internes,
  contrôle de couverture, publication PDF 4 pages, demandes d'échange.
* Planning de ménage : sondage avec plafond de refus, allocation déterministe et équitable,
  suivi avec preuve photo supprimée à la validation.
* Messagerie : diffusions, accusés de lecture, relances plafonnées, file `Outbox` lissée à
  15 e-mails/minute avec 3 essais.

### Exploitation
* Assistant d'installation web en 6 étapes + `install.py` / `install.sh`.
* 25 commandes de gestion idempotentes (`cron:run`, `bilans`, `mail:drain`, `backup`, `devtoken`…).
* Hub éditeur séparé (`hub/`) : interventions bornées, télémétrie opt-in, mises à jour avec
  sauvegarde et retour arrière.
