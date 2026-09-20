"""Routes de la centrale (/centrale/)."""
from django.urls import path

from core import views_hub

app_name = "centrale"

urlpatterns = [
    path("", views_hub.index, name="index"),
    path("ajouter/", views_hub.instance_add, name="instance_add"),
    path("<int:pk>/debrancher/", views_hub.instance_delete, name="instance_delete"),
    path("<int:pk>/action/", views_hub.instance_action, name="instance_action"),
    path("<int:pk>/cle-deblocage/", views_hub.instance_cle, name="instance_cle"),
]
