"""URL des documents (/documents/)."""
from django.urls import path

from documents import views

app_name = "documents"

urlpatterns = [
    path("", views.list_view, name="documents_list"),
    path("deposer/", views.upload, name="upload"),
    path("corbeille/", views.trash, name="trash"),
    path("corbeille/vider/", views.empty_trash, name="empty_trash"),
    path("categories/", views.categories, name="categories"),
    path("categories/<int:pk>/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/verrou/", views.category_toggle_lock, name="category_toggle_lock"),
    path("dossiers/creer/", views.folder_create, name="folder_create"),
    path("dossiers/<int:pk>/supprimer/", views.folder_delete, name="folder_delete"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/modifier/", views.edit, name="edit"),
    path("<int:pk>/remplacer/", views.replace, name="replace"),
    path("<int:pk>/telecharger/", views.download, name="download"),
    path("<int:pk>/telecharger/<int:version_id>/", views.download, name="download_version"),
    path("<int:pk>/apercu/", views.preview, name="preview"),
    path("<int:pk>/versions/<int:version_id>/restaurer/", views.restore_version, name="restore_version"),
    path("<int:pk>/supprimer/", views.soft_delete, name="soft_delete"),
    path("<int:pk>/restaurer/", views.restore_document, name="restore_document"),
    path("<int:pk>/forcer/", views.force_locked, name="force_locked"),
]
