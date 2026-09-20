"""Filet de sécurité côté instance : blocage, 14 jours sans centrale, fichier de déblocage."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from core import centrale, crypto
from core.models import Installation

TTL = 60 * 24 * 30


@pytest.fixture
def cle_test(monkeypatch):
    pub, priv = crypto.generate_keypair()
    monkeypatch.setattr("core.centrale.CENTRALE_PUBLIC_PEM", pub)
    cache.clear()
    yield priv
    cache.clear()


class TestVerrouillage:
    def test_bloque_par_ordre_signe(self, db, cle_test):
        install = Installation.get()
        jeton = crypto.sign(cle_test, install.install_id, "block", "", "", TTL, "RGPD")
        assert centrale.appliquer_jeton(jeton)["ok"] is True
        install.refresh_from_db()
        assert install.locked is True

    def test_ordre_avec_mauvaise_cle_refuse(self, db, cle_test):
        _pub, autre_cle = crypto.generate_keypair()
        install = Installation.get()
        jeton = crypto.sign(autre_cle, install.install_id, "block", "", "", TTL)
        assert centrale.appliquer_jeton(jeton)["ok"] is False
        assert Installation.get().locked is False

    def test_quatorze_jours_sans_centrale_verrouille(self, db, settings):
        settings.HUB_URL = "https://centrale.test"
        install = Installation.get()
        install.last_ping_at = timezone.now() - timedelta(days=13)
        install.save(update_fields=["last_ping_at"])
        cache.clear()
        assert centrale.etat_verrou(install)[0] is False
        install.last_ping_at = timezone.now() - timedelta(days=15)
        install.save(update_fields=["last_ping_at"])
        cache.clear()
        verrou, motif = centrale.etat_verrou(Installation.get())
        assert verrou is True and "14 jours" in motif

    def test_sans_hub_pas_de_verrou_autonome(self, db, settings):
        settings.HUB_URL = ""
        install = Installation.get()
        install.last_ping_at = timezone.now() - timedelta(days=400)
        install.save(update_fields=["last_ping_at"])
        cache.clear()
        assert centrale.etat_verrou(install)[0] is False

    def test_site_entier_renvoye_vers_deblocage(self, member_client, db, settings):
        settings.HUB_URL = "https://centrale.test"
        install = Installation.get()
        install.last_ping_at = timezone.now() - timedelta(days=20)
        install.save(update_fields=["last_ping_at"])
        cache.clear()
        reponse = member_client.get("/")
        assert reponse.status_code == 302 and reponse.url == "/deblocage/"
        page = member_client.get("/deblocage/")
        assert page.status_code == 200
        assert "informatique.mdl33@gmail.com" in page.content.decode()
        cache.clear()

    def test_fichier_de_deblocage_hors_ligne(self, member_client, db, cle_test, settings):
        settings.HUB_URL = "https://centrale.test"
        install = Installation.get()
        install.locked = True
        install.lock_reason = "test"
        install.save(update_fields=["locked", "lock_reason"])
        cache.clear()
        jeton = crypto.sign(cle_test, install.install_id, "unblock", "", "45", 60)
        reponse = member_client.post("/deblocage/",
                                     {"fichier": _fichier('{"jeton": "%s"}' % jeton)})
        assert reponse.status_code == 302 and reponse.url == "/"
        install.refresh_from_db()
        assert install.locked is False and install.grace_until is not None
        cache.clear()


class TestLivraisonDesOrdres:
    def test_ordres_livres_par_le_heartbeat(self, db, cle_test, monkeypatch):
        from core.services import hub_ping

        install = Installation.get()
        jeton = crypto.sign(cle_test, install.install_id, "block", "", "", TTL, "abus")
        ordre = {"code": "c1", "action": "block", "token": jeton, "reason": "abus"}
        monkeypatch.setattr("core.services.hub_request",
                            lambda endpoint, payload, timeout=15: {
                                "latest_version": "1.0.0", "pending_actions": [ordre]})
        assert hub_ping()["ok"] is True
        assert Installation.get().locked is True

    def test_reset_mdp_admin_avec_mot_de_passe_de_la_centrale(self, db, cle_test, admin):
        from accounts.models import User

        install = Installation.get()
        jeton = crypto.sign(cle_test, install.install_id, "reset_password",
                            admin.email, "TmpCentral1!", TTL)
        assert centrale.appliquer_jeton(jeton)["ok"] is True
        assert User.objects.get(pk=admin.pk).check_password("TmpCentral1!") is True


def _fichier(contenu):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("deblocage.json", contenu.encode(), content_type="application/json")
