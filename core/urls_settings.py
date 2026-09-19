"""URL des Réglages de l'association (/reglages/)."""
from django.urls import path

from core import views_settings as views

app_name = "settings"

urlpatterns = [
    path("", views.brand, name="settings_brand"),
    path("annees/", views.years, name="settings_years"),
    path("annees/<int:pk>/action/", views.year_action, name="settings_year_action"),
    path("annees/<int:pk>/fermetures/", views.year_closure_add, name="settings_year_closure_add"),
    path("annees/fermetures/<int:pk>/supprimer/", views.year_closure_delete, name="settings_year_closure_delete"),
    path("quotas/", views.quotas, name="settings_quotas"),
    path("securite/", views.security_settings, name="settings_security"),
    path("notifications/", views.notifications, name="settings_notifications"),
    path("smtp/", views.smtp, name="settings_smtp"),
    path("smtp/test/", views.smtp_test, name="settings_smtp_test"),
    path("smtp/vider/", views.smtp_drain, name="settings_smtp_drain"),
    path("stockage/", views.storage, name="settings_storage"),
    path("stockage/test/", views.storage_test, name="settings_storage_test"),
    path("reinitialiser/", views.reset_site, name="settings_reset"),
    path("pwa/", views.pwa, name="settings_pwa"),
    path("pwa/cles/", views.pwa_generate_keys, name="settings_pwa_keys"),
    path("bilan/", views.bilan_settings, name="settings_bilan"),
    path("sauvegarde/", views.backup_view, name="settings_backup"),
    path("sauvegarde/creer/", views.backup_create, name="settings_backup_create"),
    path("sauvegarde/supprimer/", views.backup_delete, name="settings_backup_delete"),
    path("sauvegarde/restaurer/", views.backup_restore, name="settings_backup_restore"),
    path("interventions/", views.interventions, name="settings_interventions"),
    path("interventions/<int:pk>/", views.intervention_action, name="settings_intervention_action"),
    path("maintenance/", views.maintenance, name="settings_maintenance"),
    path("mise-a-jour/", views.update, name="settings_update"),
    path("telemetrie/", views.telemetry, name="settings_telemetry"),
    path("textes/", views.texts, name="settings_texts"),
    path("textes/<slug:slug>/", views.text_edit, name="settings_text"),
]
