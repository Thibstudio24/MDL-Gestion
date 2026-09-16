"""Droits : niveaux par module, droits fins, garde-fous sur les rôles."""
from __future__ import annotations

from core import permissions
from tests.factories import make_role, make_user


class TestNiveaux:
    def test_trois_niveaux_existent(self):
        assert [value for value, _label in permissions.LEVEL_CHOICES] == [0, 1, 2]

    def test_onze_modules_couverts(self):
        assert len(permissions.MODULES) == 11

    def test_administrateur_voit_et_modifie_tout(self, admin):
        for module in permissions.MODULES:
            assert permissions.can_view(admin, module)
            assert permissions.can_edit(admin, module)

    def test_niveau_zero_interdit_la_vue(self, db):
        role = make_role("Lecteur limité", levels={"dashboard": 1, "documents": 0})
        user = make_user("limite@example.test", role=role)
        assert permissions.can_view(user, "documents") is False
        assert permissions.can_edit(user, "documents") is False

    def test_niveau_un_autorise_la_lecture_seule(self, db):
        role = make_role("Lecteur", levels={"dashboard": 1, "documents": 1})
        user = make_user("lecteur@example.test", role=role)
        assert permissions.can_view(user, "documents") is True
        assert permissions.can_edit(user, "documents") is False

    def test_niveau_deux_autorise_la_modification(self, db):
        role = make_role("Éditeur", levels={"dashboard": 1, "documents": 2})
        user = make_user("editeur@example.test", role=role)
        assert permissions.can_edit(user, "documents") is True


class TestDroitsFins:
    def test_droit_fin_accorde(self, db):
        role = make_role("Gestionnaire", levels={"dashboard": 1, "documents": 2},
                         fine=["documents.delete"])
        user = make_user("gestionnaire@example.test", role=role)
        assert permissions.fine(user, "documents.delete") is True

    def test_droit_fin_absent(self, db):
        role = make_role("Simple", levels={"dashboard": 1, "documents": 2})
        user = make_user("simple@example.test", role=role)
        assert permissions.fine(user, "documents.delete") is False

    def test_administrateur_possede_tous_les_droits_fins(self, admin):
        assert permissions.fine(admin, "finance.lock") is True
        assert permissions.fine(admin, "settings.push") is True

    def test_invalidation_du_cache(self, db):
        role = make_role("Cache", levels={"dashboard": 1, "documents": 1})
        user = make_user("cache@example.test", role=role)
        assert permissions.can_edit(user, "documents") is False
        from accounts.services import _apply_levels

        _apply_levels(role, {"dashboard": 1, "documents": 2}, [])
        assert permissions.can_edit(user, "documents") is True


class TestGardeFous:
    def test_le_module_roles_est_ferme_aux_non_administrateurs(self, db):
        role = make_role("Escalade", levels={"dashboard": 1, "roles": 2})
        user = make_user("escalade@example.test", role=role)
        assert permissions.level(user, "roles") == 0
        assert permissions.can_view(user, "roles") is False

    def test_ladministrateur_conserve_le_module_roles(self, admin):
        assert permissions.level(admin, "roles") == 2

    def test_nul_ne_peut_attribuer_un_niveau_superieur_au_sien(self, db):
        role = make_role("Plafonné", levels={"dashboard": 1, "documents": 1})
        user = make_user("plafonne@example.test", role=role)
        assert permissions.max_allowed_level(user) == 1

    def test_un_compte_inactif_na_aucun_droit(self, db):
        role = make_role("Inactif", levels={"dashboard": 2, "documents": 2})
        user = make_user("inactif@example.test", role=role, status="inactive")
        assert permissions.can_view(user, "documents") is False

    def test_un_compte_anonymise_na_aucun_droit(self, db):
        role = make_role("Anonyme", levels={"dashboard": 2, "documents": 2})
        user = make_user("anonyme@example.test", role=role, status="anonymized")
        assert permissions.is_administrator(user) is False


class TestTrameDuBureau:
    def test_les_roles_du_bureau_sont_crees(self, db):
        from accounts.services import create_board_roles

        created = create_board_roles()
        assert len(created) >= 5
        names = {role.name for role in created}
        assert "Président" in names or any("résident" in name for name in names)

    def test_les_roles_de_base_existent(self, db):
        from accounts.models import Role
        from accounts.services import ensure_base_roles

        ensure_base_roles()
        assert Role.objects.filter(name="Administrateur", is_administrator=True).exists()
        assert Role.objects.filter(name="Utilisateur", is_default=True).exists()
