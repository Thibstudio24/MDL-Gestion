"""URL de la gestion des membres (/membres/)."""
from django.urls import path

from accounts import views_members as views

app_name = "members"

urlpatterns = [
    path("", views.list_view, name="members_list"),
    path("export/", views.export, name="members_export"),
    path("inviter/", views.invite, name="members_invite"),
    path("creer/", views.create, name="members_create"),
    path("<int:pk>/", views.detail, name="members_detail"),
    path("<int:pk>/modifier/", views.edit, name="members_edit"),
    path("<int:pk>/role/", views.change_role, name="members_change_role"),
    path("<int:pk>/mot-de-passe/", views.reset_password, name="members_reset_password"),
    path("<int:pk>/debloquer/", views.unlock, name="members_unlock"),
    path("<int:pk>/a2f/", views.disable_2fa, name="members_disable_2fa"),
    path("<int:pk>/statut/", views.toggle_status, name="members_toggle_status"),
    path("<int:pk>/anonymiser/", views.anonymize, name="members_anonymize"),
    path("<int:pk>/invitation/renvoyer/", views.invitation_resend, name="members_invitation_resend"),
    path("<int:pk>/invitation/revoquer/", views.invitation_revoke, name="members_invitation_revoke"),
]
