"""Vues de la messagerie interne descendante."""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from audit import services as audit
from core import permissions
from core.decorators import fine_required, module_required
from mail import services
from mail.models import Broadcast, Outbox, Recipient

MODULE = "mail"


class BroadcastForm(forms.ModelForm):
    class Meta:
        model = Broadcast
        fields = ["subject", "body", "kind", "audience", "roles", "requires_ack", "notify_email",
                  "scheduled_at"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10}),
                   "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
                   "roles": forms.CheckboxSelectMultiple()}


@module_required(MODULE)
def mail_inbox(request):
    """Ma boîte de réception : messages du bureau, non lus en tête."""
    items = services.inbox(request.user, unread_only=request.GET.get("nonlus") == "1")
    return render(request, "mail/inbox.html", {
        "page_title": _("Messages"), "items": items, "unread": services.unread_count(request.user),
        "only_unread": request.GET.get("nonlus") == "1",
        "can_edit": permissions.can_edit(request.user, MODULE),
    })


@module_required(MODULE)
def detail(request, pk):
    recipient = get_object_or_404(Recipient.objects.select_related("broadcast", "broadcast__created_by"),
                                  pk=pk, user=request.user)
    services.mark_read(recipient)
    if request.method == "POST" and recipient.broadcast.requires_ack:
        recipient.ack_at = timezone.now()
        recipient.save(update_fields=["ack_at"])
        messages.success(request, _("Accusé de lecture envoyé."))
        return redirect("mail:mail_inbox")
    return render(request, "mail/detail.html", {"page_title": recipient.broadcast.subject,
                                                "recipient": recipient, "broadcast": recipient.broadcast})


@module_required(MODULE, edit=True)
def admin_list(request):
    """Administration des diffusions."""
    broadcasts = Broadcast.objects.select_related("created_by")[:50]
    return render(request, "mail/admin.html", {
        "page_title": _("Diffusions"), "broadcasts": broadcasts, "stats": services.stats(),
        "form": BroadcastForm(),
    })


@module_required(MODULE, edit=True)
def create(request):
    form = BroadcastForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        broadcast = form.save(commit=False)
        broadcast.created_by = request.user
        broadcast.save()
        form.save_m2m()
        audit.log(request.user, "mail.broadcast_created", MODULE, broadcast, "Diffusion créée : %s" % broadcast)
        if request.POST.get("envoyer") == "1":
            count = services.send_broadcast(broadcast, request.user)
            messages.success(request, _("Diffusion envoyée à %(nombre)s membre(s).") % {"nombre": count})
        else:
            messages.success(request, _("Brouillon enregistré."))
        return redirect("mail:admin_detail", pk=broadcast.pk)
    return render(request, "mail/create.html", {"page_title": _("Nouvelle diffusion"), "form": form})


@module_required(MODULE, edit=True)
def admin_detail(request, pk):
    broadcast = get_object_or_404(Broadcast.objects.select_related("created_by"), pk=pk)
    recipients = broadcast.recipients.select_related("user")
    return render(request, "mail/broadcast_detail.html", {
        "page_title": broadcast.subject, "broadcast": broadcast, "recipients": recipients,
        "read": recipients.filter(read_at__isnull=False).count(), "total": recipients.count(),
        "audience": services.audience_members(broadcast) if broadcast.is_pending else [],
    })


@module_required(MODULE, edit=True)
@require_POST
def send_now(request, pk):
    broadcast = get_object_or_404(Broadcast, pk=pk)
    count = services.send_broadcast(broadcast, request.user)
    messages.success(request, _("Diffusion envoyée à %(nombre)s membre(s).") % {"nombre": count})
    return redirect("mail:admin_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def cancel(request, pk):
    broadcast = get_object_or_404(Broadcast, pk=pk)
    services.cancel_broadcast(broadcast, request.user)
    messages.success(request, _("Diffusion annulée."))
    return redirect("mail:admin_detail", pk=pk)


@module_required(MODULE, edit=True)
@require_POST
def schedule(request, pk):
    broadcast = get_object_or_404(Broadcast, pk=pk)
    raw = request.POST.get("scheduled_at", "")
    try:
        when = timezone.datetime.fromisoformat(raw)
        if timezone.is_naive(when):
            when = timezone.make_aware(when)
        services.schedule(broadcast, when, request.user)
    except (ValueError, TypeError):
        messages.error(request, _("Date programmée invalide."))
        return redirect("mail:admin_detail", pk=pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("mail:admin_detail", pk=pk)
    messages.success(request, _("Diffusion programmée pour le %(date)s.")
                     % {"date": timezone.localtime(when).strftime("%d/%m/%Y à %H:%M")})
    return redirect("mail:admin_detail", pk=pk)


@fine_required("mail.schedule", MODULE)
def outbox(request):
    """File d'attente SMTP : ce qui part, ce qui a échoué."""
    items = Outbox.objects.select_related("recipient_user")[:100]
    return render(request, "mail/outbox.html", {"page_title": _("File d'attente SMTP"), "items": items,
                                                "stats": services.stats()})


@fine_required("mail.schedule", MODULE)
@require_POST
def outbox_retry(request, pk):
    item = get_object_or_404(Outbox, pk=pk)
    item.status = "queued"
    item.attempts = 0
    item.error = ""
    item.save(update_fields=["status", "attempts", "error"])
    messages.success(request, _("Courriel remis en file."))
    return redirect("mail:outbox")


@fine_required("mail.schedule", MODULE)
@require_POST
def send_test(request):
    """Envoi d'un courriel de test pour valider le SMTP."""
    target = request.POST.get("email") or request.user.email
    try:
        services.send_test_email(target)
    except Exception as exc:  # noqa: BLE001 - message SMTP explicite pour l'admin
        messages.error(request, _("Échec de l'envoi : %(erreur)s") % {"erreur": exc})
        return redirect("settings:settings_smtp")
    audit.log(request.user, "mail.test_sent", MODULE, None, "Courriel de test envoyé à %s" % target)
    messages.success(request, _("Courriel de test envoyé à %(email)s.") % {"email": target})
    return redirect("settings:settings_smtp")
