"""Messagerie descendante : file SMTP, diffusions, accusés, purges."""
from __future__ import annotations

import pytest

from mail import services
from mail.models import Broadcast, Outbox, Recipient


@pytest.fixture
def broadcast(db, admin):
    return Broadcast.objects.create(subject="Rentrée", body="**Bonjour** à tous", kind="important",
                                    audience="all", created_by=admin)


class TestFileSmtp:
    def test_mise_en_file_sans_envoi_immediat(self, db, member):
        item = services.queue_email(to_email=member.email, recipient_user=member,
                                    subject="Test", text_body="corps", kind="info")
        assert item.status == "queued"
        assert item.sent_at is None

    def test_smtp_desactive_marque_les_courriels_ignores(self, db, member, settings):
        settings.MAIL_ENABLED = False
        services.queue_email(to_email=member.email, subject="Test", text_body="corps")
        report = services.drain_outbox()
        assert report["ignores"] == 1
        assert Outbox.objects.get().status == "skipped"

    def test_les_courriels_urgents_passent_en_premier(self, db, member, settings):
        settings.MAIL_ENABLED = False
        services.queue_email(to_email=member.email, subject="Normal", text_body="x")
        services.queue_email(to_email=member.email, subject="Urgent", text_body="x", urgent=True)
        first = Outbox.objects.order_by("-urgent", "queued_at").first()
        assert first.subject == "Urgent"


class TestDiffusions:
    def test_envoi_cree_les_destinataires(self, broadcast, admin, member):
        count = services.send_broadcast(broadcast, admin)
        assert count >= 1
        assert Recipient.objects.filter(broadcast=broadcast, user=member).exists()

    def test_envoi_notifie_les_membres(self, broadcast, admin, member):
        from notifications.models import Notification

        services.send_broadcast(broadcast, admin)
        assert Notification.objects.filter(user=member, kind="mail").exists()

    def test_audience_restreinte_au_bureau(self, broadcast, admin, member, db):
        broadcast.audience = "board"
        broadcast.save(update_fields=["audience"])
        assert member not in services.audience_members(broadcast)

    def test_programmation_dans_le_passe_refusee(self, broadcast, admin):
        from django.utils import timezone

        with pytest.raises(ValueError):
            services.schedule(broadcast, timezone.now() - timezone.timedelta(hours=1), admin)

    def test_diffusion_programmee_part_a_lheure(self, broadcast, admin, member):
        from django.utils import timezone

        broadcast.status = "scheduled"
        broadcast.scheduled_at = timezone.now() - timezone.timedelta(minutes=1)
        broadcast.save(update_fields=["status", "scheduled_at"])
        assert services.send_scheduled() == 1
        broadcast.refresh_from_db()
        assert broadcast.status == "sent"

    def test_une_diffusion_programmee_plus_tard_ne_part_pas(self, broadcast, admin):
        from django.utils import timezone

        services.schedule(broadcast, timezone.now() + timezone.timedelta(hours=2), admin)
        assert services.send_scheduled() == 0
        broadcast.refresh_from_db()
        assert broadcast.status == "scheduled"

    def test_annulation(self, broadcast, admin):
        services.cancel_broadcast(broadcast, admin)
        assert broadcast.status == "cancelled"


class TestLecture:
    def test_marquer_comme_lu(self, broadcast, admin, member):
        services.send_broadcast(broadcast, admin)
        recipient = Recipient.objects.get(user=member)
        services.mark_read(recipient)
        assert recipient.read_at is not None

    def test_compteur_de_non_lus(self, broadcast, admin, member):
        services.send_broadcast(broadcast, admin)
        assert services.unread_count(member) >= 1
        services.mark_read(Recipient.objects.get(user=member))
        assert services.unread_count(member) == 0

    def test_purge_des_messages_lus(self, broadcast, admin, member):
        from django.utils import timezone

        services.send_broadcast(broadcast, admin)
        recipient = Recipient.objects.get(user=member)
        services.mark_read(recipient)
        Recipient.objects.filter(pk=recipient.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=400))
        assert services.purge_read_emails(days=180) >= 1


class TestPages:
    def test_boite_de_reception(self, member_client):
        assert member_client.get("/messages/").status_code == 200

    def test_administration(self, admin_client):
        assert admin_client.get("/messages/admin/").status_code == 200

    def test_file_smtp(self, admin_client):
        assert admin_client.get("/messages/admin/file/").status_code == 200

    def test_un_lecteur_ne_voit_que_sa_boite(self, db, client):
        from tests.factories import make_role, make_user

        role = make_role("Lecteur messages", levels={"dashboard": 1, "mail": 1})
        user = make_user("lecteur-mail@example.test", role=role)
        client.force_login(user)
        assert client.get("/messages/").status_code == 200
        assert client.get("/messages/admin/").status_code == 403
