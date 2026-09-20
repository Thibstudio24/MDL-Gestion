"""Liaison avec la centrale (côté instance) : enrôlement automatique, commandes."""
from __future__ import annotations

from django.core.management import call_command


class TestEnrolementAutomatique:
    def test_premier_ping_s_enrole_puis_plus(self, db, settings, monkeypatch):
        from core import services
        from core.models import Setting

        settings.HUB_URL = "https://centrale.test"
        appels = []

        def faux_hub(endpoint, payload, timeout=15):
            appels.append(endpoint)
            if endpoint == "enregistrement/":
                assert payload["install_id"] and payload["secret"]
            return {"latest_version": "1.0.0", "pending_actions": []}

        monkeypatch.setattr("core.services.hub_request", faux_hub)
        assert services.hub_ping()["ok"] is True
        assert appels == ["enregistrement/", "heartbeat/"]
        assert Setting.value("hub", "enrole") is True
        services.hub_ping()
        assert appels.count("enregistrement/") == 1  # une seule fois

    def test_echec_reseau_nebloque_pas_et_reessaiera(self, db, settings, monkeypatch):
        from core import services
        from core.models import Setting

        settings.HUB_URL = "https://centrale.test"

        def panne(endpoint, payload, timeout=15):
            raise OSError("réseau coupé")

        monkeypatch.setattr("core.services.hub_request", panne)
        assert services.hub_ping()["ok"] is False
        assert not Setting.value("hub", "enrole", False)

    def test_url_centrale_integree_par_defaut(self, db):
        from config import settings as module

        assert "mdl-centrale" in module.HUB_URL


class TestCommandesDeploiement:
    def test_mdl_admin_cree_le_super_admin(self, db):
        from accounts.models import User

        call_command("mdl_admin", "--email", "admin@asso.fr")
        user = User.objects.get(email="admin@asso.fr")
        assert user.role.is_administrator is True

    def test_mdl_hub_infos_affiche_le_couple(self, db):
        import io

        sortie = io.StringIO()
        call_command("mdl_hub_infos", stdout=sortie)
        texte = sortie.getvalue()
        assert "INSTALL_ID=" in texte and "SECRET=" in texte
