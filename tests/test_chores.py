"""Planning de ménage : attribution, preuves, validation, renvoi motivé, rappels."""
from __future__ import annotations

import pytest

from chores import services
from chores.models import Assignment, Response


class TestAttribution:
    def test_cinq_taches_types_attribuees(self, chore_campaign, member, admin):
        assert services.generate_assignments(chore_campaign, admin) == 5
        assert Assignment.objects.filter(campaign=chore_campaign).count() == 5

    def test_les_volontaires_sont_privilegies(self, chore_campaign, member, admin):
        Response.objects.create(campaign=chore_campaign, member=member, choice="accept")
        services.generate_assignments(chore_campaign, admin)
        assert Assignment.objects.filter(campaign=chore_campaign, member=member).count() == 5

    def test_un_membre_qui_decline_nest_pas_attribue(self, chore_campaign, member, admin):
        from tests.factories import make_user

        role = member.role
        autre = make_user("autre@example.test", role=role)
        Response.objects.create(campaign=chore_campaign, member=autre, choice="decline")
        Response.objects.create(campaign=chore_campaign, member=member, choice="accept")
        services.generate_assignments(chore_campaign, admin)
        assert Assignment.objects.filter(campaign=chore_campaign, member=autre).count() == 0

    def test_publication_attribue_et_notifie(self, chore_campaign, member, admin):
        from notifications.models import Notification

        services.publish(chore_campaign, admin)
        assert chore_campaign.published is True
        assert Notification.objects.filter(user=member, kind="menage_assigned").exists()


class TestSuivi:
    @pytest.fixture
    def task(self, chore_campaign, member, admin):
        from chores.models import Response

        Response.objects.create(campaign=chore_campaign, member=member, choice="accept")
        services.generate_assignments(chore_campaign, admin)
        return Assignment.objects.filter(campaign=chore_campaign, member=member).first()

    def test_declarer_fait(self, task, member):
        services.mark_done(member, task, note="fait ce matin")
        task.refresh_from_db()
        assert task.status == "done"
        assert task.done_at is not None

    def test_un_autre_membre_ne_peut_pas_valider_sa_tache(self, task, db):
        from tests.factories import make_user

        autre = make_user("intrus@example.test", role=task.member.role)
        with pytest.raises(ValueError):
            services.mark_done(autre, task)

    def test_validation(self, task, member, admin):
        services.mark_done(member, task)
        services.validate(task, admin)
        task.refresh_from_db()
        assert task.status == "validated"
        assert task.validated_by_id == admin.pk

    def test_renvoi_sans_motif_refuse(self, task, member, admin):
        services.mark_done(member, task)
        with pytest.raises(ValueError):
            services.request_redo(task, admin, "")

    def test_renvoi_motive_remet_a_faire(self, task, member, admin):
        from notifications.models import Notification

        services.mark_done(member, task)
        services.request_redo(task, admin, "photo floue")
        task.refresh_from_db()
        assert task.status == "redo"
        assert "photo floue" in task.note
        assert Notification.objects.filter(user=member, kind="menage_redo").exists()

    def test_progression(self, chore_campaign, member, admin, task):
        services.mark_done(member, task)
        services.validate(task, admin)
        progress = services.campaign_progress(chore_campaign)
        assert progress["total"] == 5
        assert progress["done"] == 1
        assert progress["pct"] == 20


class TestRappelsEtPurges:
    def test_rappel_aux_taches_en_attente(self, chore_campaign, member, admin):
        from notifications.models import Notification

        services.generate_assignments(chore_campaign, admin)
        Notification.objects.all().delete()
        assert services.send_reminders(chore_campaign) == 5

    def test_cloture_des_semaines_passees(self, chore_campaign):
        from django.utils import timezone

        chore_campaign.published = True
        chore_campaign.end_date = timezone.localdate() - timezone.timedelta(days=1)
        chore_campaign.save()
        assert services.close_expired_campaigns() == 1

    def test_purge_des_photos_a_sec(self, db):
        assert services.purge_photos(180, dry_run=True) == 0


class TestPages:
    def test_page_membre(self, member_client):
        assert member_client.get("/menage/").status_code == 200

    def test_suivi_administrateur(self, admin_client):
        assert admin_client.get("/menage/admin/suivi/").status_code == 200

    def test_campagnes(self, admin_client):
        assert admin_client.get("/menage/campagnes/").status_code == 200
