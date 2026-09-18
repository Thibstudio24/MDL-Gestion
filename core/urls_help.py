"""URL du mode d'emploi (/aide/)."""
from django.urls import path

from core import views_help as views

app_name = "help"

urlpatterns = [
    path("", views.index, name="help_index"),
    path("faq/", views.faq, name="help_faq"),
    path("glossaire/", views.glossary, name="help_glossary"),
    path("check-list/", views.checklist, name="help_checklist"),
    path("<str:sid>/", views.section, name="help_section"),
]
