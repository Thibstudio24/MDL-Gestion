"""URL de l'aide-intervention (/aide-intervention/)."""
from django.urls import path

from core import views_devhub as views

app_name = "devhub"

urlpatterns = [
    path("", views.index, name="devhub_index"),
    path("appliquer/", views.apply_token, name="devhub_apply"),
]
