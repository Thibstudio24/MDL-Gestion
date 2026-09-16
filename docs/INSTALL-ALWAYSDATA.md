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

Ouvrez `https://votre-sous-domaine.alwaysdata.net/installation/` et suivez les six étapes :
prérequis, base de données, comptes (administrateur + bureau), marque & textes, envois,
finalisation. L'assistant se verrouille ensuite (réponse 410) ; pour recommencer :
`python manage.py install --reset` en SSH.

## 9. Coller les lignes de cron

Panneau → **Tâches planifiées** → type *bash*, une ligne par tâche :

```
0 * * * * cd ~/apps/mdl && .venv/bin/python manage.py cron:run >> ~/cron.log 2>&1
15 7 * * * cd ~/apps/mdl && .venv/bin/python manage.py bilans --auto >> ~/bilan.log 2>&1
30 19 * * * cd ~/apps/mdl && .venv/bin/python manage.py menage:rappels >> ~/menage.log 2>&1
*/10 * * * * cd ~/apps/mdl && .venv/bin/python manage.py mail:drain >> ~/mail.log 2>&1
```

## 10. Générer les clés VAPID et installer la PWA

Réglages → **PWA & push** → *Générer les clés*, puis redémarrez le service web.
Chaque membre ouvre l'application puis :

* **Android / PC** : bouton *Installer* (ou menu du navigateur → « Installer l'application »).
* **iPhone** (iOS ≥ 16.4) : Safari → Partager → **Sur l'écran d'accueil**, puis autoriser les
  notifications depuis l'icône installée.

Sans installation, les membres reçoivent un badge dans l'application et un e-mail.
