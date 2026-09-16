"""URL des notifications (/notifications/)."""
from django.urls import path

from notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("panneau/", views.panel, name="panel"),
    path("<int:pk>/", views.detail, name="detail"),
    path("marquer-lu/", views.mark_read, name="mark_read"),
    path("tout-marquer-lu/", views.mark_all, name="mark_all"),
    path("vapid/", views.vapid, name="vapid"),
    path("push/abonner/", views.subscribe_device, name="subscribe"),
    path("desabonner/", views.unsubscribe_device, name="unsubscribe"),
    path("test/", views.test_push, name="test"),
]
