"""Cloche déroulante, suppression définitive, rôles réservés, réinitialisation du site."""
from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from accounts import services as comptes
from accounts.models import Role, User
from audit.models import AuditEntry
from notifications.models import Notification


def _reauth_fraiche(client):
    session = client.session
    session["reauth_at"] = timezone.now().isoformat()
    session.save()


def test_cloche_compteur_panneau_et_ouverture(db, admin_client, admin):
    Notification.objects.create(user=admin, kind="bilan_generated",
                                title="Bilan disponible", url="/documents/1/")
    texte = admin_client.get("/").content.decode()
    assert "data-bell-toggle" in texte
    assert "bell-count" in texte

    panneau = admin_client.get(reverse("notifications:panel"))
    items = panneau.json()["items"]
    assert len(items) == 1 and items[0]["title"] == "Bilan disponible"

    suivi = admin_client.get("/notifications/%d/" % items[0]["id"])
    assert suivi.status_code == 302 and suivi.url == "/documents/1/"
    assert "bell-count" not in admin_client.get("/").content.decode()


def test_badge_messages_independant_de_la_cloche(db, admin_client, admin):
    from mail.models import Broadcast, Recipient

    diffusion = Broadcast.objects.create(subject="S", body="B", created_by=admin)
    Recipient.objects.create(broadcast=diffusion, user=admin)
    texte = admin_client.get("/").content.decode()
    assert "nav-badge" in texte        # compteur Messages (courriels non lus)
    assert "bell-count" not in texte   # aucune notification : la cloche est muette


def test_suppression_definitive_sans_traces(db, admin_client):
    user, _inv = comptes.create_member(email="suppr@example.test", first_name="S",
                                       last_name="T", role=make_role_non_admin())
    url = reverse("members:members_delete", args=[user.pk])
    admin_client.post(url, {"confirmation": "MAUVAIS"})
    assert User.objects.filter(pk=user.pk).exists()
    admin_client.post(url, {"confirmation": "SUPPRIMER"})
    assert not User.objects.filter(pk=user.pk).exists()
    assert AuditEntry.objects.filter(action="member.deleted").exists()


def test_suppression_de_soimeme_refusee(db, admin_client, admin):
    admin_client.post(reverse("members:members_delete", args=[admin.pk]),
                      {"confirmation": "SUPPRIMER"})
    assert User.objects.filter(pk=admin.pk).exists()


def make_role_non_admin():
    return Role.objects.create(name="Invité suppression", slug="invite-suppression", order=50)


def test_non_admin_ne_peut_pas_inviter_en_admin(db, member):
    from accounts.forms import InvitationForm

    admin_role = Role.objects.filter(is_administrator=True).first()
    if admin_role is None:
        admin_role = Role.objects.create(name="Administrateur ref", slug="admin-ref",
                                         is_administrator=True, order=1)
    form = InvitationForm(actor=member)
    assert admin_role.pk not in [r.pk for r in form.fields["role"].queryset]


def test_formulaire_membre_bloque_le_passage_en_admin(db, member):
    from accounts.forms import MemberForm

    admin_role = Role.objects.create(name="Administrateur cible", slug="admin-cible",
                                     is_administrator=True, order=2)
    form = MemberForm(data={"first_name": "L", "last_name": "M", "email": member.email,
                            "role": str(admin_role.pk)}, instance=member, actor=member)
    assert not form.is_valid()
    assert "role" in form.errors


def test_reinitialisation_site(db, admin_client, settings, tmp_path, _instance_json_en_memoire):
    media = tmp_path / "media"
    media.mkdir()
    (media / "logo.png").write_bytes(b"x")
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "archive.zip").write_bytes(b"x")
    settings.MEDIA_ROOT = media
    settings.BACKUP_DIR = backups
    _reauth_fraiche(admin_client)

    reponse = admin_client.post(reverse("settings:settings_reset"),
                                {"confirmation": "REINITIALISER"})
    assert reponse.status_code == 302 and reponse.url == "/installation/"
    assert User.objects.count() == 0
    assert not (media / "logo.png").exists()
    assert not (backups / "archive.zip").exists()
    assert _instance_json_en_memoire["meta"]["installed"] is False


def test_reinitialisation_sans_confirmation_refusee(db, admin_client, admin):
    _reauth_fraiche(admin_client)
    admin_client.post(reverse("settings:settings_reset"), {"confirmation": "non"})
    assert User.objects.filter(pk=admin.pk).exists()


def test_reinitialisation_vide_toutes_les_tables(db, admin_client, admin):
    """La réinitialisation ne laisse aucune table peuplée (docs, réglages compris)."""
    from core.models import Setting
    from documents.models import Category, Document

    _reauth_fraiche(admin_client)
    categorie = Category.objects.create(name="Docs")
    Document.objects.create(category=categorie, title="Vieux règlement")
    Setting.update_section("stockage", {"provider": "local"})
    reponse = admin_client.post(reverse("settings:settings_reset"),
                                {"confirmation": "REINITIALISER"})
    assert reponse.status_code == 302 and reponse.url == "/installation/"
    assert User.objects.count() == 0
    assert Document.objects.count() == 0 and Category.objects.count() == 0
    assert Role.objects.count() == 0
    assert Setting.objects.count() == 0
    trace = AuditEntry.objects.filter(message__contains="base vidée")
    assert trace.exists()


def test_reinitialisation_purge_le_bucket_tiers(db, admin_client, admin, monkeypatch):
    from core.models import Setting
    from tests.test_storage_docs import S3_CFG

    _reauth_fraiche(admin_client)
    Setting.update_section("stockage", S3_CFG)
    purges = []
    monkeypatch.setattr("core.storage.purge_all", lambda cfg: purges.append(cfg["bucket"]) or 2)
    reponse = admin_client.post(reverse("settings:settings_reset"),
                                {"confirmation": "REINITIALISER"})
    assert reponse.status_code == 302
    assert purges == ["mdl-test"]
    assert AuditEntry.objects.filter(message__contains="bucket purgé (2 objet(s))").exists()


def test_aucune_annee_ne_reapparait_dans_les_modules(db, admin_client):
    """Après une réinitialisation (base vide), aucun module ne recrée d'année seul."""
    from core.models import SchoolYear

    assert SchoolYear.objects.count() == 0
    for url in ("/tresorerie/", "/planning/", "/menage/campagnes/", "/menage/admin/suivi/"):
        page = admin_client.get(url)
        assert page.status_code == 200, url
        assert "Aucune année scolaire" in page.content.decode(), url
    assert SchoolYear.objects.count() == 0  # rien n'a été recréé à l'insu de l'association


def test_modules_fonctionnels_une_fois_l_annee_creee(db, admin_client):
    from tests.factories import make_year

    make_year()
    for url in ("/tresorerie/", "/planning/", "/menage/campagnes/"):
        page = admin_client.get(url)
        assert page.status_code == 200, url
        assert "Aucune année scolaire" not in page.content.decode(), url
