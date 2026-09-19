"""Stockage des fichiers (serveur / tiers S3), dossiers et suppression de documents."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from core.models import Setting
from core.storage import ConfiguredStorage, S3Error, s3_pret, signed_headers


class FakeS3:
    """Remplace s3_request : un bucket en mémoire pour vérifier les appels."""

    def __init__(self, fail=False):
        self.objets = {}
        self.fail = fail
        self.appels = []

    def __call__(self, cfg, method, name, payload=b""):
        self.appels.append((method, name))
        if self.fail:
            raise S3Error("S3 %s %s : HTTP 403 Forbidden" % (method, name))
        if method == "PUT":
            self.objets[name] = payload
            return b""
        if method == "HEAD":
            if name not in self.objets:
                raise S3Error("S3 HEAD %s : HTTP 404 Not Found" % name)
            return b""
        if method == "GET":
            if name not in self.objets:
                raise S3Error("S3 GET %s : HTTP 404 Not Found" % name)
            return self.objets[name]
        if method == "DELETE":
            self.objets.pop(name, None)
            return b""
        raise AssertionError(method)


@pytest.fixture(autouse=True)
def _reset_stockage(db):
    yield
    Setting.update_section("stockage", {"provider": "local", "endpoint": "", "region": "auto",
                                        "bucket": "", "access_key": "", "secret_key": ""})


S3_CFG = {"provider": "s3", "endpoint": "https://s3.eu-west-005.backblazeb2.com",
          "region": "eu-west-005", "bucket": "mdl-test", "access_key": "cle", "secret_key": "sec"}


class TestClientS3:
    def test_s3_pret_exige_les_quatre_valeurs(self):
        assert s3_pret(S3_CFG) is True
        incomplet = {**S3_CFG, "bucket": ""}
        assert s3_pret(incomplet) is False
        assert s3_pret({"provider": "local"}) is False

    def test_signature_sigv4_conforme_au_vecteur_aws(self):
        """Vecteur officiel AWS (S3 API, « Example: GET Object ») : même requête,
        mêmes identifiants d'exemple → la signature doit être identique au octet près."""
        entetes = signed_headers(
            "GET", "examplebucket.s3.amazonaws.com", "/test.txt",
            "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1",
            now=datetime(2013, 5, 24, tzinfo=UTC),
            extra_headers={"range": "bytes=0-9"})
        assert ("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
                in entetes["Authorization"])

    def test_region_b2_detectee_dans_l_endpoint(self):
        """Un HTTP 403 B2 venait d'une région « auto » signée : la région doit être
        déduite de l'endpoint (eu-central-003) quand l'utilisateur laisse « auto »."""
        from core.storage import effective_region

        cfg = {**S3_CFG, "region": "auto", "endpoint": "s3.eu-central-003.backblazeb2.com"}
        entetes = signed_headers("GET", "s3.eu-central-003.backblazeb2.com", "/o", "cle", "sec",
                                 effective_region(cfg))
        assert "/eu-central-003/s3/aws4_request" in entetes["Authorization"]

    def test_region_explicite_prioritaire(self):
        from core.storage import effective_region

        assert effective_region({"region": "us-west-004",
                                 "endpoint": "s3.eu-central-003.backblazeb2.com"}) == "us-west-004"

    def test_r2_garde_auto(self):
        from core.storage import effective_region

        assert effective_region({"region": "auto",
                                 "endpoint": "abc123.r2.cloudflarestorage.com"}) == "auto"

    def test_le_code_erreur_du_fournisseur_est_expose(self, monkeypatch):
        import io
        import urllib.error

        def urlopen_boite(request, timeout=30):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {},
                                         io.BytesIO(b"<Error><Code>SignatureDoesNotMatch</Code>"
                                                    b"<Message>Signature mismatch</Message></Error>"))

        monkeypatch.setattr("urllib.request.urlopen", urlopen_boite)
        from core.storage import s3_request

        with pytest.raises(S3Error) as exc:
            s3_request(S3_CFG, "PUT", "x.txt", payload=b"z")
        assert "403" in str(exc.value) and "SignatureDoesNotMatch" in str(exc.value)

    def test_defaut_sur_le_disque_du_serveur(self, settings):
        chemin = default_storage.save("tests/local.txt", ContentFile(b"bonjour"))
        try:
            with default_storage.open(chemin, "rb") as handle:
                assert handle.read() == b"bonjour"
        finally:
            default_storage.delete(chemin)

    def test_ecriture_et_lecture_chez_le_fournisseur(self, settings, monkeypatch):
        Setting.update_section("stockage", S3_CFG)
        faux = FakeS3()
        monkeypatch.setattr("core.storage.s3_request", faux)
        chemin = default_storage.save("tests/tiers.txt", ContentFile(b"chez b2"))
        assert ("PUT", chemin) in faux.appels
        assert faux.objets[chemin] == b"chez b2"
        with default_storage.open(chemin, "rb") as handle:
            assert handle.read() == b"chez b2"
        default_storage.delete(chemin)
        assert ("DELETE", chemin) in faux.appels

    def test_repli_local_pour_les_anciens_fichiers(self, monkeypatch):
        Setting.update_section("stockage", S3_CFG)
        faux = FakeS3()
        monkeypatch.setattr("core.storage.s3_request", faux)
        # fichier présent uniquement sur le disque (téléversé avant le passage au tiers)
        local = ConfiguredStorage().local
        ancien = local.save("tests/ancien.txt", ContentFile(b"vieux fichier"))
        try:
            with default_storage.open(ancien, "rb") as handle:
                assert handle.read() == b"vieux fichier"
        finally:
            local.delete(ancien)

    def test_panne_du_fourniteur_ne_casse_pas_la_lecture_locale(self, monkeypatch):
        Setting.update_section("stockage", S3_CFG)
        monkeypatch.setattr("core.storage.s3_request", FakeS3(fail=True))
        local = ConfiguredStorage().local
        ancien = local.save("tests/panne.txt", ContentFile(b"toujours la"))
        try:
            with default_storage.open(ancien, "rb") as handle:
                assert handle.read() == b"toujours la"
        finally:
            local.delete(ancien)


class TestReglagesStockage:
    def test_vue_enregistre_le_choix(self, admin_client):
        reponse = admin_client.post("/reglages/stockage/", {
            "provider": "s3", "endpoint": S3_CFG["endpoint"], "region": "eu-west-005",
            "bucket": "mdl", "access_key": "cle", "secret_key": "sec"})
        assert reponse.status_code == 302
        data = Setting.data().get("stockage")
        assert data["provider"] == "s3" and data["bucket"] == "mdl" and data["secret_key"] == "sec"

    def test_tiers_incomplet_refuse(self, admin_client):
        reponse = admin_client.post("/reglages/stockage/", {
            "provider": "s3", "endpoint": "", "region": "auto", "bucket": "",
            "access_key": "", "secret_key": ""})
        assert reponse.status_code == 200  # rechargé avec les erreurs
        assert Setting.data()["stockage"]["provider"] == "local"

    def test_cle_secrete_conservee_si_vide(self, admin_client):
        Setting.update_section("stockage", S3_CFG)
        admin_client.post("/reglages/stockage/", {
            "provider": "s3", "endpoint": S3_CFG["endpoint"], "region": "eu-west-005",
            "bucket": "mdl", "access_key": "cle", "secret_key": ""})
        assert Setting.data()["stockage"]["secret_key"] == "sec"

    def test_test_de_connexion_succes(self, admin_client, monkeypatch):
        Setting.update_section("stockage", S3_CFG)
        faux = FakeS3()
        monkeypatch.setattr("core.views_settings.s3_request", faux, raising=False)
        monkeypatch.setattr("core.storage.s3_request", faux)
        reponse = admin_client.post("/reglages/stockage/test/")
        assert reponse.status_code == 302
        assert ("PUT", "mdl-test/connexion.txt") in faux.appels
        assert ("DELETE", "mdl-test/connexion.txt") in faux.appels

    def test_test_de_connexion_echec(self, admin_client, monkeypatch):
        Setting.update_section("stockage", S3_CFG)
        monkeypatch.setattr("core.storage.s3_request", FakeS3(fail=True))
        reponse = admin_client.post("/reglages/stockage/test/")
        assert reponse.status_code == 302  # erreur affichée, pas d'exception

    def test_page_inaccessible_aux_membres(self, member_client):
        assert member_client.get("/reglages/stockage/").status_code in (302, 403)

    def test_installation_propose_le_choix(self, client):
        session = client.session
        session["install_admin"] = "admin@example.test"
        session.save()
        page = client.get("/installation/termine/")
        assert page.status_code == 200
        assert "Stockage des fichiers" in page.content.decode()

    def test_installation_enregistre_le_stockage(self, client):
        session = client.session
        session["install_admin"] = "admin@example.test"
        session.save()
        reponse = client.post("/installation/stockage/", {
            "provider": "s3", "endpoint": S3_CFG["endpoint"], "region": "eu-west-005",
            "bucket": "mdl", "access_key": "cle", "secret_key": "sec"})
        assert reponse.status_code == 302
        assert Setting.data()["stockage"]["provider"] == "s3"


class TestDossiers:
    def test_creation_avec_les_champs_visibles_seulement(self, admin_client, db):
        """Régression : « Ce champ est obligatoire » alors que tout est rempli.

        Le formulaire n'envoie ni ordre ni parent : ils doivent rester optionnels.
        """
        from documents.models import Category, Folder

        categorie = Category.objects.create(name="Fiches clubs")
        reponse = admin_client.post("/documents/dossiers/creer/", {
            "category": categorie.pk, "name": "Club théâtre", "description": "Les fiches"})
        assert reponse.status_code == 302
        dossier = Folder.objects.get(name="Club théâtre")
        assert dossier.order == 100 and dossier.parent is None

    def test_creation_dun_sous_dossier(self, admin_client, db):
        from documents.models import Category, Folder

        categorie = Category.objects.create(name="Fiches clubs")
        racine = Folder.objects.create(category=categorie, name="Clubs 2026")
        reponse = admin_client.post("/documents/dossiers/creer/", {
            "category": categorie.pk, "parent": racine.pk, "name": "Théâtre"})
        assert reponse.status_code == 302
        assert Folder.objects.get(name="Théâtre").parent == racine

    def test_page_categories_liste_les_parents_possibles(self, admin_client, db):
        from documents.models import Category, Folder

        categorie = Category.objects.create(name="Docs")
        Folder.objects.create(category=categorie, name="Racine")
        page = admin_client.get("/documents/categories/")
        assert "Racine" in page.content.decode()


class TestSuppressionDocument:
    def test_trame_du_bureau_inclut_le_droit_de_suppression(self):
        from core.permissions import BOARD_TEMPLATE

        for nom, trame in BOARD_TEMPLATE.items():
            if trame.get("documents", 0) >= 2:
                assert "documents.delete" in trame.get("fine", []), nom

    def test_carte_suppression_visible_avec_le_droit_fin(self, admin_client, db):
        from documents.models import Category, Document

        categorie = Category.objects.create(name="Docs")
        document = Document.objects.create(category=categorie, title="Règlement")
        page = admin_client.get("/documents/%s/" % document.pk)
        assert "Mettre à la corbeille" in page.content.decode()

    def test_indication_pour_un_role_sans_droit_fin(self, client, db):
        from documents.models import Category, Document
        from tests.factories import make_role, make_user

        role = make_role("Éditeur", levels={"documents": 2}, fine=[])
        user = make_user("editeur@example.test", "Éditeur", role=role)
        categorie = Category.objects.create(name="Docs")
        document = Document.objects.create(category=categorie, title="Règlement")
        client.force_login(user)
        page = client.get("/documents/%s/" % document.pk)
        assert "Supprimer des documents" in page.content.decode()


class TestPurgeDuBucket:
    def test_liste_les_objets_pages_comprises(self, monkeypatch):
        import io
        import urllib.request

        pages = [b'<?xml version="1.0"?><ListBucketResult>'
                 b'<Contents><Key>a.txt</Key></Contents><Contents><Key>b/c.txt</Key></Contents>'
                 b'<NextContinuationToken>tok</NextContinuationToken></ListBucketResult>',
                 b'<ListBucketResult><Contents><Key>d.txt</Key></Contents></ListBucketResult>']

        def urlopen_pages(request, timeout=30):
            return io.BytesIO(pages.pop(0))

        monkeypatch.setattr(urllib.request, "urlopen", urlopen_pages)
        from core.storage import list_objects

        assert list_objects(S3_CFG) == ["a.txt", "b/c.txt", "d.txt"]

    def test_purge_supprime_tout(self, monkeypatch):
        from core.storage import purge_all

        faux = FakeS3()
        faux.objets.update({"a.txt": b"1", "b.txt": b"2", "c.txt": b"3"})
        monkeypatch.setattr("core.storage.s3_request", faux)
        monkeypatch.setattr("core.storage.list_objects", lambda cfg: list(faux.objets))
        assert purge_all(S3_CFG) == 3
        assert faux.objets == {}
