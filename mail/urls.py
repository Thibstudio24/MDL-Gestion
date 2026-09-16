"""Routes de la messagerie interne."""
from django.urls import path

from mail import views

app_name = "mail"

urlpatterns = [
    path("", views.mail_inbox, name="mail_inbox"),
    path("<int:pk>/", views.detail, name="detail"),
    path("admin/", views.admin_list, name="admin_list"),
    path("admin/creer/", views.create, name="create"),
    path("admin/<int:pk>/", views.admin_detail, name="admin_detail"),
    path("admin/<int:pk>/envoyer/", views.send_now, name="send_now"),
    path("admin/<int:pk>/annuler/", views.cancel, name="cancel"),
    path("admin/<int:pk>/programmer/", views.schedule, name="schedule"),
    path("admin/file/", views.outbox, name="outbox"),
    path("admin/file/<int:pk>/relancer/", views.outbox_retry, name="outbox_retry"),
    path("admin/test/", views.send_test, name="send_test"),
]
