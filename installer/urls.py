"""Routes de l'assistant d'installation."""
from django.urls import path

from installer import views

app_name = "installer"

urlpatterns = [
    path("", views.welcome, name="welcome"),
    path("identite/", views.identity, name="identity"),
    path("administrateur/", views.administrator, name="admin"),
    path("termine/", views.done, name="done"),
    path("referentiels/", views.seed_defaults, name="seed_defaults"),
    path("stockage/", views.storage_choice, name="storage"),
]
