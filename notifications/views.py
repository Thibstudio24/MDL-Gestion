"""Notifications in-app et abonnements push."""
from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from notifications import push, services
from notifications.models import Notification


@login_required
def inbox(request):
    queryset = request.user.notifications.select_related("user")
    tab = request.GET.get("onglet", "non-lus")
    if tab == "lus":
        queryset = queryset.filter(read_at__isnull=False)
    elif tab == "tous":
        pass
    else:
        queryset = queryset.filter(read_at__isnull=True)
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(request, "notifications/inbox.html", {
        "page_obj": page, "tab": tab, "unread": services.unread_count(request.user),
        "page_title": "Notifications",
    })


@login_required
def panel(request):
    """Panneau latéral de la cloche (fragment JSON)."""
    items = request.user.notifications.filter(read_at__isnull=True)[:12]
    return JsonResponse({
        "unread": services.unread_count(request.user),
        "items": [{"id": item.pk, "title": item.title, "body": item.body[:160], "url": item.url,
                   "level": item.level, "at": item.created_at.strftime("%d/%m %H:%M")} for item in items],
    })


@login_required
@require_POST
def mark_read(request):
    identifier = request.POST.get("id")
    count = services.mark_read(request.user, int(identifier) if identifier else None)
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True, "count": count, "unread": services.unread_count(request.user)})
    messages.success(request, _("%(n)s notification(s) marquée(s) comme lue(s).") % {"n": count})
    return redirect("notifications:inbox")


@login_required
@require_POST
def mark_all(request):
    count = services.mark_read(request.user)
    messages.success(request, _("Tout est marqué comme lu (%(n)s).") % {"n": count})
    return redirect("notifications:inbox")


@login_required
def vapid(request):
    """Clé publique VAPID pour l'abonnement côté navigateur."""
    return JsonResponse({"key": push.public_key(), "enabled": bool(push.public_key())})


@login_required
@require_POST
def subscribe_device(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "payload invalide"}, status=400)
    device = push.subscribe(request.user, payload, label=request.POST.get("label", ""),
                            user_agent=request.headers.get("user-agent", ""))
    if device is None:
        return JsonResponse({"ok": False, "error": "endpoint manquant"}, status=400)
    request.user.set_pref("push_enabled", True)
    return JsonResponse({"ok": True, "id": device.pk})


@login_required
@require_POST
def unsubscribe_device(request):
    endpoint = request.POST.get("endpoint", "")
    count = push.unsubscribe(request.user, endpoint)
    messages.success(request, _("Appareil retiré (%(n)s).") % {"n": count})
    return redirect("settings_me:settings_notifications_me")


@login_required
@require_POST
def test_push(request):
    ok = push.send_push(request.user, "Notification de test",
                        "Si vous voyez ce message, le push fonctionne sur au moins un appareil.", "/")
    if ok:
        messages.success(request, _("Notification de test envoyée."))
    else:
        messages.warning(request, _("Aucun appareil n'a reçu la notification (abonnement ou clés VAPID à vérifier)."))
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": ok})
    return redirect("settings_me:settings_notifications_me")


@login_required
def detail(request, pk: int):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.read_at:
        services.mark_read(request.user, notification.pk)
    if notification.url:
        return redirect(notification.url)
    return redirect("notifications:inbox")
