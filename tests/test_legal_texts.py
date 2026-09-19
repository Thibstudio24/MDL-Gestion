"""Textes légaux par défaut : RGPD, charte, mentions, règlement."""
from __future__ import annotations

from django.urls import reverse

from core.models import LegalDocument


class TestGeneration:
    def test_quatre_textes_personnalises(self, db):
        from core.legal_texts import ensure_legal_texts

        assert ensure_legal_texts() == 4
        assert LegalDocument.objects.count() == 4
        rgpd = LegalDocument.objects.get(kind="rgpd")
        assert "CNIL" in rgpd.body and "10 ans" in rgpd.body and "portabilité" in rgpd.body
        charte = LegalDocument.objects.get(kind="charte")
        assert charte.requires_acceptance is True and charte.published is True
        mentions = LegalDocument.objects.get(kind="mentions")
        assert "alwaysdata" in mentions.body

    def test_jamais_de_doublon_ni_ecrasement(self, db):
        from core.legal_texts import ensure_legal_texts

        ensure_legal_texts()
        rgpd = LegalDocument.objects.get(kind="rgpd")
        rgpd.body = "Texte réécrit par l'association."
        rgpd.save()
        assert ensure_legal_texts() == 0
        assert LegalDocument.objects.get(kind="rgpd").body == "Texte réécrit par l'association."

    def test_bouton_des_reglages(self, admin_client):
        reponse = admin_client.post(reverse("settings:settings_texts_generate"))
        assert reponse.status_code == 302
        assert LegalDocument.objects.count() == 4

    def test_bouton_reserve_aux_administrateurs(self, member_client):
        reponse = member_client.post(reverse("settings:settings_texts_generate"))
        assert reponse.status_code in (302, 403)
        assert LegalDocument.objects.count() == 0


class TestCharteALaConnexion:
    def test_charte_proposee_sur_la_page_bienvenue(self, member_client, db):
        from core.legal_texts import ensure_legal_texts

        ensure_legal_texts()
        page = member_client.get(reverse("auth:welcome"))
        assert page.status_code == 200
        contenu = page.content.decode()
        assert 'name="accept_charte"' in contenu and "/parametres/charte/" in contenu

    def test_acceptation_horodatee(self, member_client, member, db):
        from core.legal_texts import ensure_legal_texts

        ensure_legal_texts()
        charte = LegalDocument.objects.get(kind="charte")
        reponse = member_client.post(reverse("auth:welcome"),
                                     {"accept_charte": "on", "receive_personal_email": "on"})
        assert reponse.status_code == 302
        acceptation = member.legal_acceptances.filter(document=charte).first()
        assert acceptation is not None and acceptation.accepted_at is not None
