"""URL d'authentification (/connexion/, /inviter/, /mot-de-passe/)."""
from django.urls import path

from accounts import views_auth as views

app_name = "auth"

urlpatterns = [
    path("", views.login_view, name="login"),
    path("a2f/", views.second_factor, name="twofa"),
    path("a2f/configurer/", views.twofa_setup, name="twofa_setup"),
    path("a2f/desactiver/", views.twofa_disable, name="twofa_disable"),
    path("bienvenue/", views.welcome, name="welcome"),
]
