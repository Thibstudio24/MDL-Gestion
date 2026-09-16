"""Chaîne de montage des URL de MDL Gestion."""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from accounts import views_auth as accounts_views
from core import views as core_views

urlpatterns = [
    path("", core_views.dashboard, name="dashboard"),
    path("connexion/", include("accounts.urls_auth")),
    path("deconnexion/", accounts_views.logout_view, name="logout"),
    path("reauthentifier/", accounts_views.reauth, name="reauth"),
    path("mot-de-passe/oubli/", accounts_views.password_reset_request, name="password_reset"),
    path("reinitialiser/<str:token>/", accounts_views.password_reset_confirm, name="password_reset_confirm"),
    path("inviter/<uuid:token>/", accounts_views.invitation_accept, name="invitation_accept"),
    path("inviter/<str:code>/", accounts_views.invitation_code, name="invitation_code"),
    path("parametres/", include("accounts.urls_settings")),
    path("membres/", include("accounts.urls_members")),
    path("roles/", include("accounts.urls_roles")),
    path("documents/", include("documents.urls")),
    path("tresorerie/", include("finance.urls")),
    path("planning/", include("plannings.urls")),
    path("menage/", include("chores.urls")),
    path("messages/", include("mail.urls")),
    path("notifications/", include("notifications.urls")),
    path("reglages/", include("core.urls_settings")),
    path("audit/", include("audit.urls")),
    path("aide/", include("core.urls_help")),
    path("installation/", include("installer.urls")),
    path("aide-intervention/", include("core.urls_devhub")),
    # Fichiers de service
    path("theme.css", core_views.theme_css, name="theme_css"),
    path("manifest.webmanifest", core_views.manifest, name="manifest"),
    path("service-worker.js", core_views.service_worker, name="service_worker"),
    path("hors-ligne/", core_views.offline, name="offline"),
    path("sante/", core_views.health, name="health"),
    path("favicon.ico", core_views.favicon, name="favicon"),
    path("robots.txt", core_views.robots, name="robots"),
    # Médias privés : servis par une vue qui vérifie les droits (jamais public en prod)
    path("fichiers/<path:relpath>", core_views.serve_media, name="serve_media"),
]

handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
handler500 = "core.views.error_500"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
