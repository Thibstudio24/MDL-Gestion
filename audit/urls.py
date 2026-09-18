"""URL du journal d'audit (/audit/)."""
from django.urls import path

from audit import views

app_name = "audit"

urlpatterns = [
    path("", views.list_view, name="audit_list"),
    path("export/", views.export, name="audit_export"),
    path("vider/", views.clear, name="audit_clear"),
    path("<int:pk>/", views.detail, name="audit_detail"),
]
