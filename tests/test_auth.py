"""Connexion, verrouillage, double facteur, ré-authentification."""
from __future__ import annotations

from accounts import twofa
from accounts.models import User


class TestConnexion:
    def test_connexion_valide(self, client, member):
        response = client.post("/connexion/", {"email": member.email, "password": "MotDePasse-Solide-2026"})
        assert response.status_code == 302
        assert User.objects.get(pk=member.pk).last_login is not None

    def test_mot_de_passe_incorrect_refuse(self, client, member):
        response = client.post("/connexion/", {"email": member.email, "password": "mauvais"})
        assert response.status_code == 200
        assert not response.wsgi_request.user.is_authenticated

    def test_compte_inactif_refuse(self, client, member):
        member.status = "inactive"
        member.save(update_fields=["status"])
        response = client.post("/connexion/", {"email": member.email, "password": "MotDePasse-Solide-2026"})
        assert not response.wsgi_request.user.is_authenticated

    def test_verrouillage_apres_trop_dechecs(self, client, member):
        from accounts.services import authenticate
        from core.models import Setting

        limit = int(Setting.value("securite", "login_max_attempts", 5))
        for _ in range(limit + 1):
            authenticate(None, member.email, "mauvais")
        member.refresh_from_db()
        assert member.locked_until is not None

    def test_compte_verrouille_refuse_le_bon_mot_de_passe(self, client, member):
        from django.utils import timezone

        member.locked_until = timezone.now() + timezone.timedelta(minutes=15)
        member.save(update_fields=["locked_until"])
        response = client.post("/connexion/", {"email": member.email, "password": "MotDePasse-Solide-2026"})
        assert not response.wsgi_request.user.is_authenticated

    def test_assistant_propose_quand_aucun_compte_nexiste(self, client, db):
        response = client.get("/connexion/")
        assert response.status_code == 302
        assert response["Location"] == "/installation/"

    def test_page_de_connexion_affichee_des_quun_compte_existe(self, client, member):
        assert client.get("/connexion/").status_code == 200


class TestDoubleFacteur:
    def test_generation_et_verification_dun_code(self, member):
        import pyotp

        secret = twofa.generate_secret()
        member.totp_secret = secret
        member.totp_enabled = True
        member.save(update_fields=["totp_secret", "totp_enabled"])
        assert twofa.verify(secret, pyotp.TOTP(secret).now(), member) is True

    def test_un_code_faux_est_refuse(self, member):
        secret = twofa.generate_secret()
        assert twofa.verify(secret, "000000", member) is False

    def test_codes_de_secours_utilisables_une_fois(self, member):
        codes = twofa.generate_recovery_codes(member)
        assert len(codes) >= 5
        assert twofa.use_recovery_code(member, codes[0]) is True
        assert twofa.use_recovery_code(member, codes[0]) is False

    def test_qr_code_en_svg(self, member):
        secret = twofa.generate_secret()
        uri = twofa.provisioning_uri(secret, member.email)
        assert uri.startswith("otpauth://totp/")
        svg = twofa.qr_svg(uri)
        assert "<svg" in svg and "</svg>" in svg


class TestSessionEtReauth:
    def test_deconnexion(self, member_client):
        response = member_client.post("/deconnexion/", follow=True)
        assert response.status_code == 200

    def test_reauth_exigee_pour_une_action_sensible(self, admin_client, member):
        response = admin_client.get("/membres/%d/anonymiser/" % member.pk)
        assert response.status_code in (302, 405)

    def test_les_pages_privees_redirigent_vers_la_connexion(self, client, db):
        response = client.get("/membres/")
        assert response.status_code == 302
        assert "/connexion/" in response["Location"]

    def test_suivi_de_session_apres_une_vraie_connexion(self, client, member):
        from accounts.models import AccountSession

        client.post("/connexion/", {"email": member.email, "password": "MotDePasse-Solide-2026"})
        assert AccountSession.objects.filter(user=member).exists()
