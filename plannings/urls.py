"""Routes du planning de la salle."""
from django.urls import path

from plannings import views

app_name = "plannings"

urlpatterns = [
    path("", views.planning_list, name="planning_list"),
    path("mes-disponibilites/", views.my_availabilities, name="mine"),
    path("creer/", views.campaign_create, name="campaign_create"),
    path("<int:pk>/", views.campaign_detail, name="campaign_detail"),
    path("<int:pk>/couverture/", views.coverage, name="coverage"),
    path("<int:pk>/publier/", views.publish, name="publish"),
    path("<int:pk>/cloturer/", views.close, name="close"),
    path("<int:pk>/rappel/", views.remind, name="remind"),
    path("<int:pk>/supprimer/", views.delete, name="campaign_delete"),
    path("<int:pk>/creneaux/ajouter/", views.slot_add, name="slot_add"),
    path("<int:pk>/export/", views.export, name="export"),
    path("creneaux/<int:pk>/supprimer/", views.slot_delete, name="slot_delete"),
    path("reponse/", views.save_availability, name="save_availability"),
]
