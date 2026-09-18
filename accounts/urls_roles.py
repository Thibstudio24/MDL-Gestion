"""URL des rôles & droits (/roles/)."""
from django.urls import path

from accounts import views_roles as views

app_name = "roles"

urlpatterns = [
    path("", views.list_view, name="roles_list"),
    path("creer/", views.create, name="roles_create"),
    path("export/", views.export_rights, name="roles_export"),
    path("import/", views.import_rights, name="roles_import"),
    path("<int:pk>/", views.detail, name="roles_detail"),
    path("<int:pk>/dupliquer/", views.duplicate, name="roles_duplicate"),
    path("<int:pk>/supprimer/", views.delete, name="roles_delete"),
    path("<int:pk>/niveau/", views.quick_level, name="roles_quick_level"),
]
