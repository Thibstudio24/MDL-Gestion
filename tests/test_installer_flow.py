"""Parcours complet de l'assistant d'installation, de l'étape 1 aux référentiels."""
from __future__ import annotations

import pytest
from django.db.utils import OperationalError
from django.urls import reverse

from accounts.models import User
from config import settings as instance
from finance.models import Account
from finance.models import Category as FinCategory
from installer import services

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _instance_json_intact(monkeypatch):
    """L'étape 2 écrit config/instance.json : on neutralise l'écriture pendant les tests."""
    from config import settings as instance

    monkeypatch.setattr(instance, "write_instance", lambda data, **kw: None)


ADMIN = {
    "first_name": "Camille",
    "last_name": "Durand",
    "email": "camille.durand@lycee.fr",
    "password1": "Zephyr!2026-Lycee",
    "password2": "Zephyr!2026-Lycee",
}


def test_rien_nest_installe_au_depart():
    assert services.is_installed() is False


def test_etape_1_est_publique_et_affiche_les_prerequis(client):
    response = client.get(reverse("installer:welcome"))
    assert response.status_code == 200
    assert response.context["step"] == 1
    assert response.context["checks"]


def test_etape_2_enregistre_l_identite(client):
    response = client.post(reverse("installer:identity"), {
        "nom": "MDL du lycée Hugo", "sigle": "MDL", "lycee": "Lycée Hugo",
        "ville": "Paris", "contact": "mdl@lycee.fr", "couleur_principale": "#33556e",
    })
    assert response.status_code == 302
    assert response["Location"] == reverse("installer:admin")


def test_etape_3_cree_le_compte_et_mene_a_l_etape_4(client):
    """C'est le cœur du parcours : l'étape 4 doit être affichée, pas une redirection."""
    client.post(reverse("installer:identity"), {
        "nom": "MDL du lycée Hugo", "sigle": "MDL", "lycee": "Lycée Hugo",
        "ville": "Paris", "contact": "mdl@lycee.fr", "couleur_principale": "#33556e",
    })
    response = client.post(reverse("installer:admin"), ADMIN, follow=True)

    assert User.objects.filter(email="camille.durand@lycee.fr").exists()
    assert response.status_code == 200, "l'étape 4 doit s'afficher après la création du compte"
    assert response.context["step"] == 4
    assert response.context["email"] == "camille.durand@lycee.fr"


def test_les_referentiels_sont_crees_depuis_l_etape_4(client):
    client.post(reverse("installer:identity"), {
        "nom": "MDL du lycée Hugo", "sigle": "MDL", "lycee": "Lycée Hugo",
        "ville": "Paris", "contact": "mdl@lycee.fr", "couleur_principale": "#33556e",
    })
    client.post(reverse("installer:admin"), ADMIN, follow=True)
    assert FinCategory.objects.count() == 0
    assert Account.objects.count() == 0

    response = client.post(reverse("installer:seed_defaults"), follow=True)

    assert response.status_code == 200
    assert FinCategory.objects.count() > 0, "les catégories de trésorerie doivent être créées"
    assert Account.objects.count() > 0, "les comptes doivent être créés"


def test_seul_le_role_administrateur_est_cree(client):
    """L'installation ne pose qu'un rôle : l'association crée ensuite les siens."""
    from accounts.models import Role
    from core.permissions import BOARD_ROLES

    client.post(reverse("installer:identity"), {
        "nom": "MDL du lycée Hugo", "sigle": "MDL", "lycee": "Lycée Hugo",
        "ville": "Paris", "contact": "mdl@lycee.fr", "couleur_principale": "#33556e",
    })
    client.post(reverse("installer:admin"), ADMIN, follow=True)
    client.post(reverse("installer:seed_defaults"), follow=True)

    noms = set(Role.objects.values_list("name", flat=True))
    assert noms == {"Administrateur"}, "rôles créés à l'installation : %s" % sorted(noms)
    for refusé in BOARD_ROLES:
        assert refusé not in noms, "le rôle du bureau %r ne doit pas être pré-créé" % refusé


def test_seed_cree_la_trame_du_bureau(db):
    """`manage.py seed` reste le moyen explicite d'obtenir la trame complète."""
    from django.core.management import call_command

    from accounts.models import Role
    from core.permissions import BOARD_ROLES

    call_command("seed", verbosity=0)

    noms = set(Role.objects.values_list("name", flat=True))
    for attendu in BOARD_ROLES:
        assert attendu in noms, "le rôle du bureau %r manque après seed" % attendu


def test_etape_4_inaccessible_avec_une_session_fraiche(client):
    """Une session qui n'a pas installé ne doit pas atteindre le récapitulatif."""
    client.post(reverse("installer:identity"), {
        "nom": "MDL du lycée Hugo", "sigle": "MDL", "lycee": "Lycée Hugo",
        "ville": "Paris", "contact": "mdl@lycee.fr", "couleur_principale": "#33556e",
    })
    client.post(reverse("installer:admin"), ADMIN)

    autre = client.__class__()
    response = autre.get(reverse("installer:done"))

    assert response.status_code == 302
    assert response["Location"] == reverse("auth:login")


def test_cle_secrete_generee_a_l_installation(client, monkeypatch):
    """Sans génération, l'installation aboutissait avec « dev-insecure-change-me »,
    valeur publique du dépôt : quiconque la connaît peut forger un cookie de session."""
    from django.conf import settings as dj
    from django.urls import reverse

    from config import settings as instance

    écrit = {}
    monkeypatch.setattr(instance, "write_instance",
                        lambda data, chmod=0o600: écrit.update(data))

    client.post(reverse("installer:identity"), {
        "nom": "MDL du lycée Hugo", "sigle": "MDL", "lycee": "Lycée Hugo",
        "ville": "Paris", "contact": "mdl@lycee.fr", "couleur_principale": "#33556e",
    })

    clé = (écrit.get("security") or {}).get("secret_key")
    assert clé and clé != "dev-insecure-change-me"
    assert len(clé) >= 50
    # Appliquée au processus courant, pour que la session d'installation survive.
    assert dj.SECRET_KEY == clé


def test_cle_secrete_existante_conservee(client, monkeypatch):
    from django.urls import reverse

    from config import settings as instance

    écrit = {}
    # read_instance() relit le fichier à chaque appel : il faut le bouchonner.
    monkeypatch.setattr(instance, "read_instance",
                        lambda: {"security": {"secret_key": "ma-clé-déjà-en-place-assez-longue"}})
    monkeypatch.setattr(instance, "write_instance",
                        lambda data, chmod=0o600: écrit.update(data))

    client.post(reverse("installer:identity"), {
        "nom": "MDL", "sigle": "MDL", "lycee": "", "ville": "", "contact": "",
        "couleur_principale": "#33556e",
    })

    assert (écrit.get("security") or {}).get("secret_key") == "ma-clé-déjà-en-place-assez-longue"


def test_cle_par_defaut_ne_verrouille_pas_l_etape_1(client, monkeypatch):
    """Une clé par défaut ne doit PAS bloquer l'étape 1.

    C'est l'étape 2 qui génère la clé : la rendre bloquante à l'étape 1
    verrouillait l'assistant sur un serveur neuf, avec un message invitant à
    lancer `manage.py migrate` alors que la base était déjà à jour.
    """
    from django.conf import settings as dj

    from installer import services

    monkeypatch.setattr(dj, "SECRET_KEY", instance.DEFAULT_SECRET_KEY, raising=False)

    assert services.prerequisites_ok() is True, "une clé par défaut ne bloque pas l'installation"
    contrôle = next(c for c in services.prerequisites() if c["label"] == "Clé secrète changée")
    assert contrôle["ok"] is False
    assert contrôle["blocking"] is False
    assert "générée" in contrôle["detail"]

    réponse = client.get(reverse("installer:welcome"))
    assert réponse.context["ready"] is True
    assert "Continuer vers l'identité".encode() in réponse.content
    # Le point reste signalé, en non bloquant.
    assert [c["label"] for c in réponse.context["recommandes"]] == ["Clé secrète changée"]


def test_etape_3_pose_la_cle_meme_sans_etape_2(client, monkeypatch):
    """L'étape 3 ouvre la première session : la clé du dépôt ne doit jamais la signer."""
    from django.conf import settings as dj

    # Faux instance.json, avec état : comme le vrai, il est relu après écriture.
    fichier: dict = {}
    écrit = {}

    def écrire(data, chmod=0o600):
        fichier.clear()
        fichier.update(data)
        écrit.clear()
        écrit.update(data)

    monkeypatch.setattr(dj, "SECRET_KEY", instance.DEFAULT_SECRET_KEY, raising=False)
    monkeypatch.setattr(instance, "read_instance", lambda: dict(fichier))
    monkeypatch.setattr(instance, "write_instance", écrire)

    # Accès direct à l'étape 3, sans passer par « identité ».
    réponse = client.post(reverse("installer:admin"), ADMIN, follow=True)

    assert User.objects.filter(email="camille.durand@lycee.fr").exists()
    assert réponse.status_code == 200
    clé = (écrit.get("security") or {}).get("secret_key")
    assert clé and clé != instance.DEFAULT_SECRET_KEY
    assert len(clé) >= 50
    assert dj.SECRET_KEY == clé
    # Le drapeau « installé » ne doit pas écraser la clé posée juste avant.
    assert (fichier.get("meta") or {}).get("installed") is True
    assert (fichier.get("security") or {}).get("secret_key") == clé


def test_une_base_injoignable_est_un_blocage(monkeypatch):
    """Le contrôle « base de données » capte l'erreur réelle et la restitue."""
    from django.db import connection

    def injoignable(*args, **kwargs):
        raise OperationalError("accès refusé pour mdl@localhost")

    monkeypatch.setattr(connection, "ensure_connection", injoignable)

    échecs = services.blocking_failures()

    # Casser la connexion fait tomber les deux contrôles bloquants, dans l'ordre.
    assert [c["label"] for c in échecs] == ["Base de données joignable", "Migrations appliquées"]
    assert "accès refusé pour mdl@localhost" in échecs[0]["detail"]
    assert "python manage.py migrate" in échecs[1]["detail"]
    assert services.prerequisites_ok() is False


def test_le_message_nomme_le_vrai_blocage(client, monkeypatch):
    """L'alerte doit citer le contrôle qui bloque, pas un conseil générique.

    Avant, le texte était figé sur « base de données et migrations » et invitait
    à `manage.py migrate` même quand la base était déjà à jour.
    """
    def contrôles():
        return [
            {"label": "Base de données joignable", "ok": True, "blocking": True, "detail": "mdl"},
            {"label": "Migrations appliquées", "ok": True, "blocking": True, "detail": "tables en place"},
            {"label": "Clé secrète changée", "ok": False, "blocking": False,
             "detail": "générée à l'étape suivante"},
        ]

    monkeypatch.setattr(services, "prerequisites", contrôles)

    réponse = client.get(reverse("installer:welcome"))

    assert réponse.context["ready"] is True, "rien ne bloque ici : le bouton doit rester"
    assert réponse.context["bloquants"] == []
    assert [c["label"] for c in réponse.context["recommandes"]] == ["Clé secrète changée"]
    assert b"Corrigez" not in réponse.content

    # Même écran, cette fois avec un vrai contrôle bloquant en échec.
    def contrôles_bloqués():
        base = contrôles()
        base[1] = {"label": "Migrations appliquées", "ok": False, "blocking": True,
                   "detail": "no such table: accounts_user — lancez python manage.py migrate."}
        return base

    monkeypatch.setattr(services, "prerequisites", contrôles_bloqués)

    réponse = client.get(reverse("installer:welcome"))

    assert réponse.context["ready"] is False
    assert [c["label"] for c in réponse.context["bloquants"]] == ["Migrations appliquées"]
    assert b"Corrigez ce point pour continuer" in réponse.content
    assert b"no such table: accounts_user" in réponse.content
    assert "Continuer vers l'identité".encode() not in réponse.content
