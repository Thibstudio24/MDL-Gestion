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
from mail.services import _try_send, queue_email

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


def test_e_mail_de_test_part_immediatement(admin_client, settings):
    settings.MAIL_ENABLED = True
    reponse = admin_client.post(reverse("settings:settings_smtp_test"), {"email": "cible@example.test"})
    assert reponse.status_code == 302
    assert len(boite_aux_lettres.outbox) == 1
    assert boite_aux_lettres.outbox[0].to == ["cible@example.test"]


def test_test_smtp_desactive_affiche_une_erreur(admin_client):
    reponse = admin_client.post(reverse("settings:settings_smtp_test"),
                                {"email": "cible@example.test"}, follow=True)
    assert "SMTP désactivé" in reponse.content.decode()
    assert len(boite_aux_lettres.outbox) == 0


def test_connexion_derive_le_mode_du_port(settings):
    from mail.services import _connexion_smtp

    settings.TESTING = False
    settings.EMAIL_PORT = 587
    connexion = _connexion_smtp()
    assert connexion.use_tls is True and connexion.use_ssl is False
    settings.EMAIL_PORT = 465
    connexion = _connexion_smtp()
    assert connexion.use_ssl is True and connexion.use_tls is False


def test_courriel_deja_pris_n_est_pas_envoye_deux_fois(db, settings, monkeypatch):
    settings.MAIL_ENABLED = True
    settings.TESTING = False
    envois = []
    monkeypatch.setattr(boite_aux_lettres.EmailMultiAlternatives, "send",
                        lambda self, *a, **k: envois.append(1))
    item = Outbox.objects.create(to_email="a@example.test", subject="S", text_body="B")
    Outbox.objects.filter(pk=item.pk).update(status="sending")
    assert _try_send(item) is True
    assert envois == []


def test_lien_invitation_est_absolu_sans_base_url(db, settings):
    from accounts import services as comptes
    from tests.factories import make_role

    settings.BASE_URL = ""
    settings.ALLOWED_HOSTS = ["mdl-test.alwaysdata.net"]
    _user, invitation = comptes.create_member(email="lien@example.test", first_name="Léa",
                                              last_name="Martin", role=make_role("Invité"))
    corps = comptes.render_invitation_email(invitation)
    assert "https://mdl-test.alwaysdata.net/inviter/" in corps


def test_base_url_auto_detectee_et_memorisee(admin_client, settings, _instance_json_en_memoire):
    settings.BASE_URL = ""
    settings.ALLOWED_HOSTS = ["testserver", "mdl.alwaysdata.net"]
    admin_client.get("/", HTTP_HOST="mdl.alwaysdata.net")
    assert settings.BASE_URL == "https://mdl.alwaysdata.net"
    assert _instance_json_en_memoire.get("app", {}).get("base_url") == "https://mdl.alwaysdata.net"


def test_lien_invitation_absolu_apres_auto_detection(db, admin_client, settings):
    from accounts import services as comptes
    from tests.factories import make_role

    settings.BASE_URL = ""
    settings.ALLOWED_HOSTS = ["testserver", "mdl.alwaysdata.net"]
    admin_client.get("/", HTTP_HOST="mdl.alwaysdata.net")
    _user, invitation = comptes.create_member(email="auto@example.test", first_name="Léa",
                                              last_name="Martin", role=make_role("Invité"))
    assert "https://mdl.alwaysdata.net/inviter/" in comptes.render_invitation_email(invitation)


def test_lien_notification_est_absolu(db, settings, monkeypatch):
    import notifications.services as notif
    from tests.factories import make_role, make_user

    monkeypatch.setattr(notif, "in_quiet_hours", lambda user: False)
    settings.BASE_URL = ""
    settings.ALLOWED_HOSTS = ["mdl-test.alwaysdata.net"]
    user = make_user("notif@example.test", role=make_role("Membre"))
    notif.notify(user, "bilan_generated", "Bilan disponible", "Solde : 0", url="/documents/1/")
    item = Outbox.objects.get()
    assert "Lien : https://mdl-test.alwaysdata.net/documents/1/" in item.text_body


def test_courriel_unitaire_part_immediatement(db, settings, monkeypatch):
    from django.core.mail import get_connection

    import mail.services as ms

    monkeypatch.setattr(ms, "_connexion_smtp", lambda: get_connection())
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
