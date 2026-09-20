"""Centrale super-admin : heartbeat signé, raccordement, commandes de déploiement."""
from __future__ import annotations

import hashlib
import json

from django.core.management import call_command
from django.utils import timezone

from core.models import HubInstance


def _instance():
    return HubInstance.objects.create(label="MDL lycée test", install_id="abc123",
                                      secret="secret-partage", url="https://mdl2.test")


def _ping(client, instance, corps: dict, horodatage=None, signature=None):
    corps_json = json.dumps(corps, ensure_ascii=False, sort_keys=True)
    signature = signature or hashlib.sha256(
        ("%s|%s|%s" % (instance.install_id, instance.secret, corps_json)).encode()).hexdigest()
    return client.post("/api/heartbeat/", data=corps_json, content_type="application/json",
                       HTTP_X_INSTALL_ID=instance.install_id, HTTP_X_SIGNATURE=signature,
                       HTTP_X_TIMESTAMP=str(int((horodatage or timezone.now()).timestamp())))


class TestHeartbeat:
    def test_ping_signe_accepte(self, db, client):
        instance = _instance()
        reponse = _ping(client, instance, {"heartbeat": {"members": 12, "version": "1.0.0"}})
        assert reponse.status_code == 200 and reponse.json()["ok"] is True
        instance.refresh_from_db()
        assert instance.counters["members"] == 12 and instance.last_ping_at is not None
        assert instance.last_error == ""

    def test_signature_invalide_refusee(self, db, client):
        instance = _instance()
        reponse = _ping(client, instance, {"heartbeat": {}}, signature="0" * 64)
        assert reponse.status_code == 403
        instance.refresh_from_db()
        assert instance.last_error == "signature invalide"

    def test_instance_inconnue(self, db, client):
        reponse = client.post("/api/heartbeat/", data="{}", content_type="application/json",
                              HTTP_X_INSTALL_ID="inconnu", HTTP_X_SIGNATURE="x",
                              HTTP_X_TIMESTAMP="0")
        assert reponse.status_code == 404

    def test_horodatage_trop_ancien(self, db, client):
        from datetime import timedelta

        instance = _instance()
        reponse = _ping(client, instance, {"heartbeat": {}},
                        horodatage=timezone.now() - timedelta(hours=1))
        assert reponse.status_code == 403


class TestCentrale:
    def test_page_refusee_aux_membres(self, member_client):
        assert member_client.get("/centrale/").status_code == 403

    def test_page_ouverte_a_l_administrateur(self, admin_client):
        assert admin_client.get("/centrale/").status_code == 200

    def test_raccordement_d_une_instance(self, admin_client):
        reponse = admin_client.post("/centrale/ajouter/", {
            "label": "MDL lycée 2", "install_id": "xyz987", "secret": "s2",
            "url": "https://mdl2.example"})
        assert reponse.status_code == 302
        instance = HubInstance.objects.get(install_id="xyz987")
        assert instance.label == "MDL lycée 2"

    def test_debranchement(self, admin_client):
        instance = _instance()
        reponse = admin_client.post("/centrale/%d/debrancher/" % instance.pk)
        assert reponse.status_code == 302
        assert HubInstance.objects.count() == 0

    def test_entree_de_navigation_pour_les_admins_seulement(self, admin_client):
        assert "Centrale" in admin_client.get("/").content.decode()

    def test_aucune_entree_centrale_pour_un_membre(self, member_client):
        assert "Centrale" not in member_client.get("/menage/").content.decode()


class TestCommandesDeploiement:
    def test_mdl_admin_cree_le_super_admin(self, db):
        from accounts.models import User

        call_command("mdl_admin", "--email", "centrale@asso.fr")
        user = User.objects.get(email="centrale@asso.fr")
        assert user.role.is_administrator is True

    def test_mdl_hub_infos_affiche_le_couple(self, db):
        import io

        sortie = io.StringIO()
        call_command("mdl_hub_infos", stdout=sortie)
        texte = sortie.getvalue()
        assert "INSTALL_ID=" in texte and "SECRET=" in texte
