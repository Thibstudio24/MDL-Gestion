"""Documents : formats acceptés, quota, versions, corbeille, verrouillage de catégorie."""
from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documents import services
from documents.models import Category, Document
from documents.services import UploadError


def upload(name: str, size: int = 2048) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"x" * size)


@pytest.fixture
def category(db):
    from documents.services import ensure_default_categories

    ensure_default_categories()
    return Category.objects.get(name="Comptes rendus")


class TestFormats:
    def test_pdf_accepte(self, db):
        assert services.validate_upload("compte-rendu.pdf", 1024) == "pdf"

    def test_bureautique_acceptee(self, db):
        for name in ("rapport.docx", "budget.xlsx", "note.odt", "photos.png", "archive.zip"):
            assert services.validate_upload(name, 1024)

    def test_executable_refuse(self, db):
        for name in ("virus.exe", "script.sh", "macro.js", "installeur.msi"):
            with pytest.raises(UploadError):
                services.validate_upload(name, 1024)

    def test_extension_inconnue_refusee(self, db):
        with pytest.raises(UploadError):
            services.validate_upload("donnees.xyz", 1024)

    def test_fichier_vide_refuse(self, db):
        with pytest.raises(UploadError):
            services.validate_upload("vide.pdf", 0)

    def test_taille_maximale_reglable(self, db):
        from core.models import Setting

        Setting.update_section("quota", {"max_file_mb": 1})
        with pytest.raises(UploadError):
            services.validate_upload("gros.pdf", 2 * 1024 * 1024)


class TestQuota:
    def test_usage_calcule(self, db):
        usage = services.quota_usage()
        assert {"used", "total", "pct"} <= set(usage)

    def test_refus_au_dela_du_quota(self, db):
        from core.models import Setting

        Setting.update_section("quota", {"total_mb": 1})
        with pytest.raises(UploadError):
            services.check_quota(10 * 1024 * 1024)


class TestVersions:
    def test_trois_versions_conservees(self, category, admin):
        document = Document.objects.create(category=category, title="CR", owner=admin)
        for index in range(5):
            services.store_version(document, upload("v%d.pdf" % index), admin, comment="v%d" % index)
        assert document.versions.count() == 3
        assert document.current.version == 5

    def test_la_version_courante_est_la_derniere(self, category, admin):
        document = Document.objects.create(category=category, title="CR", owner=admin)
        first = services.store_version(document, upload("a.pdf"), admin)
        second = services.store_version(document, upload("b.pdf"), admin)
        document.refresh_from_db()
        first.refresh_from_db()
        assert document.current_id == second.pk
        assert first.is_current is False

    def test_restaurer_une_version_cree_une_nouvelle_version(self, category, admin):
        document = Document.objects.create(category=category, title="CR", owner=admin)
        first = services.store_version(document, upload("a.pdf"), admin)
        services.store_version(document, upload("b.pdf"), admin)
        services.restore_version(document, first, admin)
        document.refresh_from_db()
        assert document.current.version == 3
        assert document.versions.count() == 3

    def test_empreinte_sha256_calculee(self, category, admin):
        document = Document.objects.create(category=category, title="CR", owner=admin)
        version = services.store_version(document, upload("a.pdf"), admin)
        assert len(version.sha256) == 64


class TestCorbeille:
    def test_suppression_logique_puis_restauration(self, category, admin):
        document = Document.objects.create(category=category, title="CR", owner=admin)
        services.store_version(document, upload("a.pdf"), admin)
        services.soft_delete(document, admin, "doublon")
        assert Document.objects.trashed().count() == 1
        assert Document.objects.live().count() == 0
        services.restore(document, admin)
        assert Document.objects.live().count() == 1

    def test_motif_obligatoire(self, category, admin):
        document = Document.objects.create(category=category, title="CR", owner=admin)
        with pytest.raises(UploadError):
            services.soft_delete(document, admin, "")

    def test_purge_de_la_corbeille_a_sec(self, db):
        assert isinstance(services.purge_trash(30, dry_run=True), int)


class TestCategories:
    def test_quatre_categories_par_defaut(self, db):
        from documents.services import ensure_default_categories

        ensure_default_categories()
        assert Category.objects.count() == 4

    def test_categorie_verrouillee_bloque_un_editeur_sans_droit_fin(self, category, db):
        from tests.factories import make_role, make_user

        category.locked_read = True
        category.save(update_fields=["locked_read"])
        role = make_role("Éditeur documents", levels={"dashboard": 1, "documents": 2})
        user = make_user("editeur-docs@example.test", role=role)
        assert services.can_edit_category(user, category) is False

    def test_administrateur_peut_forcer_le_verrou(self, category, admin):
        category.locked_read = True
        category.save(update_fields=["locked_read"])
        from core import permissions

        assert permissions.fine(admin, "documents.categories") is True
        assert services.can_edit_category(admin, category) is True
