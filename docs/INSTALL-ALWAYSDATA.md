<!-- Ce fichier est généré par scripts/make_docs.py depuis core/help_content.py. -->
<!-- Ne pas modifier à la main : corriger core/help_content.py puis relancer le script. -->

# Installation sur alwaysdata (plan Free)

Déploiement de MDL Gestion sur l'offre gratuite d'alwaysdata : 1 Go de disque,
256 Mo de mémoire, 1/4 de CPU, sous-domaine `*.alwaysdata.net`, HTTPS, cron et
SMTP inclus. Comptez une demi-heure.

Les limites du plan Free sont suffisantes pour 10 à 25 comptes. Au-delà, passez
sur un plan payant ou découpez l'association en plusieurs installations.

## 3. Créer le compte alwaysdata

1. Créez un compte sur **alwaysdata** (plan Free).
2. Choisissez un sous-domaine : `mdl-lycee.alwaysdata.net` (pas de domaine personnel sur ce plan).
3. Vérifiez l'onglet **Limites** : 1 Go de disque, 256 Mo de mémoire, 1/4 de CPU. C'est suffisant
   pour 10 à 25 comptes.

## 4. Créer la base SQL

Dans le panneau alwaysdata → **Bases de données** → *Ajouter* :

* type **PostgreSQL** (recommandé) ou **MariaDB** ;
* nom : `mdl` ; utilisateur : `mdl` ; mot de passe généré → **recopiez-le** ;
* notez l'hôte affiché (souvent `localhost` en interne).

Décommentez la ligne correspondante dans `requirements.txt` (`psycopg[binary]` ou `PyMySQL`)
avant d'installer les dépendances.

## 5. Créer la boîte mail SMTP

Panneau → **Adresses e-mails** → créer `mdl@votredomaine.alwaysdata.net`.

* Serveur : `smtp.alwaysdata.com`
* Port : `465` (SSL) ou `587` (STARTTLS)
* Identifiant : **l'adresse e-mail complète**
* Mot de passe : celui de la boîte

La logique est inversée par rapport à un hébergeur classique : la boîte doit être marquée
« envoi autorisé ». Testez depuis Réglages → Envois (SMTP) → **Envoyer un e-mail de test**.

## 6. Monter le ZIP sur le serveur

En SFTP (FileZilla, WinSCP…), envoyez `MDL-Gestion-v1.0.0.zip` dans `~/apps/mdl/` puis décompressez-le,
ou bien :

```bash
cd ~ && mkdir -p apps && cd apps
git clone https://github.com/Thibstudio24/MDL-Gestion.git mdl
```

## 7. Créer l'application Python

```bash
cd ~/apps/mdl
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
```
Puis panneau → **Applications** → *Ajouter* : type **Python (uWSGI)**, dossier `~/apps/mdl`,
module `config.wsgi`, 1 processus. Dans « Variables d'environnement », collez les `MDL_*`
(ou laissez l'assistant écrire `config/instance.json`).

## 8. Lancer l'assistant d'installation

Ouvrez `https://votre-sous-domaine.alwaysdata.net/installation/` et suivez les quatre étapes :
prérequis techniques, identité de l'association, création du premier compte administrateur,
récapitulatif.

L'assistant disparaît dès qu'un compte existe : il redirige alors vers la page de connexion.
Il n'y a pas de commande de réinitialisation — pour le revoir, il faut supprimer tous les
comptes, ce qui n'est pas une opération courante.

## 9. Coller la ligne de cron

Panneau → **Tâches planifiées** → type *bash*. Une seule ligne suffit :

```
0 * * * * cd ~/apps/mdl && .venv/bin/python manage.py mdl_cron >> ~/cron.log 2>&1
```

`mdl_cron` enchaîne toutes les tâches horaires dans cet ordre : vidage de la file SMTP,
envoi des diffusions programmées, relance des invitations, clôture des campagnes expirées,
rappels de ménage, génération du bilan à échéance, alertes de quota et purges. Chaque étape
est indépendante : un échec n'interrompt pas les suivantes.

Ajoutez une sauvegarde quotidienne si vous le souhaitez :

```
45 3 * * * cd ~/apps/mdl && .venv/bin/python manage.py mdl_backup >> ~/backup.log 2>&1
```

En diagnostic, `manage.py mdl_health` affiche l'état de l'installation et
`manage.py mdl_purge tout --dry-run` compte ce que les purges supprimeraient.

## 10. Générer les clés VAPID et installer la PWA

Réglages → **PWA & push** → *Générer les clés*, puis redémarrez le service web.
Chaque membre ouvre l'application puis :

* **Android / PC** : bouton *Installer* (ou menu du navigateur → « Installer l'application »).
* **iPhone** (iOS ≥ 16.4) : Safari → Partager → **Sur l'écran d'accueil**, puis autoriser les
  notifications depuis l'icône installée.

Sans installation, les membres reçoivent un badge dans l'application et un e-mail.
