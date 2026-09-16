"""Socle : thème, réglages, formats français, journal d'audit, endpoints PWA, santé."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.template import Context, Template

from core import theme
from core.models import Setting
from core.templatetags.ui import date_fr, kb, money, signed_money


def render(source: str, **context) -> str:
    return Template("{%% load ui %%}%s" % source).render(Context(context))


class TestFormatsFrancais:
    def test_montant_avec_espace_insecable_et_virgule(self):
        # 1 250,50 € avec espace insécable fine (U+202F) et virgule décimale française
        assert money(Decimal("1250.50")) == "1\u202f250,50 €"

    def test_montant_negatif_avec_signe_typographique(self):
        assert money(Decimal("-42.00")) == "\u221242,00 €"

    def test_montant_signe(self):
        assert signed_money(Decimal("12.00")) == "+12,00 €"
        assert signed_money(Decimal("-12.00")) == "\u221212,00 €"

    def test_date_lundi_debut_de_semaine(self):
        import datetime

        assert date_fr(datetime.date(2026, 9, 14)) == "14/09/2026"

    def test_taille_de_fichier(self):
        assert kb(1536).endswith("Ko")

    def test_filtre_dans_un_gabarit(self):
        assert "1 250,50".replace(" ", "\u202f") in render("{{ valeur|money }}", valeur=Decimal("1250.50"))


class TestTheme:
    def test_six_palettes_proposees(self):
        assert len(theme.PALETTES) == 6

    def test_css_construit_contient_les_variables(self):
        css = theme.build_css({"palette": "ardoise", "mode": "light"})
        assert ":root" in css and "--primary" in css and "--bg" in css

    def test_apercu_svg(self):
        svg = theme.preview_svg("ardoise", "light")
        assert svg.startswith("<svg") and "</svg>" in svg

    def test_choix_de_palettes_pour_un_formulaire(self):
        # 6 palettes + l'option « suivre la couleur de l'association »
        assert len(theme.palette_choices()) == 7

    def test_endpoint_theme_css(self, client, db):
        response = client.get("/theme.css")
        assert response.status_code == 200
        assert "text/css" in response["Content-Type"]


class TestReglages:
    def test_lecture_dune_valeur_par_defaut(self, db):
        assert Setting.value("quota", "max_file_mb", 10) == 10

    def test_ecriture_puis_lecture(self, db):
        Setting.update_section("quota", {"max_file_mb": 25})
        assert Setting.value("quota", "max_file_mb", 10) == 25

    def test_marque_de_lassociation(self, db):
        Setting.update_section("branding", {"nom": "MDL du lycée Camille-Claudel"})
        assert Setting.brand()["nom"] == "MDL du lycée Camille-Claudel"


class TestPwaEtSante:
    def test_manifest(self, client, db):
        response = client.get("/manifest.webmanifest")
        assert response.status_code == 200
        assert "application/manifest+json" in response["Content-Type"]

    def test_service_worker(self, client, db):
        response = client.get("/service-worker.js")
        assert response.status_code == 200
        assert "mdl-shell" in response.content.decode()

    def test_page_hors_ligne(self, client, db):
        assert client.get("/hors-ligne/").status_code == 200

    def test_sante_sans_authentification(self, client, db):
        response = client.get("/sante/")
        assert response.status_code == 200

    def test_sante_signale_letat(self, admin_client):
        from core import services

        assert services.health()["status"] in ("ok", "warning", "danger")


class TestJournalAudit:
    def test_ecriture_dune_ligne(self, admin):
        from audit import services as audit

        entry = audit.log(admin, "member.created", "members", admin, "test")
        assert entry.pk and entry.actor_id == admin.pk

    def test_une_ligne_existante_ne_peut_pas_etre_modifiee(self, admin):
        from audit import services as audit
        from audit.models import AuditEntry

        entry = audit.log(admin, "member.created", "members", admin, "test")
        with pytest.raises(Exception) as excinfo:
            entry.message = "falsifié"
            entry.save()
        assert "modifi" in str(excinfo.value).lower() or "interdit" in str(excinfo.value).lower()
        assert AuditEntry.objects.get(pk=entry.pk).message == "test"

    def test_une_ligne_ne_peut_pas_etre_supprimee(self, admin):
        from audit import services as audit

        entry = audit.log(admin, "member.created", "members", admin, "test")
        with pytest.raises(Exception) as excinfo:
            entry.delete()
        assert "supprim" in str(excinfo.value).lower() or "interdit" in str(excinfo.value).lower()

    def test_les_changements_sont_enregistres(self, admin):
        from audit import services as audit

        entry = audit.log(admin, "role.updated", "roles", None, "test",
                          previous={"niveau": 1}, current={"niveau": 2})
        assert entry.changes

    def test_purge_a_sec_renvoie_un_nombre(self, db):
        from audit import services as audit

        assert audit.purge_audit(5, dry_run=True) == 0


class TestErreurs:
    def test_page_404(self, admin_client):
        assert admin_client.get("/page-inexistante/").status_code == 404

    def test_refus_403_pour_un_module_sans_droit(self, member_client):
        response = member_client.get("/audit/")
        assert response.status_code == 403


class TestRenduDesMessages:
    def test_le_markdown_est_rendu(self):
        from core.templatetags.ui import markdown

        assert "<strong>Gras</strong>" in markdown("**Gras**")

    def test_le_html_brut_est_echappe(self):
        from core.templatetags.ui import markdown

        rendu = markdown("<script>alert(1)</script>")
        assert "<script>" not in rendu
        assert "&lt;script&gt;" in rendu

    def test_un_message_vide_ne_casse_pas(self):
        from core.templatetags.ui import markdown

        assert markdown("") == ""
