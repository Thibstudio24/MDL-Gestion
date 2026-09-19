# MDL Gestion

Application web privée de gestion d'une **Maison des Lycéens** (MDL) : les élèves tiennent une
salle (permanence, jeux, baby-foot, billard, documentation) et gèrent leur trésorerie.

* **Intranet associatif** — accès sur invitation uniquement, aucun formulaire public.
* **Mono-association** — 1 installation = 1 association ; toute autre asso installe sa propre copie.
* **Cible d'exécution** — alwaysdata plan Free : 1 Go de disque, 256 Mo de RAM, 1/4 de CPU,
  sous-domaine `*.alwaysdata.net`, HTTPS, cron et SMTP inclus.
* **Aucun build frontend** — pas de Node, pas de Sass, pas de Tailwind, pas de CDN, pas de
  Celery/Redis, pas de DRF, pas de Pillow, pas de crispy-forms. Une feuille CSS écrite à la main,
  ~25 Ko de JS vanilla et Chart.js servi en local.

## Modules

| Module | Contenu |
| --- | --- |
| Tableau de bord | 12 tuiles prédéfinies, filtrées par droits, jamais vides |
| Documents | catégories, sous-dossiers (un par club), versions, corbeille, quota, aperçu PDF |
| Trésorerie | grand livre, comptes (banque / coffre), comptages de caisse, clôtures mensuelles, import CSV/QIF/OFX, bilan annuel Excel, export Excel/CSV/PDF |
| Planning de la salle | campagnes de disponibilités par période (trimestre / semestre / année), créneaux et capacités, couverture, export PDF A4 paysage |
| Planning de ménage | 5 tâches types, répartition automatique équitable, preuve photo purgée 180 jours après validation |
| Messagerie | diffusions descendantes, accusés de lecture, envoi programmé, file d'attente SMTP en base |
| Membres & droits | invitations, A2F TOTP, rôles (module × Aucun/Consulter/Modifier + droits fins), RGPD |
| Réglages | marque, années scolaires, quotas, notifications, SMTP, PWA/push, sauvegarde, mises à jour |

## Démarrage rapide (SQLite, 3 minutes)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

Puis ouvrir <http://127.0.0.1:8000/installation/> et suivre l'assistant en quatre étapes
(identité, base de données, compte administrateur, récapitulatif).

## Déploiement alwaysdata

Voir [`docs/INSTALL-ALWAYSDATA.md`](docs/INSTALL-ALWAYSDATA.md) : création du compte, base SQL,
boîte SMTP, site Python WSGI, assistant d'installation, ligne de cron, clés VAPID.

## Tests

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
```

## Documentation

* [`docs/MODE-EMPLOI.md`](docs/MODE-EMPLOI.md) — 26 sections + FAQ + glossaire + check-list
* [`docs/INSTALL-ALWAYSDATA.md`](docs/INSTALL-ALWAYSDATA.md) — déploiement pas à pas sur le plan Free
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — applications, modèles, droits, exports
* [`docs/SECURITE-CONFORMITE.md`](docs/SECURITE-CONFORMITE.md) — sécurité, RGPD, canal éditeur

`docs/MODE-EMPLOI.md` et `docs/INSTALL-ALWAYSDATA.md` sont générés depuis
`core/help_content.py` — la même source que l'aide en ligne `/aide/` — par
`python scripts/make_docs.py`. Ne les modifiez pas à la main.

## Licence

AGPL-3.0 — voir [`LICENSE`](LICENSE).
By Thibstudio24
Idée originale de Lindeku-lab
