"""Routes du planning de ménage."""
from django.urls import path

from chores import views

app_name = "chores"

urlpatterns = [
    path("", views.chores_list, name="chores_list"),
    path("repondre/", views.respond, name="respond"),
    path("taches/<int:pk>/faire/", views.mark_done, name="mark_done"),
    path("admin/suivi/", views.admin_tracking, name="admin_tracking"),
    path("admin/valider/<int:pk>/", views.validate, name="validate"),
    path("admin/refaire/<int:pk>/", views.request_redo, name="request_redo"),
    path("campagnes/", views.campaigns, name="campaigns"),
    path("campagnes/creer/", views.campaign_create, name="campaign_create"),
    path("campagnes/<int:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campagnes/<int:pk>/publier/", views.publish, name="publish"),
    path("campagnes/<int:pk>/supprimer/", views.delete, name="campaign_delete"),
    path("campagnes/<int:pk>/cloturer/", views.close, name="close"),
    path("campagnes/<int:pk>/rappel/", views.remind, name="remind"),
    path("campagnes/<int:pk>/tache/", views.task_add, name="task_add"),
    path("tache/<int:pk>/retirer/", views.task_delete, name="task_delete"),
    path("taches/<int:pk>/rearranger/", views.reassign, name="reassign"),
    path("preferences/", views.save_prefs, name="save_prefs"),
]
