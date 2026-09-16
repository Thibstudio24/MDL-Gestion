"""Journal d'audit des Réglages : chaque modification laisse une trace, sans secret."""
from __future__ import annotations

import pytest
from django.urls import reverse

from audit.models import AuditEntry
from core.models import LegalDocument, Setting


def last(action: str) -> AuditEntry:
    return AuditEntry.objects.filter(action=action).order_by("-id").first()


class TestJournalDesReglages:
    def test_marque(self, admin_client):
        admin_client.post(reverse("settings:settings_brand"), {
            "nom": "MDL Jean-Moulin", "sigle": "MDL", "couleur_principale": "#33556e",
        })
        entry = last("settings.brand_updated")
        assert entry is not None
        assert entry.changes["nom"]["apres"] == "MDL Jean-Moulin"

    def test_quotas(self, admin_client):
        admin_client.post(reverse("settings:settings_quotas"), {
            "max_file_mb": 25, "total_mb": 900, "versions_kept": 3,
            "chores_photos_kept": 6, "mail_purge_years": 1, "purge_inactive_months": 24,
        })
        entry = last("settings.quota_updated")
        assert entry is not None
        assert entry.changes["total_mb"]["apres"] == 900

    def test_securite(self, admin_client):
        admin_client.post(reverse("settings:settings_security"), {
            "password_min_length": 12, "login_max_attempts": 5, "login_lockout_minutes": 15,
            "session_days": 14, "audit_keep_years": 5, "delai_2fa_jours": 30,
        })
        entry = last("settings.security_updated")
        assert entry is not None
        assert entry.level == "warn"

    def test_annee_creee_puis_cloturee_puis_rouverte(self, admin_client, year):
        admin_client.post(reverse("settings:settings_years"), {
            "label": "2030-2031", "start_date": "2030-09-01", "end_date": "2031-08-31",
        })
        created = last("settings.year_created")
        assert created is not None and "2030-2031" in created.message

        url = reverse("settings:settings_year_action", args=[year.pk])
        admin_client.post(url, {"action": "lock"})
        assert last("settings.year_locked") is not None

        admin_client.post(url, {"action": "unlock"})
        assert last("settings.year_unlocked") is not None

    def test_matrice_de_notifications(self, admin_client):
        admin_client.post(reverse("settings:settings_notifications"), {
            "evt-invitation-email": "on",
        })
        assert last("settings.matrix_updated") is not None

    def test_maintenance(self, admin_client):
        admin_client.post(reverse("settings:settings_maintenance"), {
            "maintenance": "on", "maintenance_message": "Fermeture annuelle",
        })
        entry = last("settings.maintenance")
        assert entry is not None
        assert "activé" in entry.message
        assert entry.level == "warn"

    def test_mise_a_jour(self, admin_client):
        admin_client.post(reverse("settings:settings_update"), {
            "update_channel": "stable", "pinned_version": "1.0.0",
        })
        assert last("settings.update_applied") is not None

    def test_texte_legal(self, admin_client):
        document = LegalDocument.objects.create(kind="mentions", title="Mentions", slug="mentions", body="Avant")
        admin_client.post(reverse("settings:settings_text", args=["mentions"]), {
            "title": "Mentions légales", "body": "Après", "published": "on",
        })
        entry = last("settings.legal_updated")
        assert entry is not None
        assert document.slug in entry.message or "Mentions" in entry.message


class TestSecretsJamaisJournalises:
    """Le journal est lisible par tout administrateur et conservé cinq ans."""

    def test_mot_de_passe_smtp_masque(self, admin_client):
        admin_client.post(reverse("settings:settings_smtp"), {
            "enabled": "on", "host": "smtp.example.test", "port": 587, "use_tls": "on",
            "user": "mdl@example.test", "password": "Sup3r-Secret-SMTP",
            "mail_from": "mdl@example.test", "rate_per_minute": 15, "fallback": "email",
        })
        entry = last("settings.smtp_updated")
        assert entry is not None
        assert Setting.value("mail", "password") == "Sup3r-Secret-SMTP", "le réglage conserve le vrai mot de passe"
        assert entry.changes["password"]["apres"] == "***"
        assert "Sup3r-Secret-SMTP" not in str(entry.changes)

    def test_cle_privee_vapid_masquee(self, admin_client):
        admin_client.post(reverse("settings:settings_pwa"), {
            "enabled": "on", "public_key": "BPUBLIC", "private_key": "PRIVEE-CONFIDENTIELLE",
            "claims_email": "mdl@example.test",
        })
        entry = last("settings.push_updated")
        assert entry is not None
        assert entry.changes["private_key"]["apres"] == "***"
        assert "PRIVEE-CONFIDENTIELLE" not in str(entry.changes)
        assert entry.changes["public_key"]["apres"] == "BPUBLIC", "la clé publique reste lisible"


class TestHelperDeMasquage:
    def test_safe_masque_les_cles_sensibles(self):
        from core.views_settings import _safe

        masked = _safe({"password": "abc", "private_key": "xyz", "host": "smtp", "port": 587})
        assert masked == {"password": "***", "private_key": "***", "host": "smtp", "port": 587}

    def test_safe_laisse_une_valeur_vide_visible(self):
        from core.views_settings import _safe

        # Une valeur vide masquée en « *** » ferait croire à un secret présent.
        assert _safe({"password": ""}) == {"password": ""}

    def test_safe_accepte_un_payload_vide(self):
        from core.views_settings import _safe

        assert _safe(None) == {}
        assert _safe({}) == {}


class TestAutresEmetteurs:
    def test_code_de_recuperation_2fa(self, admin, db):
        from accounts.twofa import generate_recovery_codes, use_recovery_code

        raw = generate_recovery_codes(admin)[0]
        assert use_recovery_code(admin, raw) is True
        entry = last("auth.2fa_recovery_used")
        assert entry is not None
        assert entry.level == "warn"
        assert raw not in entry.message, "le code ne doit pas être recopié dans le journal"

    def test_code_de_recuperation_inconnu_ne_journalise_rien(self, admin, db):
        from accounts.twofa import use_recovery_code

        assert use_recovery_code(admin, "XXXX-XXXX") is False
        assert last("auth.2fa_recovery_used") is None

    def test_revocation_d_intervention(self, admin, db):
        from core.models import Intervention
        from core.services import revoke_intervention

        intervention = Intervention.objects.create(action="health", target="", origin="hub", status="queued")
        revoke_intervention(intervention, actor=admin)
        entry = last("devhub.intervention_revoked")
        assert entry is not None
        assert entry.level == "warn"


@pytest.mark.parametrize("action", [
    "settings.brand_updated", "settings.quota_updated", "settings.security_updated",
    "settings.smtp_updated", "settings.push_updated", "settings.matrix_updated",
    "settings.year_created", "settings.year_locked", "settings.year_unlocked",
    "settings.legal_updated", "settings.maintenance", "settings.backup_created",
    "settings.backup_restored", "settings.update_applied",
])
def test_action_declaree_dans_le_vocabulaire(action):
    """Garde-fou : chaque action émise par les Réglages existe dans le modèle."""
    declared = {code for code, _label in AuditEntry._meta.get_field("action").choices}
    assert action in declared


def test_aucune_action_settings_sans_emetteur():
    """Les 14 actions settings.* déclarées doivent toutes avoir un émetteur."""
    import pathlib
    import re

    declared = {code for code, _label in AuditEntry._meta.get_field("action").choices
                if code.startswith("settings.")}
    source = pathlib.Path("core/views_settings.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r"audit\.log\([^,]+,\s*[\"']([^\"']+)[\"']", source))
    assert declared - emitted == set(), "actions déclarées sans émetteur : %s" % sorted(declared - emitted)
