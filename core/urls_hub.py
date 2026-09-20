"""Routes de la centrale (/centrale/)."""
from django.urls import path

from core import views_hub

app_name = "centrale"

urlpatterns = [
    path("", views_hub.index, name="index"),
    path("ajouter/", views_hub.instance_add, name="instance_add"),
    path("<int:pk>/debrancher/", views_hub.instance_delete, name="instance_delete"),
]
