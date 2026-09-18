"""Membres : invitations, changement de rôle, protection du dernier administrateur."""
from __future__ import annotations

from django.utils import timezone

from accounts import services


class TestInvitations:
    def test_un_code_sans_caracteres_ambigus(self, db):
        from tests.factories import make_role

        role = make_role("Invité")
        _user, invitation = services.create_member(email="nouveau@example.test", first_name="Léa",
                                                   last_name="Martin", role=role)
        assert len(invitation.code) == 6
        assert not set(invitation.code) & set("O0I1")

    def test_le_compte_cree_est_en_attente(self, db):
        from tests.factories import make_role

        role = make_role("Invité")
        user, _invitation = services.create_member(email="attente@example.test", first_name="Léa",
                                                   last_name="Martin", role=role)
        assert user.status == "pending"

    def test_acceptation_valide_le_compte(self, db):
        from tests.factories import make_role

        role = make_role("Invité")
        _user, invitation = services.create_member(email="accepte@example.test", first_name="Léa",
                                                   last_name="Martin", role=role)
        ok, message = services.accept_invitation(invitation, "MotDePasse-Solide-2026")
        assert ok is True, message
        invitation.user.refresh_from_db()
        assert invitation.user.status == "active"

    def test_une_invitation_expiree_est_refusee(self, db):
        from tests.factories import make_role

        role = make_role("Invité")
        _user, invitation = services.create_member(email="expire@example.test", first_name="Léa",
                                                   last_name="Martin", role=role)
        invitation.expires_at = timezone.now() - timezone.timedelta(days=1)
        invitation.save(update_fields=["expires_at"])
        ok, _message = services.accept_invitation(invitation, "MotDePasse-Solide-2026")
        assert ok is False

    def test_renouvellement_prolonge_la_validite(self, db):
        from tests.factories import make_role

        role = make_role("Invité")
        _user, invitation = services.create_member(email="renouveler@example.test", first_name="Léa",
                                                   last_name="Martin", role=role)
        before = invitation.expires_at
        invitation.renew(30)
        assert invitation.expires_at > before

    def test_revocation_en_expirant_linvitation(self, db):
        from tests.factories import make_role

        role = make_role("Invité")
        _user, invitation = services.create_member(email="revoque@example.test", first_name="Léa",
                                                   last_name="Martin", role=role)
        assert invitation.is_valid is True
        invitation.expires_at = timezone.now()
        invitation.save(update_fields=["expires_at"])
        assert invitation.is_valid is False


class TestRoles:
    def test_changement_de_role_trace(self, member, admin):
        from tests.factories import make_role

        new_role = make_role("Trésorier de test")
        services.change_role(member, new_role, admin)
        member.refresh_from_db()
        assert member.role_id == new_role.pk

    def test_le_dernier_administrateur_ne_peut_pas_etre_retire(self, admin):
        assert services.last_administrator(admin) is True

    def test_un_second_administrateur_peut_etre_retire(self, db):
        from tests.factories import make_admin

        first = make_admin("premier@example.test")
        second = make_admin("second@example.test")
        assert services.last_administrator(second) is False
        assert services.active_administrators() >= 2
        assert first.pk != second.pk


class TestAnonymisation:
    def test_anonymiser_pseudonymise_sans_supprimer_le_compte(self, member):
        identifier = member.pk
        member.anonymize()
        member.refresh_from_db()
        assert member.pk == identifier
        assert member.status == "anonymized"
        assert member.first_name == "Membre" and member.last_name == "supprimé"
        assert member.email.startswith("anonyme-") and member.email.endswith("@supprime.invalid")
        assert member.totp_enabled is False

    def test_le_compte_anonymise_ne_peut_plus_se_connecter(self, client, member):
        member.anonymize()
        response = client.post("/connexion/", {"email": "membre-test@example.test",
                                               "password": "MotDePasse-Solide-2026"})
        assert not response.wsgi_request.user.is_authenticated


class TestPagesMembres:
    def test_liste_des_membres(self, admin_client):
        assert admin_client.get("/membres/").status_code == 200

    def test_fiche_membre(self, admin_client, member):
        assert admin_client.get("/membres/%d/" % member.pk).status_code == 200

    def test_export_des_membres(self, admin_client):
        response = admin_client.get("/membres/export/")
        assert response.status_code == 200

    def test_un_lecteur_ne_peut_pas_inviter(self, db, client):
        from tests.factories import make_role, make_user

        role = make_role("Lecteur membres", levels={"dashboard": 1, "members": 1})
        user = make_user("lecteur-membres@example.test", role=role)
        client.force_login(user)
        assert client.get("/membres/inviter/").status_code == 403
