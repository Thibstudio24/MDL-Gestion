"""URL de la page Settings du membre (/parametres/)."""
from django.urls import path

from accounts import views_settings as views

app_name = "settings_me"

urlpatterns = [
    path("", views.profile, name="settings_profile"),
    path("apparence/", views.appearance, name="settings_appearance"),
    path("notifications/", views.notifications_me, name="settings_notifications_me"),
    path("securite/", views.security, name="settings_security"),
    path("securite/sessions/<int:pk>/revoquer/", views.session_revoke, name="settings_session_revoke"),
    path("securite/sessions/toutes/", views.sessions_revoke_all, name="settings_sessions_revoke_all"),
    path("application/", views.application, name="settings_application"),
    path("donnees/", views.data, name="settings_data"),
    path("donnees/export/", views.data_export, name="settings_data_export"),
    path("donnees/anonymiser/", views.anonymize, name="settings_anonymize"),
    path("charte/", views.charte, name="settings_charte"),
    path("charte/<slug:slug>/accepter/", views.charte_accept, name="settings_charte_accept"),
    path("prefs/", views.prefs, name="settings_prefs"),
]
