# Sécurité et conformité

Ce document décrit les mécanismes réellement présents dans le code. Chaque
affirmation renvoie au fichier qui l'implémente.

## Accès

Aucun formulaire public. `core/middleware.py::RequireLoginMiddleware` exige une
session sur toute URL qui n'est pas dans `MDL_PUBLIC_URLS` :

```
/connexion/  /mot-de-passe/oubli/  /reinitialiser/  /inviter/  /installation/
/theme.css   /manifest.webmanifest /service-worker.js /hors-ligne/ /sante/
/favicon.ico /robots.txt           /static/
```

L'entrée se fait uniquement par invitation à usage unique (lien + code court de
6 caractères, `accounts/models.py::Invitation`).

## Mots de passe

`config/settings.py::PASSWORD_HASHERS` utilise Argon2 lorsqu'il est installé
sur le serveur, et retombe sinon sur `MdlPBKDF2SHA256Hasher`.

Quatre validateurs (`core/validators.py`) :

| Validateur | Effet |
| --- | --- |
| `MinLengthValidator` | 10 caractères minimum (réglable) |
| `CommonPasswordListValidator` | refuse ~1 250 mots courants, claviers et années |
| `NumericPasswordValidator` | refuse un mot de passe uniquement numérique |
| `PersonalDataValidator` | refuse le prénom, le nom et l'e-mail du membre |

## Connexion

* Verrouillage après **5 échecs pendant 15 minutes** (`login_max_attempts`,
  `login_lockout_minutes`).
* Sessions de **14 jours**, cookie `HttpOnly`, `SameSite=Lax`, `Secure` hors
  debug ; sessions listées et révocables (`accounts/models.py::AccountSession`).
* **Ré-authentification** exigée pour les actions sensibles : le tampon
  `reauth_at` n'est valable que 10 minutes
  (`core/decorators.py::reauth_required`).

## Deux facteurs

TOTP RFC 6238 (`accounts/twofa.py`) : 6 chiffres, période de 30 secondes,
émetteur « MDL Gestion ». Le QR est rendu en SVG inline par `segno`, sans
service tiers. Dix codes de récupération à usage unique sont générés, hachés en
SHA-256 en base et affichés une seule fois.

Un compte dont l'A2F n'est pas confirmée dans les 14 jours
(`delai_2fa_jours`) est relancé.

## En-têtes HTTP

`core/middleware.py::SecurityHeadersMiddleware` pose sur chaque réponse :

```
X-Frame-Options: DENY
Referrer-Policy: same-origin
X-Content-Type-Options: nosniff
Permissions-Policy: geolocation=(), camera=(), microphone=(), payment=(),
                    usb=(), accelerometer=(), gyroscope=(), magnetometer=()
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline';
                    style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;
                    font-src 'self' data:; connect-src 'self';
                    frame-src 'self' data: blob:; manifest-src 'self';
                    worker-src 'self'; object-src 'none'; form-action 'self';
                    base-uri 'self'; frame-ancestors 'none'
Cross-Origin-Opener-Policy: same-origin-allow-popups
Strict-Transport-Security: max-age=31536000; includeSubDomains   (hors debug)
```

`'unsafe-inline'` reste nécessaire aux styles posés par les gabarits ; aucun
CDN n'est appelé, Chart.js est servi depuis `static/vendor/`.

Hors debug, `SECURE_SSL_REDIRECT` renvoie toute requête HTTP en 301 vers HTTPS.
Ce réglage est désactivé pendant les tests (`settings.TESTING`), sans quoi le
client de test ne recevrait que des redirections.

## Journal d'audit

`audit/models.py::AuditEntry` refuse toute modification et toute suppression :
`save()` lève une `ValueError` dès que la ligne existe, `delete()` lève
toujours. La purge passe par `purge_audit(years)` et conserve 5 ans par défaut
(`audit_keep_years`).

## Fichiers

16 extensions acceptées, 13 refusées dont les exécutables
(`documents/services.py::ACCEPTED` / `REFUSED`). Un fichier vide est refusé.
Quota par défaut : 400 Mo au total, 10 Mo par fichier, alertes à 80 % et 95 %.
Les médias ne sont jamais servis en statique : `documents/views.py::download`
et `::preview` ouvrent le fichier derrière le contrôle de droits.

## RGPD

* **Export** — `core/export.py::user_export` produit un JSON de toutes les
  données d'un compte (compte, écritures, documents, disponibilités, tâches,
  messages, connexions). Accessible par le membre lui-même
  (`/reglages/donnees/export/`) et par l'administration.
* **Anonymisation** — `accounts/models.py::User.anonymize` passe le compte en
  `anonymized`, remplace l'identité par « Membre supprimé », l'adresse par
  `anonyme-<id>@supprime.invalid`, supprime la photo, vide le secret TOTP et
  les préférences. L'historique comptable et le journal d'audit restent
  lisibles, comme l'exige la conservation des pièces.
* **Durées de conservation** — corbeille des documents 30 jours, 3 versions
  conservées par document, photos de preuve de ménage 180 jours après
  validation, messages lus 180 jours, notifications 90 jours. Chaque purge
  accepte `--dry-run` et journalise son résultat.
* **Textes légaux** — `core/models.py::LegalDocument` est versionné ; chaque
  acceptation est horodatée dans `accounts/models.py::LegalAcceptance`.

## Secrets

`config/instance.json` est écrit avec les droits `0600`
(`config/settings.py::write_instance`). Les variables `MDL_*` permettent de ne
rien poser sur le disque : la `SECRET_KEY`, les identifiants SQL, le SMTP et
les clés VAPID peuvent venir de l'environnement.

## Canal éditeur

Aucun accès distant implicite. L'éditeur ne peut agir que par un jeton
**Ed25519** signé hors ligne, collé par un administrateur sur
`/aide-intervention/`. `core/crypto.py::verify` contrôle la version du jeton,
la signature, l'expiration, l'identifiant d'installation et une liste blanche
de quatre actions : `reset_password`, `disable_2fa`, `resend_invite`, `health`.
Chaque intervention est tracée dans `core/models.py::Intervention` et
révocable.
