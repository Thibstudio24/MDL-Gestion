# Architecture

Vue d'ensemble technique de MDL Gestion. Ce document décrit ce qui est
effectivement dans le dépôt ; les textes destinés aux utilisateurs sont dans
[MODE-EMPLOI.md](MODE-EMPLOI.md) et dans l'application à l'adresse `/aide/`.

## Principe

Une seule association par installation. Django 5.2, PostgreSQL / MariaDB /
SQLite, aucun service annexe : pas de Celery, pas de Redis, pas de DRF, pas de
Pillow, pas d'outillage frontal. Tout ce qui devrait être asynchrone passe par
une table en base vidée par le cron.

La cible d'exécution est l'offre gratuite d'alwaysdata : 1 Go de disque,
256 Mo de mémoire, 1/4 de CPU, un sous-domaine `*.alwaysdata.net`, HTTPS, cron
et SMTP inclus. D'où un seul worker uWSGI, `reportlab` plutôt que WeasyPrint,
et une file d'attente en base plutôt qu'un broker.

## Applications

| Application | Modèles | Rôle |
| --- | --- | --- |
| `core` | `Setting`, `SchoolYear`, `ClosureDay`, `LegalDocument`, `Installation`, `Intervention` | réglages, années scolaires, jours de fermeture, textes légaux, identité d'installation et jetons d'intervention |
| `accounts` | `Role`, `RolePermission`, `User`, `RoleMembership`, `Invitation`, `RecoveryCode`, `AccountSession`, `LoginAttempt`, `LegalAcceptance`, `UserProfileExtra` | comptes, rôles, invitations, A2F, sessions, tentatives de connexion |
| `audit` | `AuditEntry` | journal immuable des actions sensibles |
| `notifications` | `Notification`, `PushDevice`, `NotificationPreference` | 23 événements, matrice de diffusion, appareils push |
| `documents` | `Category`, `CategoryAccess`, `Folder`, `Document`, `DocumentFile`, `DocumentViewLog` | GED : catégories, dossiers, versions, corbeille, quota |
| `finance` | `Account`, `AccountOpening`, `Category`, `MonthLock`, `Entry`, `CashCount`, `ImportBatch`, `BalanceRun` | grand livre, comptes, clôtures, comptages, imports, bilans |
| `plannings` | `Campaign`, `Slot`, `Availability` | planning de la salle |
| `chores` | `Campaign`, `Assignment`, `Response` | planning de ménage |
| `mail` | `Broadcast`, `Recipient`, `Outbox` | messagerie descendante et file SMTP |
| `installer` | — | assistant de première installation (4 étapes) |

## Configuration

`config/settings.py` lit `config/instance.json` (posé par l'assistant
d'installation). Les variables d'environnement `MDL_*` sont toujours
prioritaires sur le fichier : c'est ce qui permet de coller les réglages dans
le panneau alwaysdata sans toucher au disque. `config/instance.example.json`
est le modèle versionné, utilisé par la CI.

Les réglages modifiables par l'administration vivent dans `core.Setting`
(une ligne JSON unique) et surchargent le fichier. Les valeurs par défaut sont
déclarées dans `core/models.py::_DEFAULTS`.

## Droits

`core/permissions.py` définit 11 modules — `dashboard`, `members`, `roles`,
`documents`, `finance`, `planning_salle`, `planning_menage`, `mail`, `audit`,
`backup`, `settings_global` — chacun noté 0 (aucun), 1 (consulter) ou
2 (modifier), plus 10 droits fins :

```
documents.import   documents.export   documents.delete   documents.categories
finance.lock       finance.import     finance.export
mail.schedule      members.invite     settings.push
```

Le résultat est mis en cache 300 s sous la clé `perm:<id>` et invalidé à chaque
modification de rôle. Un compte désactivé ou anonymisé ne conserve aucun droit.

Les décorateurs `module_required`, `fine_required`, `administrator_required`,
`reauth_required` et `require_POST` protègent les vues.

## Chaîne de traitement horaire

`python manage.py mdl_cron` enchaîne, dans l'ordre : vidage de la file SMTP,
envoi des diffusions programmées, rappels de ménage, génération du bilan si
l'échéance est atteinte, clôture des campagnes expirées, alertes de quota et
purges. Chaque étape est indépendante : une exception n'interrompt pas les
suivantes.

## Exports

`core/export.py` produit en mémoire (BytesIO) du CSV, du XLSX (openpyxl) et du
PDF A4 paysage (reportlab). `finance/pdf.py` et `plannings/pdf.py` composent
leurs documents à partir de ces briques. Aucun fichier temporaire n'est écrit
sur le disque.

## Tests et CI

183 tests pytest dans `tests/`, exécutés par GitHub Actions sur Python 3.11 et
3.12 avec Django 5.2. La CI rejoue `manage.py check`,
`makemigrations --check --dry-run`, `migrate` puis `pytest --cov`, et fait
tourner `ruff` et `bandit -ll` en parallèle.

Pendant les tests, `settings.TESTING` est vrai : la redirection HTTPS et les
cookies `Secure` sont désactivés, sinon le client de test — qui parle HTTP —
recevrait des 301 sur toutes les pages.
