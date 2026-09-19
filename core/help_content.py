"""Contenu du mode d'emploi en ligne (/aide/) — source unique des pages HTML et de docs/."""
from __future__ import annotations

SECTIONS = [
    ("1", "Découvrir l'interface", """
La **barre latérale** liste les modules auxquels votre rôle donne accès : un module absent du menu
signifie simplement que votre rôle n'a aucun droit dessus. En haut : le filtre d'année scolaire, la
recherche, la cloche des notifications, la bascule clair/sombre et votre profil.
La cloche déroule les notifications non lues : un clic marque comme lu et ouvre la page
concernée ; « Tout marquer lu » solde le compteur. Le petit chiffre à côté de
« Messages » compte, lui, les courriels non lus de la messagerie.

* « Réduire la sidebar » (icône en bas de la barre) passe en pleine largeur.
* Densité **confort** ou **compacte** : Réglages → Apparence.
* Six palettes × clair/sombre ; l'administration peut imposer un rendu à toute l'association.
* Tout écran est imprimable : bouton **Imprimer** ou `Ctrl + P`.
"""),
    ("2", "Installer chez soi pour essayer (3 minutes, SQLite)", """
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py runserver 0.0.0.0:8000
```
Ouvrez <http://127.0.0.1:8000/installation/> : l'assistant crée le compte administrateur, les
catégories, les rôles du bureau et les textes légaux. La base est un simple fichier `db.sqlite3`.
"""),
    ("3", "Créer le compte alwaysdata", """
1. Créez un compte sur **alwaysdata** (plan Free).
2. Choisissez un sous-domaine : `mdl-lycee.alwaysdata.net` (pas de domaine personnel sur ce plan).
3. Vérifiez l'onglet **Limites** : 1 Go de disque, 256 Mo de mémoire, 1/4 de CPU. C'est suffisant
   pour 10 à 25 comptes.
"""),
    ("4", "Créer la base SQL", """
Dans le panneau alwaysdata → **Bases de données** → *Ajouter* :

* type **PostgreSQL** (recommandé) ou **MariaDB** ;
* nom : `mdl` ; utilisateur : `mdl` ; mot de passe généré → **recopiez-le** ;
* notez l'hôte affiché (souvent `localhost` en interne).

Décommentez la ligne correspondante dans `requirements.txt` (`psycopg[binary]` ou `PyMySQL`)
avant d'installer les dépendances.
"""),
    ("5", "Créer la boîte mail SMTP", """
Panneau → **Adresses e-mails** → créer `mdl@votredomaine.alwaysdata.net`.

* Serveur : `smtp.alwaysdata.com`
* Port : `465` (SSL) ou `587` (STARTTLS)
* Identifiant : **l'adresse e-mail complète**
* Mot de passe : celui de la boîte

La logique est inversée par rapport à un hébergeur classique : la boîte doit être marquée
« envoi autorisé ». Testez depuis Réglages → Envois (SMTP) → **Envoyer un e-mail de test**.

Dans l'application, l'enregistrement du formulaire écrit la section `mail` de
`config/instance.json` (mot de passe compris, fichier en droits 600) et applique les
réglages immédiatement, sans redémarrage. SSL = port 465, STARTTLS = port 587 ; au
moment de l'envoi, le mode est déduit du port, donc un vieux réglage incohérent ne
bloque plus rien.

Une pompe de fond vide la file automatiquement toutes les ~15 secondes, sans cron
ni bouton (désactivable par `mail.pump = false` ou `MDL_MAIL_PUMP=0`) ; le cron
`mdl_cron` et le bouton « Vider la file maintenant » restent disponibles en
secours. En cas d'échec, l'erreur exacte du serveur s'affiche dans la file, et le
courriel retente sa chance aux passages suivants. Les courriels unitaires
(invitation, mot de passe, alerte) tentent en plus un envoi immédiat.

Les liens contenus dans les courriels (invitation, réinitialisation, bilan,
messagerie…) sont absolus : `https://votre-site/page`. L'adresse de base est
détectée automatiquement à la première visite du site et mémorisée dans
`config/instance.json` (`app.base_url`) ; on peut aussi la poser à la main
(`app.base_url` ou `MDL_BASE_URL`), elle est alors prioritaire, ou la laisser
se déduire du premier hôte autorisé (`app.allowed_hosts`).
"""),
    ("6", "Monter le ZIP sur le serveur", """
Le code va dans `~/www/`. **N'utilisez pas `~/admin/`** : ce répertoire appartient à
alwaysdata (configurations en lecture seule, journaux, temporaires, sauvegardes) et n'est
pas destiné à recevoir vos fichiers.

En SFTP (FileZilla, WinSCP…), envoyez `MDL-Gestion-v1.0.0.zip` dans `~/www/` puis
décompressez-le, ou bien en SSH :

```bash
cd ~/www
git clone -b arena/01a0a9db-mdl-gestion https://github.com/Thibstudio24/MDL-Gestion.git mdl
cd mdl
```

Le ZIP contient un dossier `mdl/` : le projet se retrouve dans `~/www/mdl/`.
"""),
    ("7", "Créer l'application Python", """
Chez alwaysdata, on lance toujours `python`, jamais `python3`. La version se choisit dans
le panneau **Environnement → Python** (3.11 ou plus récent convient) ; `PYTHON_VERSION`
permet d'en forcer une autre ponctuellement.

```bash
cd ~/www/mdl
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
```
Puis panneau → **Web → Sites** → *Ajouter* : type **Python WSGI**, et

* **chemin de l'application** : `/www/mdl/config/wsgi.py` — c'est un chemin de fichier,
  pas un nom de module ;
* **répertoire de travail** : `/www/mdl/` ;
* **répertoire du virtualenv** : `/www/mdl/.venv/` ;
* **version de Python** : 3.11 ou plus.

Dans « Variables d'environnement », collez les `MDL_*`, ou laissez l'assistant écrire
`config/instance.json`. Les erreurs uWSGI s'inscrivent dans
`~/admin/logs/uwsgi/<id>.log`, l'identifiant du site étant affiché dans **Web → Sites**.
"""),
    ("8", "Lancer l'assistant d'installation", """
Ouvrez `https://votre-sous-domaine.alwaysdata.net/installation/` et suivez les quatre étapes :
prérequis techniques, identité de l'association, création du premier compte administrateur,
récapitulatif.

L'étape 1 liste huit contrôles. Seuls deux sont bloquants : **base de données joignable** et
**migrations appliquées**. Quand l'un des deux échoue, l'alerte le nomme et donne l'erreur
telle quelle — elle ne propose plus `python manage.py migrate` à l'aveugle. Les autres
contrôles (clé secrète, `DEBUG`, hôtes autorisés, dossiers accessibles en écriture, fuseau
horaire) sont signalés sans empêcher d'avancer.

La **clé secrète** est générée automatiquement à l'étape 2 : 50 caractères aléatoires écrits
dans `config/instance.json` (section `security.secret_key`, droits 600). Vous pouvez la poser
vous-même avant, via la variable `MDL_SECRET_KEY` ou ce même fichier ; une clé déjà en place
n'est jamais écrasée. Si vous servez l'application avec plusieurs processus, relancez le site
après l'installation pour que tous lisent la clé du fichier. Changer la clé invalide les
sessions ouvertes.

L'assistant disparaît dès qu'un compte existe : il redirige alors vers la page de connexion.
Il n'y a pas de commande de réinitialisation — pour le revoir, il faut supprimer tous les
comptes, ce qui n'est pas une opération courante.
"""),
    ("9", "Coller la ligne de cron", """
Panneau → **Tâches planifiées** → type *bash*. Une seule ligne suffit :

```
0 * * * * cd ~/www/mdl && .venv/bin/python manage.py mdl_cron >> ~/cron.log 2>&1
```

`mdl_cron` enchaîne toutes les tâches horaires dans cet ordre : vidage de la file SMTP,
envoi des diffusions programmées, relance des invitations, clôture des campagnes expirées,
rappels de ménage, génération du bilan à échéance, alertes de quota et purges. Chaque étape
est indépendante : un échec n'interrompt pas les suivantes.

Ajoutez une sauvegarde quotidienne si vous le souhaitez :

```
45 3 * * * cd ~/www/mdl && .venv/bin/python manage.py mdl_backup >> ~/backup.log 2>&1
```

En diagnostic, `manage.py mdl_health` affiche l'état de l'installation et
`manage.py mdl_purge tout --dry-run` compte ce que les purges supprimeraient.
"""),
    ("10", "Générer les clés VAPID et installer la PWA", """
Réglages → **PWA & push** → *Générer les clés*, puis redémarrez le service web.
Chaque membre ouvre l'application puis :

* **Android / PC** : bouton *Installer* (ou menu du navigateur → « Installer l'application »).
* **iPhone** (iOS ≥ 16.4) : Safari → Partager → **Sur l'écran d'accueil**, puis autoriser les
  notifications depuis l'icône installée.

Sans installation, les membres reçoivent un badge dans l'application et un e-mail.
"""),
    ("11", "Inviter les membres", """
Membres → **Inviter un membre** : prénom, nom, e-mail, rôle, fonction, message, durée de validité
(1, 3, 7 ou 30 jours). Le compte est créé « en attente » et ne peut pas se connecter avant
d'avoir choisi son mot de passe.

Le lien **et** un code court à 6 caractères sont affichés : le code sert aux membres dont l'adresse
e-mail n'est pas fiable. Relance automatique la veille de l'expiration.

Seul un administrateur voit et peut attribuer le rôle Administrateur (invitation ou
changement de rôle) ; les autres rôles n'ont même pas l'option à l'écran. Sur la fiche
d'un membre, un administrateur peut **anonymiser** (l'historique reste lisible sous un
nom pseudonymisé) ou **supprimer définitivement** le compte, sans laisser de traces
(confirmation tapée « SUPPRIMER », irréversible).
"""),
    ("12", "Créer un rôle et ses droits", """
Rôles & droits → **Créer un rôle**. Pour chaque module : *Aucun* (module absent du menu),
*Consulter*, *Modifier*. Les droits fins (supprimer un document, clôturer un mois…) se cochent
à part ; « Modifier » accorde automatiquement importer/exporter.

Un rôle ne peut jamais recevoir un niveau supérieur au vôtre, et « Rôles & droits » n'est
modifiable que par un Administrateur.

L'installation ne crée qu'un seul rôle, **Administrateur** : c'est à vous de composer ceux de
votre bureau. Un rôle peut **imposer l'A2F** à ses membres, avec un délai d'activation ;
passé ce délai, la connexion reste sur l'écran d'activation.
"""),
    ("13", "Saisir une écriture de trésorerie", """
Trésorerie → **Nouvelle écriture** : date, libellé, catégorie, montant, sens (Recette / Dépense /
Transfert / Ajustement), compte, mode de règlement, tiers, référence, note, justificatif.

Un **transfert** Banque → Coffre ne change pas le solde global : il déplace l'argent.
Le solde du coffre est toujours **calculé**, jamais saisi.
"""),
    ("14", "Importer un relevé bancaire", """
Trésorerie → **Importer** : déposez le fichier (xlsx ou csv), l'écran de mapping propose une
correspondance colonne par colonne, puis la prévisualisation signale les dates invalides, les
catégories inconnues et les doublons (même date + libellé + montant). L'import est enregistré
avec un rapport et peut être **annulé** en bloc.
"""),
    ("15", "Clore un mois", """
Trésorerie → **Périodes** → *Clôturer*. Le verrou est dur : plus personne ne modifie le mois,
pas même un administrateur. La réouverture demande une ré-authentification, un motif, et écrit
une ligne d'audit en rouge.
"""),
    ("16", "Générer et retrouver le bilan Excel", """
Un **seul classeur par année scolaire**, régénéré à chaque échéance :
onglet *Synthèse annuelle*, un onglet par mois, *Coffre & comptages*, *Écritures*.
Il est rangé dans Documents → **Bilans** et notifié aux ayants droit.

Les destinataires ne se choisissent pas : le bilan va aux seuls membres qui peuvent
**consulter la trésorerie**, et ce même droit ouvre la catégorie « Bilans ». Retirer le droit
trésorerie retire aussitôt l'accès au classeur.

Boutons : *Générer maintenant*, *Choisir le mois d'arrêt*, *Télécharger le classeur*,
*Ouvrir l'aperçu*, *Exporter ce mois*.
"""),
    ("17", "Compter la caisse du coffre", """
Trésorerie → **Coffre** → *Comptage*. Le théorique est calculé à la date saisie ; vous indiquez le
montant réellement compté. Un écart non nul exige un motif et crée automatiquement une écriture
d'ajustement (sens « A »). L'écart apparaît au tableau de bord et dans l'onglet Coffre du bilan.
"""),
    ("18", "Lancer une campagne de disponibilités", """
Planning de la salle → **Créer une campagne** : libellé, description, période (trimestre,
semestre ou année entière), date d'ouverture, date de clôture des réponses et durée d'un
créneau en minutes.

Six créneaux types sont créés automatiquement (permanences du lundi au vendredi de 12 h à 13 h
et ouverture du foyer le vendredi de 16 h à 18 h, deux gérants par créneau). Vous pouvez en
ajouter d'autres — jour, horaire, intitulé, nombre de gérants — ou supprimer ceux qui ne
servent pas.

Chaque membre répond **Disponible**, **Si besoin** ou **Indisponible** sur chaque créneau, avec
une note libre s'il le faut (« seulement jusqu'à 12 h 30 »). Une seule réponse par membre et
par créneau ; elle reste modifiable tant que la campagne est ouverte.
"""),
    ("19", "Compléter et publier le planning PDF", """
Planning → *Couverture* : taux de réponse nominatif, relances individuelles ou groupées, puis
**Générer le planning (PDF)**. La page de couverture liste les créneaux sans gérant ; la
publication reste possible malgré les trous — l'administrateur complète à la main en ajoutant
un créneau ou en relançant.

Le PDF A4 paysage comporte deux pages :

1. **Grille des créneaux** — jour, horaire, intitulé, gérants requis, membres disponibles,
   membres « si besoin », état. Les créneaux sans gérant sont surlignés en orange : c'est la
   page à imprimer et à afficher sur la porte du foyer.
2. **Synthèse par membre** — disponibles / si besoin / indisponibles et créneaux concernés,
   pour relancer nominativement les absents.

Le même export existe en CSV (bouton **CSV** sur la grille) pour retravailler les données dans
un tableur.
"""),
    ("20", "Relancer et clôturer une campagne", """
Planning → **Relancer** envoie une notification à tous les membres actifs qui n'ont pas encore
répondu ; la date du dernier rappel est conservée sur la campagne pour éviter le harcèlement.

**Clôturer** fige les réponses : plus personne ne peut les modifier. Les campagnes dont la date
de clôture est dépassée sont fermées automatiquement par le traitement horaire (`mdl_cron`).

Pour corriger un créneau déjà publié, l'administrateur ajoute un créneau ou modifie la
capacité, puis régénère le PDF : la grille imprimée reflète toujours l'état courant.
"""),
    ("21", "Préparer le ménage : tâches, refus, jours et réarrangement", """
**Créer la campagne** : Planning de ménage → **Campagnes** → « Nouvelle campagne » (semaine type,
dates, date limite). Les cinq tâches types sont pré-créées ; sur la page de la campagne, ajoutez
vos propres tâches (libellé, jour, lieu) ou retirez-en avant publication.

**Les membres** répondent à la campagne (J'accepte / Je ne peux pas) puis déclarent, carte
« Mes préférences », leurs **jours de présence** et les **tâches qu'ils ne peuvent pas faire**.
« Publier et attribuer » confie chaque tâche au membre le moins chargé : une tâche refusée n'est
jamais donnée à qui l'a refusée (s'il reste des volontaires) et les jours déclarés sont privilégiés.

**Réarranger** : sur la page de la campagne, chaque tâche attribuée propose un sélecteur de membre
et de jour — « Appliquer » change le titulaire sans toucher au reste. Chacun déclare sa tâche
faite avec une photo ; la validation supprime immédiatement la photo.
"""),
    ("22", "Envoyer un message et relire les accusés", """
Messages → **Nouvelle diffusion** : objet, corps (gras, italique, listes, titres, liens),
destinataires (toute l'association, un rôle, une sélection, avec exclusions), canal
(dans l'app, par e-mail, les deux), envoi immédiat ou différé, copie vers un dossier Documents.

L'onglet de suivi liste nominativement qui a lu, avec le compteur « 8/12 lus » et le bouton
**Relancer les non-lecteurs**.
"""),
    ("23", "Sauvegarder, restaurer, mettre à jour", """
Réglages → **Sauvegarde** : le ZIP contient le dump JSON, la configuration (mots de passe masqués)
et les fichiers. La restauration exige une ré-authentification. Chaque archive peut être
supprimée du serveur ; téléchargez-la d'abord, le serveur ne doit pas être votre seul exemplaire.

Réglages → **Journal d'audit** : le journal ne se modifie jamais ligne à ligne. L'administrateur
peut le vider entièrement ; le vidage lui-même y est tracé.

Réglages → **Sauvegarde**, « Zone dangereuse » : un administrateur ré-authentifié peut
réinitialiser complètement le site (comptes, documents, messages, fichiers, sauvegardes)
et rendre la main à l'assistant d'installation. Confirmation tapée « REINITIALISER »,
irréversible.

Réglages → **Mises à jour** : vérification depuis les Releases GitHub, application en un clic
(sauvegarde automatique, vérification SHA-256, retour arrière en cas d'échec). L'application ne
peut pas redémarrer le service web : cliquez sur *Redémarrer* dans le panneau alwaysdata.
"""),
    ("24", "Choisir où sont rangés les fichiers", """
Par défaut, documents, photos de ménage et pièces jointes sont rangés sur le disque du serveur
(1 Go sur l'offre gratuite alwaysdata). Réglages → **Stockage** — ou la dernière étape de
l'installation — permet de passer chez un **fournisseur tiers gratuit et sans carte bancaire**,
compatible S3 :

* **Backblaze B2** : 10 Go offerts. Créez un compte, un bucket **privé**, notez l'endpoint
  (`s3.eu-west-005.backblazeb2.com`, région `eu-west-005`) et générez une clé d'application.
* **Cloudflare R2** : 10 Go offerts, endpoint de type `<compte>.r2.cloudflarestorage.com`.
* **Supabase** : 1 Go offert, section Storage → « S3 Connection ».

Collez endpoint, région, bucket et les deux clés, enregistrez, puis lancez le **test de
connexion** : il dépose, relit et supprime un petit fichier dans le bucket. Les fichiers déjà
présents sur le serveur restent consultables ; les nouveaux partent chez le fournisseur, et un
retour au disque du serveur se fait en un choix. La sauvegarde du site couvre la base de
données : sauvegardez le bucket chez le fournisseur (B2 propose un miroir gratuit).
"""),
    ("25", "FAQ", "voir la page FAQ"),
    ("26", "Glossaire", "voir la page Glossaire"),
    ("27", "Check-list de rentrée", """
- [ ] Compte alwaysdata créé, sous-domaine choisi, limites vérifiées
- [ ] Base PostgreSQL (ou MariaDB) créée, identifiants recopiés
- [ ] Boîte `mdl@…` créée et testée (envoi autorisé)
- [ ] Code monté dans `~/www/mdl`, environnement virtuel installé, migrations jouées
- [ ] Site **Python WSGI** créé et démarré
- [ ] Assistant d'installation terminé (administrateur + bureau invités)
- [ ] Ligne de cron `mdl_cron` collée
- [ ] Clés VAPID générées, PWA installée sur au moins un téléphone
- [ ] Année scolaire ouverte, catégories de trésorerie vérifiées
- [ ] Soldes d'ouverture saisis (banque + coffre)
- [ ] Campagne de disponibilités lancée, planning publié
- [ ] Sondage de ménage lancé et répartition publiée
- [ ] Première sauvegarde téléchargée hors du serveur
"""),
]

FAQ = [
    ("J'ai oublié mon mot de passe", """
Écran de connexion → **Mot de passe oublié ?** : un lien valable 3 heures part sur votre adresse.
Sans accès à cette boîte, demandez à un administrateur : Membres → votre fiche → *Réinitialiser le
mot de passe* (le nouveau mot de passe ne s'affiche jamais à l'écran, il part par e-mail)."""),
    ("Le membre n'a pas reçu son invitation", """
Vérifiez Réglages → Envois (SMTP) : si le canal est « seulement dans l'app », aucun e-mail ne part.
La fiche du membre affiche alors le lien et le **code court** à transmettre à la main. Pensez aussi
au dossier indésirables."""),
    ("Le lien a expiré", """
Un écran explicite le dit. Un ayant droit peut **Renvoyer** l'invitation depuis la fiche du membre :
un nouveau lien et un nouveau code sont générés, l'ancien est neutralisé."""),
    ("Je veux consulter un document sans e-mail", """
Tout se passe dans l'application : Documents → catégorie → aperçu (PDF et images) ou
téléchargement. Le bouton **Garder hors ligne** conserve le fichier dans l'appareil pour une
lecture ultérieure sans réseau."""),
    ("« Compte verrouillé »", """
Cinq tentatives échouées verrouillent le compte 15 minutes. Un administrateur peut débloquer
immédiatement : Membres → fiche → *Débloquer*."""),
    ("Pourquoi la plage du soir est grisée ?", """
La plage du soir (par défaut 18 h → 21 h) est réservée aux **internes** : votre fiche indique
« externe ». Un administrateur peut modifier la mention interne/externe."""),
    ("Comment changer mes disponibilités après la clôture ?", """
Ce n'est plus possible par vous-même : la campagne est clôturée. Prévenez l'administrateur, qui
notera l'absence et complétera le créneau à la main avant de régénérer le planning PDF. Toute
intervention de sa part est datée et journalisée."""),
    ("Pourquoi une écriture est bloquée ?", """
Le mois est clôturé. Le message nomme le mois concerné. Seul un administrateur peut rouvrir la
période, avec un motif et une trace dans le journal d'audit."""),
    ("Le bilan n'est pas arrivé", """
Vérifiez que la ligne de cron `mdl_cron` existe, que l'échéance est bien atteinte
(Réglages → Bilan) et que le SMTP fonctionne. Le bouton *Générer maintenant* déclenche la
génération immédiatement."""),
    ("Mon iPhone ne reçoit pas les notifications", """
Il faut iOS ≥ 16.4 **et** l'application ajoutée à l'écran d'accueil via Safari → Partager →
« Sur l'écran d'accueil ». Les notifications doivent ensuite être autorisées depuis l'icône
installée. Sinon, vous gardez le badge dans l'application et l'e-mail."""),
]

GLOSSARY = [
    ("A2F", "Authentification à deux facteurs : un code à 6 chiffres changeant toutes les 30 secondes (application d'authentification), plus 10 codes de récupération."),
    ("Année scolaire", "Période de référence de toutes les données (écritures, campagnes, bilan). Une année clôturée devient lecture seule."),
    ("Bilan", "Classeur Excel unique par année scolaire : synthèse, un onglet par mois, coffre et comptages, grand livre."),
    ("Campagne", "Consultation des membres : disponibilités de la salle ou sondage de ménage, avec date de clôture."),
    ("Catégorie", "Regroupement de documents (Comptes rendus, Fiches clubs, Documents administratifs, Bilans) ou d'écritures (Fournitures, Cotisations…)."),
    ("Clôture mensuelle", "Verrou dur sur un mois de trésorerie : plus aucune écriture ne peut être modifiée sans réouverture tracée."),
    ("Coffre", "Compte dont le solde est toujours calculé ; les mouvements sont des transferts et les écarts sont justifiés par un comptage."),
    ("Droit fin", "Autorisation booléenne précise (supprimer un document, clôturer un mois, programmer un envoi…), indépendante du niveau du module."),
    ("Intervention technique", "Action bornée demandée par l'éditeur (réinitialiser un mot de passe, couper l'A2F, renvoyer une invitation) : annoncée, révocable, journalisée."),
    ("Mois d'arrêt", "Dernier mois inclus dans le bilan généré."),
    ("Preuve", "Photo jointe à une tâche de ménage terminée ; supprimée dès la validation."),
    ("Q1 / Q2", "Semaine type 1 et semaine type 2 du planning de la salle, qui alternent de semaine en semaine."),
    ("Quota", "Espace disque alloué à l'association, avec alertes à 80 % et 95 %."),
    ("Rôle", "Ensemble de droits (module × niveau + droits fins). Un seul rôle par membre."),
]

CHECKLIST_EMAIL = """
Objet : Hébergement free alwaysdata de notre association

Bonjour,

Nous mettons en place la gestion de la Maison des Lycéens (trésorerie, documents, plannings,
messagerie interne). L'application est libre (AGPL-3.0) et s'installe sur un hébergement
gratuit alwaysdata ; nous avons besoin de votre validation pour deux points techniques.

1. Création du compte alwaysdata (plan Free) : 1 Go de disque, 256 Mo de mémoire, un
   sous-domaine du type mdl-<lycee>.alwaysdata.net. Aucun nom de domaine personnel n'est
   nécessaire ni possible sur ce plan.
2. Coller une ligne de tâche planifiée (cron) dans le panneau alwaysdata : elle envoie les
   e-mails, génère le bilan mensuel, rappelle les ménages et lance les purges.

Nous créons nous-mêmes la base de données et la boîte e-mail d'envoi dans le panneau, et nous
nous chargeons de l'installation. Aucune donnée ne sort de cet hébergement.

Merci d'avance,
Le bureau de la MDL
"""
