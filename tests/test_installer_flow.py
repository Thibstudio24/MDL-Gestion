"""Parcours complet de l'assistant d'installation, de l'étape 1 aux référentiels."""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import User
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
