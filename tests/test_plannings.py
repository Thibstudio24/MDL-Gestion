"""Planning de la salle : campagnes, créneaux, réponses, couverture, clôture."""
from __future__ import annotations

import pytest
from django.utils import timezone

from plannings import services
from plannings.models import Availability, Slot


@pytest.fixture
def slots(campaign):
    from plannings.views import _default_slots

    _default_slots(campaign)
    return list(Slot.objects.filter(campaign=campaign))


class TestCampagne:
    def test_campagne_ouverte_aux_dates_prevues(self, campaign):
        assert campaign.is_open is True

    def test_campagne_non_publiee_nest_pas_ouverte(self, campaign):
        campaign.published = False
        campaign.save(update_fields=["published"])
        assert campaign.is_open is False

    def test_campagne_cloturee_refuse_les_reponses(self, campaign, member):
        campaign.published = True
        campaign.closed = True
        campaign.save()
        with pytest.raises(ValueError):
            services.save_availability(member, campaign, Slot.objects.create(campaign=campaign, weekday=1,
                                                                             start_time="12:00",
                                                                             end_time="13:00"), "yes")

    def test_statistiques_sans_reponse(self, campaign, slots):
        stats = services.campaign_stats(campaign)
        assert stats["answered"] == 0
        assert stats["reponse_pct"] == 0
        assert stats["gaps"] == len(slots)

    def test_reponse_fait_monter_le_taux(self, campaign, slots, member):
        services.save_availability(member, campaign, slots[0], "yes")
        stats = services.campaign_stats(campaign)
        assert stats["answered"] == 1
        assert stats["reponse_pct"] > 0

    def test_un_creneau_couvert_nest_plus_en_manque(self, campaign, slots, member):
        slot = slots[0]
        slot.capacity = 1
        slot.save(update_fields=["capacity"])
        services.save_availability(member, campaign, slot, "yes")
        stats = services.campaign_stats(campaign)
        assert stats["coverage"][slot.pk]["covered"] is True

    def test_si_besoin_ne_compte_pas_comme_gerant(self, campaign, slots, member):
        slot = slots[0]
        services.save_availability(member, campaign, slot, "maybe")
        stats = services.campaign_stats(campaign)
        assert stats["coverage"][slot.pk]["managers"] == 0

    def test_grille_par_jour(self, campaign, slots):
        days = services.by_day(campaign)
        assert len(days) == len(slots)
        assert {row["label"] for row in days}


class TestReponses:
    def test_une_seule_reponse_par_membre_et_creneau(self, campaign, slots, member):
        services.save_availability(member, campaign, slots[0], "yes")
        services.save_availability(member, campaign, slots[0], "no")
        assert Availability.objects.filter(campaign=campaign, member=member, slot=slots[0]).count() == 1
        assert Availability.objects.get(slot=slots[0], member=member).choice == "no"

    def test_note_conservee(self, campaign, slots, member):
        services.save_availability(member, campaign, slots[0], "yes", "jusqu'à 12 h 30")
        assert Availability.objects.get(slot=slots[0]).note == "jusqu'à 12 h 30"


class TestPublication:
    def test_publication_notifie_les_membres(self, year, admin, member):
        from notifications.models import Notification
        from tests.factories import make_campaign

        draft = make_campaign(year, label="Brouillon")
        services.publish(draft, admin)
        draft.refresh_from_db()
        assert draft.published is True
        assert Notification.objects.filter(user=member, kind="planning_published").exists()

    def test_publication_deja_faite_ne_renotifie_pas(self, campaign, admin, member):
        from notifications.models import Notification

        services.publish(campaign, admin)
        assert not Notification.objects.filter(user=member, kind="planning_published").exists()

    def test_rappel_aux_seuls_non_repondants(self, campaign, slots, admin, member):
        services.publish(campaign, admin)
        services.save_availability(member, campaign, slots[0], "yes")
        from notifications.models import Notification

        Notification.objects.all().delete()
        assert services.send_reminder(campaign, admin) >= 1
        assert not Notification.objects.filter(user=member, kind="campaign_deadline").exists()

    def test_cloture_automatique_des_campagnes_expirees(self, campaign, slots):
        campaign.published = True
        campaign.end_date = timezone.localdate() - timezone.timedelta(days=1)
        campaign.save()
        assert services.close_expired_campaigns() == 1
        campaign.refresh_from_db()
        assert campaign.closed is True


class TestPages:
    def test_liste_des_campagnes(self, admin_client):
        assert admin_client.get("/planning/").status_code == 200

    def test_grille_dune_campagne(self, admin_client, campaign, slots):
        assert admin_client.get("/planning/%d/" % campaign.pk).status_code == 200

    def test_couverture(self, admin_client, campaign, slots):
        assert admin_client.get("/planning/%d/couverture/" % campaign.pk).status_code == 200

    def test_mes_disponibilites(self, member_client):
        assert member_client.get("/planning/mes-disponibilites/").status_code == 200

    def test_export_csv(self, admin_client, campaign, slots):
        response = admin_client.get("/planning/%d/export/" % campaign.pk)
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
