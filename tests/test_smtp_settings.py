"""Réglages SMTP : écrits dans config/instance.json, appliqués à chaud, file vidable.

Ces tests verrouillent la correction du trou « le mail ne part pas » : le
formulaire enregistrait autrefois en base seulement, alors que l'envoi lit
settings.EMAIL_* chargés depuis instance.json au démarrage.
"""
from __future__ import annotations

from django.core import mail as boite_aux_lettres
from django.urls import reverse

from audit.models import AuditEntry
from core.models import Setting
from mail.models import Outbox
from mail.services import queue_email

POST_SMTP = {
    "enabled": "on", "host": "smtp.example.test", "port": "587", "use_tls": "on",
    "user": "mdl@example.test", "password": "secret-mdp",
    "mail_from": "mdl@example.test", "rate_per_minute": "15", "fallback": "inapp",
}


def test_enregistrement_ecrit_instance_json_et_applique_a_chaud(admin_client, settings,
                                                                _instance_json_en_memoire):
    reponse = admin_client.post(reverse("settings:settings_smtp"), POST_SMTP)
    assert reponse.status_code == 302
    mail_cfg = _instance_json_en_memoire["mail"]
    assert mail_cfg["host"] == "smtp.example.test"
    assert mail_cfg["password"] == "secret-mdp"
    assert mail_cfg["enabled"] is True
    assert mail_cfg["use_tls"] is True
    assert settings.MAIL_ENABLED is True
    assert settings.EMAIL_HOST == "smtp.example.test"
    assert settings.EMAIL_PORT == 587
    assert settings.EMAIL_HOST_PASSWORD == "secret-mdp"
    assert Setting.data()["mail"]["host"] == "smtp.example.test"


def test_ssl_coche_sur_587_realigne_le_port_465(admin_client, settings):
    donnees = dict(POST_SMTP, use_tls="", use_ssl="on", port="587")
    admin_client.post(reverse("settings:settings_smtp"), donnees)
    assert settings.EMAIL_USE_SSL is True
    assert settings.EMAIL_PORT == 465
    assert Setting.data()["mail"]["port"] == 465


def test_ssl_et_starttls_ensemble_refuses(admin_client):
    donnees = dict(POST_SMTP, use_ssl="on", use_tls="on")
    reponse = admin_client.post(reverse("settings:settings_smtp"), donnees)
    assert reponse.status_code == 200
    assert "pas les deux" in reponse.content.decode()


def test_mot_de_passe_vide_conserve_l_ancien(admin_client, settings, _instance_json_en_memoire):
    admin_client.post(reverse("settings:settings_smtp"), POST_SMTP)
    sans_mdp = dict(POST_SMTP)
    sans_mdp.pop("password")
    admin_client.post(reverse("settings:settings_smtp"), sans_mdp)
    assert _instance_json_en_memoire["mail"]["password"] == "secret-mdp"
    assert settings.EMAIL_HOST_PASSWORD == "secret-mdp"


def test_e_mail_de_test_part_immediatement(admin_client):
    reponse = admin_client.post(reverse("settings:settings_smtp_test"), {"email": "cible@example.test"})
    assert reponse.status_code == 302
    assert len(boite_aux_lettres.outbox) == 1
    assert boite_aux_lettres.outbox[0].to == ["cible@example.test"]


def test_courriel_unitaire_part_immediatement(db, settings):
    settings.MAIL_ENABLED = True
    settings.TESTING = False
    item = queue_email(to_email="invite@example.test", subject="Invitation",
                       text_body="Viens nous rejoindre.", kind="invitation", immediat=True)
    assert item.status == "sent"
    assert len(boite_aux_lettres.outbox) == 1


def test_courriel_unitaire_en_echec_reste_en_file(db, settings, monkeypatch):
    settings.MAIL_ENABLED = True
    settings.TESTING = False

    def echec(self, *args, **kwargs):
        raise OSError("connexion refusée")

    monkeypatch.setattr(boite_aux_lettres.EmailMultiAlternatives, "send", echec)
    item = queue_email(to_email="invite@example.test", subject="Invitation",
                       text_body="Viens nous rejoindre.", kind="invitation", immediat=True)
    assert item.status == "queued"
    assert item.attempts == 1
    assert "connexion refusée" in item.error


def test_drain_sans_smtp_marque_ignores(admin_client):
    Outbox.objects.create(to_email="a@example.test", subject="S", text_body="B")
    reponse = admin_client.post(reverse("settings:settings_smtp_drain"))
    assert reponse.status_code == 302
    item = Outbox.objects.get()
    assert item.status == "skipped"
    assert item.error == "SMTP désactivé"


def test_drain_avec_smtp_envoie_et_journalise(admin_client, settings):
    settings.MAIL_ENABLED = True
    Outbox.objects.create(to_email="a@example.test", subject="S", text_body="B")
    admin_client.post(reverse("settings:settings_smtp_drain"))
    item = Outbox.objects.get()
    assert item.status == "sent"
    assert len(boite_aux_lettres.outbox) == 1
    assert AuditEntry.objects.filter(action="mail.outbox_drained").exists()
