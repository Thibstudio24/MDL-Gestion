"""Contenu du mode d'emploi en ligne (/aide/) — source unique des pages HTML et de docs/."""
from __future__ import annotations

SECTIONS = [
    ("1", "Découvrir l'interface", """
La **barre latérale** liste les modules auxquels votre rôle donne accès : un module absent du menu
signifie simplement que votre rôle n'a aucun droit dessus. En haut : le filtre d'année scolaire, la
recherche, la cloche des notifications, la bascule clair/sombre et votre profil.

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
"""),
    ("6", "Monter le ZIP sur le serveur", """
En SFTP (FileZilla, WinSCP…), envoyez `MDL-Gestion-v1.0.0.zip` dans `~/apps/mdl/` puis décompressez-le,
ou bien :

```bash
cd ~ && mkdir -p apps && cd apps
git clone https://github.com/Thibstudio24/MDL-Gestion.git mdl
```
"""),
    ("7", "Créer l'application Python", """
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
"""),
    ("8", "Lancer l'assistant d'installation", """
Ouvrez `https://votre-sous-domaine.alwaysdata.net/installation/` et suivez les six étapes :
prérequis, base de données, comptes (administrateur + bureau), marque & textes, envois,
finalisation. L'assistant se verrouille ensuite (réponse 410) ; pour recommencer :
`python manage.py install --reset` en SSH.
"""),
    ("9", "Coller les lignes de cron", """
Panneau → **Tâches planifiées** → type *bash*, une ligne par tâche :

```
0 * * * * cd ~/apps/mdl && .venv/bin/python manage.py cron:run >> ~/cron.log 2>&1
15 7 * * * cd ~/apps/mdl && .venv/bin/python manage.py bilans --auto >> ~/bilan.log 2>&1
30 19 * * * cd ~/apps/mdl && .venv/bin/python manage.py menage:rappels >> ~/menage.log 2>&1
*/10 * * * * cd ~/apps/mdl && .venv/bin/python manage.py mail:drain >> ~/mail.log 2>&1
```
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
"""),
    ("12", "Créer un rôle et ses droits", """
Rôles & droits → **Créer un rôle**. Pour chaque module : *Aucun* (module absent du menu),
*Consulter*, *Modifier*. Les droits fins (supprimer un document, clôturer un mois…) se cochent
à part ; « Modifier » accorde automatiquement importer/exporter.

Un rôle ne peut jamais recevoir un niveau supérieur au vôtre, et « Rôles & droits » n'est
modifiable que par un Administrateur.
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

Boutons : *Générer maintenant*, *Choisir le mois d'arrêt*, *Télécharger le classeur*,
*Ouvrir l'aperçu*, *Exporter ce mois*.
"""),
    ("17", "Compter la caisse du coffre", """
Trésorerie → **Coffre** → *Comptage*. Le théorique est calculé à la date saisie ; vous indiquez le
montant réellement compté. Un écart non nul exige un motif et crée automatiquement une écriture
d'ajustement (sens « A »). L'écart apparaît au tableau de bord et dans l'onglet Coffre du bilan.
"""),
    ("18", "Lancer une campagne de disponibilités", """
Planning de la salle → **Créer une campagne** : libellé, période, nombre de semaines, plage
horaire et pas (30, 60, 90 ou 120 minutes), jours de la semaine, plage du soir réservée aux
internes, nombre minimal et maximal de gérants par créneau, date de clôture.

Chaque membre coche ses créneaux pour la **semaine 1** et la **semaine 2** (cases binaires).
"""),
    ("19", "Compléter et publier le planning PDF", """
Planning → *Couverture* : taux de réponse nominatif, relances individuelles ou groupées, puis
**Générer le planning**. Le bilan affiche les créneaux sans gérant (rouge) et surchargés (orange) ;
la publication reste possible malgré les trous — l'administrateur peut compléter à la main avec
un motif (marqué `*`).

Le PDF A4 paysage comporte quatre pages : grille semaine 1, grille semaine 2, calendrier daté des
semaines réelles, synthèse par membre.
"""),
    ("20", "Gérer les demandes d'échange", """
Un membre propose un échange depuis son planning ; les ayants droit « Modifier » sont notifiés.
En cas d'accord, l'administrateur applique l'échange : le planning est recalculé, une nouvelle
version est publiée et tout le monde est prévenu.
"""),
    ("21", "Créer un sondage de ménage et publier la répartition", """
Planning de ménage → **Créer une campagne** : jours (ex. mardi et vendredi midi), tâches avec
pénibilité et nombre de personnes, nombre maximal de refus autorisés.

Après les réponses, **Générer la répartition** équilibre l'historique, la charge et la pénibilité
(de façon déterministe), puis vous ajustez à la main avant de publier. Chacun coche « c'est fait »,
éventuellement avec une photo ; la validation supprime immédiatement la photo.
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
et les fichiers. La restauration exige une ré-authentification.

Réglages → **Mises à jour** : vérification depuis les Releases GitHub, application en un clic
(sauvegarde automatique, vérification SHA-256, retour arrière en cas d'échec). L'application ne
peut pas redémarrer le service web : cliquez sur *Redémarrer* dans le panneau alwaysdata.
"""),
    ("24", "FAQ", "voir la page FAQ"),
    ("25", "Glossaire", "voir la page Glossaire"),
    ("26", "Check-list de rentrée", """
- [ ] Compte alwaysdata créé, sous-domaine choisi, limites vérifiées
- [ ] Base PostgreSQL (ou MariaDB) créée, identifiants recopiés
- [ ] Boîte `mdl@…` créée et testée (envoi autorisé)
- [ ] Code monté dans `~/apps/mdl`, environnement virtuel installé, migrations jouées
- [ ] Application Python (uWSGI) créée et démarrée
- [ ] Assistant d'installation terminé (administrateur + bureau invités)
- [ ] 4 lignes de cron collées
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
Ce n'est plus possible par vous-même. Demandez à l'administrateur de **rouvrir la campagne** :
toute modification est datée et journalisée. Pour un créneau déjà publié, utilisez la
**demande d'échange**."""),
    ("Pourquoi une écriture est bloquée ?", """
Le mois est clôturé. Le message nomme le mois concerné. Seul un administrateur peut rouvrir la
période, avec un motif et une trace dans le journal d'audit."""),
    ("Le bilan n'est pas arrivé", """
Vérifiez que la ligne de cron `bilans --auto` existe, que l'échéance est bien atteinte
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
2. Coller quatre lignes de tâches planifiées (cron) dans le panneau alwaysdata : elles
   envoient les e-mails, génèrent le bilan mensuel et rappellent les ménages.

Nous créons nous-mêmes la base de données et la boîte e-mail d'envoi dans le panneau, et nous
nous chargeons de l'installation. Aucune donnée ne sort de cet hébergement.

Merci d'avance,
Le bureau de la MDL
"""
