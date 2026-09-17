

def test_boutons_de_suppression_partout(admin_client, campaign, chore_campaign, tmp_path, settings):
    """Ce qui peut être créé peut être supprimé : sauvegarde, campagne de
    planning, campagne de ménage. Les rôles et les membres avaient déjà leurs
    actions (« Supprimer », « Désactiver », « Anonymiser »)."""
    from django.urls import reverse

    from chores.models import Campaign as ChoreCampaign
    from plannings.models import Campaign as PlanCampaign

    # Campagne de planning de salle
    page = admin_client.get(reverse("plannings:campaign_detail", args=[campaign.pk]))
    assert "Supprimer" in page.content.decode()
    response = admin_client.post(reverse("plannings:campaign_delete", args=[campaign.pk]), follow=True)
    assert response.status_code == 200
    assert PlanCampaign.objects.count() == 0

    # Campagne de ménage
    page = admin_client.get(reverse("chores:campaign_detail", args=[chore_campaign.pk]))
    assert "Supprimer" in page.content.decode()
    response = admin_client.post(reverse("chores:campaign_delete", args=[chore_campaign.pk]), follow=True)
    assert response.status_code == 200
    assert ChoreCampaign.objects.count() == 0

    # Sauvegarde
    dossier = tmp_path / "backups"
    dossier.mkdir()
    (dossier / "mdl-2026.zip").write_bytes(b"PK" + b"0" * 50)
    settings.BASE_DIR = tmp_path
    page = admin_client.get(reverse("settings:settings_backup"))
    assert "Supprimer" in page.content.decode()
    response = admin_client.post(
        reverse("settings:settings_backup_delete"), {"archive": "mdl-2026.zip"}, follow=True)
    assert response.status_code == 200
    assert not (dossier / "mdl-2026.zip").exists()


def test_suppression_de_sauvegarde_refuse_la_traversee(admin_client, tmp_path, settings):
    """Le nom vient du formulaire : il ne doit pas permettre de sortir du dossier."""
    from django.urls import reverse

    dossier = tmp_path / "backups"
    dossier.mkdir()
    hors_cible = tmp_path / "secret.zip"
    hors_cible.write_bytes(b"PK")
    settings.BASE_DIR = tmp_path

    admin_client.post(reverse("settings:settings_backup_delete"),
                      {"archive": "../secret.zip"}, follow=True)
    assert hors_cible.exists(), "un fichier hors du dossier de sauvegardes a été supprimé"
