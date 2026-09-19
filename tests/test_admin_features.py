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
