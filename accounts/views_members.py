"""Gestion des membres (/membres/) : liste, fiche, invitations, actions sensibles."""
from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts import services
from accounts.forms import InvitationForm, MemberForm
from accounts.models import Invitation, Role, RoleMembership, User
from audit.services import log
from core import permissions
from core.decorators import administrator_required, module_required, reauth_required
from core.export import csv_response
from core.models import Setting


def _filters(request):
    queryset = User.objects.select_related("role").annotate(invites=Count("invitation"))
    params = {}
    if request.GET.get("q"):
        params["q"] = request.GET["q"].strip()
        queryset = queryset.filter(
            Q(first_name__icontains=params["q"]) | Q(last_name__icontains=params["q"])
            | Q(email__icontains=params["q"]) | Q(display_function__icontains=params["q"])
        )
    if request.GET.get("role"):
        params["role"] = request.GET["role"]
        queryset = queryset.filter(role_id=params["role"])
    if request.GET.get("status"):
        params["status"] = request.GET["status"]
        queryset = queryset.filter(status=params["status"])
    if request.GET.get("sans_a2f") == "1":
        params["sans_a2f"] = "1"
        queryset = queryset.filter(status="active", totp_enabled=False)
    if request.GET.get("inactifs") == "1":
        params["inactifs"] = "1"
        queryset = queryset.filter(Q(last_seen__lt=timezone.now() - timedelta(days=365)) | Q(last_seen__isnull=True))
    return queryset.order_by("last_name", "first_name"), params


@module_required("members")
def list_view(request):
    queryset, params = _filters(request)
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    invitations = Invitation.objects.filter(accepted_at__isnull=True).select_related("user")[:10]
    grantables = Role.objects.all()
    if not permissions.is_administrator(request.user):
        grantables = grantables.filter(is_administrator=False)
    return render(request, "accounts/member_list.html", {
        "page_obj": page, "params": params, "invitations": invitations,
        "roles": Role.objects.all(), "roles_invite": grantables,
        "can_edit": permissions.can_edit(request.user, "members"),
        "can_invite": permissions.fine(request.user, "members.invite"),
        "page_title": "Membres & invitations",
    })


@module_required("members", edit=True)
@require_POST
def invite(request):
    if not permissions.fine(request.user, "members.invite"):
        messages.error(request, _("Votre rôle ne permet pas d'inviter un membre."))
        return HttpResponseForbidden()
    form = InvitationForm(request.POST, actor=request.user)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, "%s : %s" % (form.fields[field].label if field in form.fields else field, error))
        return redirect("members:members_list")
    data = form.cleaned_data
    if not _can_grant(request.user, data["role"]):
        messages.error(request, _("Vous ne pouvez pas attribuer un rôle Administrateur."))
        return redirect("members:members_list")
    user, invitation = services.create_member(
        email=data["email"], first_name=data["first_name"], last_name=data["last_name"],
        role=data["role"], display_function=data["display_function"], days=data["days"],
        message=data["message"], actor=request.user, boarder=data["is_boarder"],
    )
    link = _absolute(request, invitation.accept_url())
    etat = _send_invitation(user, invitation)
    log(request.user, "member.created", "members", user,
        "Membre créé et invité : %(email)s" % {"email": user.email}, request=request)
    messages.success(request, _("Invitation créée pour %(email)s.") % {"email": user.email})
    _alerte_envoi(request, etat, invitation, link)
    return redirect("members:members_detail", pk=user.pk)


def _send_invitation(user, invitation):
    """Renvoie le statut du courriel (« sent », « queued », « sending ») ou None.

    Une panne de notification in-app ou de push ne doit jamais être présentée
    comme une panne SMTP : chaque canal a son propre filet de sécurité. Seul
    l'état réel du courriel en file décide de l'alerte affichée.
    """
    from mail.services import queue_email
    from notifications.services import notify

    try:
        item = queue_email(to_email=user.email, recipient_user=user,
                           subject="Invitation à rejoindre l'association",
                           text_body=services.render_invitation_email(invitation),
                           kind="invitation", immediat=True)
    except Exception:  # noqa: BLE001 - sans file, le code reste transmissible à la main
        return None
    try:
        notify(user, "invitation", "Vous êtes invité·e à rejoindre l'association",
               "Ouvrez le lien reçu pour choisir votre mot de passe.", url=invitation.accept_url())
    except Exception:  # noqa: BLE001 - une notification n'est pas un courriel
        pass
    try:
        invitation.delivered = True
        invitation.save(update_fields=["delivered"])
    except Exception:  # noqa: BLE001
        pass
    return item.status


def _alerte_envoi(request, etat, invitation, lien: str = "") -> None:
    """N'alerte que si le courriel est vraiment en panne, jamais pour une notification."""
    manuel = (" — transmettez%(lien)s à la main, ou ce code : %(code)s"
              % {"lien": (" ce lien : %s" % lien) if lien else "", "code": invitation.code})
    if etat is None:
        messages.warning(request, _("E-mail impossible à mettre en file%(manuel)s") % {"manuel": manuel})
    elif etat == "failed":
        messages.warning(request, _("L'envoi SMTP a échoué, détail dans Réglages → Envois%(manuel)s")
                         % {"manuel": manuel})
    elif etat in ("queued", "sending"):
        messages.info(request, _("Courriel en file : départ automatique dans quelques secondes."))


def _absolute(request, path: str) -> str:
    base = str(getattr(Setting, "brand", lambda: {})().get("base_url", "") or "")
    if not base:
        base = request.build_absolute_uri("/")[:-1]
    return base.rstrip("/") + path


def _can_grant(actor, role: Role) -> bool:
    if role.is_administrator and not permissions.is_administrator(actor):
        return False
    return True


@module_required("members")
def detail(request, pk: int):
    member = get_object_or_404(User.objects.select_related("role"), pk=pk)
    invitation = getattr(member, "invitation", None)
    data = {
        "roles": member.role_memberships.select_related("role", "changed_by")[:20],
        "sessions": member.sessions.order_by("-last_seen")[:8],
        "attempts": member.login_attempts.order_by("-at")[:10],
        "acceptances": member.legal_acceptances.select_related("document")[:10],
        "audit": _audit_lines(member),
        "entries": _entries(member),
        "documents": _documents(member),
        "slots": _slots(member),
        "chores": _chores(member),
        "messages": _messages(member),
    }
    return render(request, "accounts/member_detail.html", {
        "member": member, "invitation": invitation, "data": data,
        "can_edit": permissions.can_edit(request.user, "members"),
        "is_admin": permissions.is_administrator(request.user),
        "all_roles": (Role.objects.order_by("order", "name") if permissions.is_administrator(request.user)
                      else Role.objects.filter(is_administrator=False).order_by("order", "name")),
        "page_title": member.get_full_name() or member.email,
    })


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _audit_lines(member):
    from audit.models import AuditEntry

    return _safe(lambda: AuditEntry.objects.filter(actor=member).order_by("-at")[:15], [])


def _entries(member):
    from finance.models import Entry

    return _safe(lambda: Entry.objects.filter(created_by=member).count(), 0)


def _documents(member):
    from documents.models import Document

    return _safe(lambda: Document.objects.filter(owner=member).count(), 0)


def _slots(member):
    from plannings.models import Availability

    return _safe(lambda: Availability.objects.filter(member=member).count(), 0)


def _chores(member):
    from chores.models import Assignment

    return _safe(lambda: {
        "valides": Assignment.objects.filter(member=member, status="validated").count(),
        "retard": Assignment.objects.filter(member=member, status="todo").count(),
    }, {})


def _messages(member):
    from mail.models import Recipient

    return _safe(lambda: {
        "lus": Recipient.objects.filter(user=member, read_at__isnull=False).count(),
        "non_lus": Recipient.objects.filter(user=member, read_at__isnull=True).count(),
    }, {})


@administrator_required
def create(request):
    form = MemberForm(request.POST or None, request.FILES or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        member.email = (member.email or "").strip().lower()
        if User.objects.filter(email__iexact=member.email).exists():
            form.add_error("email", _("Cette adresse est déjà utilisée."))
        else:
            member.status = member.status or "pending"
            member.save()
            RoleMembership.objects.create(user=member, role=member.role, changed_by=request.user)
            log(request.user, "member.created", "members", member, "Membre créé directement", request=request)
            messages.success(request, _("Membre créé."))
            return redirect("members:members_detail", pk=member.pk)
    return render(request, "accounts/member_form.html", {
        "form": form, "page_title": "Créer un membre", "member": None,
    })


@administrator_required
def edit(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    form = MemberForm(request.POST or None, request.FILES or None, instance=member, actor=request.user)
    if request.method == "POST" and form.is_valid():
        previous = {"role": member.role.name if member.role else None, "status": member.status,
                    "is_boarder": member.is_boarder}
        saved = form.save()
        current = {"role": saved.role.name if saved.role else None, "status": saved.status,
                   "is_boarder": saved.is_boarder}
        if previous["role"] != current["role"]:
            RoleMembership.objects.filter(user=saved, until__isnull=True).exclude(role=saved.role).update(
                until=timezone.now(), changed_by=request.user)
            RoleMembership.objects.create(user=saved, role=saved.role, changed_by=request.user)
            permissions.invalidate(saved)
        log(request.user, "member.updated", "members", saved, "Fiche membre modifiée",
            previous=previous, current=current, request=request)
        messages.success(request, _("Fiche enregistrée."))
        return redirect("members:members_detail", pk=saved.pk)
    return render(request, "accounts/member_form.html", {
        "form": form, "member": member, "page_title": "Modifier %s" % (member.get_full_name() or member.email),
    })


@administrator_required
@require_POST
def change_role(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    role = get_object_or_404(Role, pk=request.POST.get("role"))
    if role.is_administrator and not permissions.is_administrator(request.user):
        messages.error(request, _("Seul un Administrateur peut attribuer le rôle Administrateur."))
        return redirect("members:members_detail", pk=pk)
    if services.last_administrator(member) and not role.is_administrator:
        messages.error(request, _("Il faut au moins un compte Administrateur actif."))
        return redirect("members:members_detail", pk=pk)
    services.change_role(member, role, actor=request.user)
    messages.success(request, _("Rôle de %(membre)s : %(role)s.") % {"membre": member.get_full_name(), "role": role.name})
    return redirect("members:members_detail", pk=pk)


@administrator_required
@require_POST
def reset_password(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    services.set_password_by_admin(member, actor=request.user)
    messages.success(request, _("Mot de passe provisoire envoyé à %(email)s (jamais affiché à l'écran).")
                     % {"email": member.email})
    return redirect("members:members_detail", pk=pk)


@administrator_required
@require_POST
def unlock(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    member.unlock()
    log(request.user, "member.unlocked", "members", member, "Verrouillage levé", level="warn", request=request)
    messages.success(request, _("Compte débloqué."))
    return redirect("members:members_detail", pk=pk)


@administrator_required
@require_POST
def disable_2fa(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, _("Un motif est obligatoire pour couper l'A2F d'un membre."))
        return redirect("members:members_detail", pk=pk)
    member.totp_secret = ""
    member.totp_enabled = False
    member.totp_confirmed_at = None
    member.save(update_fields=["totp_secret", "totp_enabled", "totp_confirmed_at", "updated_at"])
    log(request.user, "member.2fa_reset", "members", member, "A2F coupée : %s" % reason, level="danger", request=request)
    try:
        from notifications.services import notify

        notify(member, "security", "Votre A2F a été désactivée",
               "L'authentification à deux facteurs a été coupée par le bureau. Motif : %s" % reason,
               url="/parametres/securite/")
    except Exception:
        pass
    messages.success(request, _("A2F désactivée, le membre est prévenu."))
    return redirect("members:members_detail", pk=pk)


@administrator_required
@require_POST
def toggle_status(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    if request.user.pk == member.pk:
        messages.error(request, _("Vous ne pouvez pas vous désactiver vous-même."))
        return redirect("members:members_detail", pk=pk)
    if member.status == "active":
        member.status = "inactive"
        services.revoke_all_sessions(member)
        log(request.user, "member.deactivated", "members", member, "Compte désactivé", level="warn", request=request)
        messages.success(request, _("Compte désactivé."))
    else:
        member.status = "active"
        member.save(update_fields=["status", "updated_at"])
        log(request.user, "member.reactivated", "members", member, "Compte réactivé", request=request)
        messages.success(request, _("Compte réactivé."))
    if member.status == "inactive":
        member.save(update_fields=["status", "updated_at"])
    return redirect("members:members_detail", pk=pk)


@reauth_required
@administrator_required
@require_POST
def anonymize(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    confirmation = (request.POST.get("confirmation") or "").strip().lower()
    expected = (member.last_name or member.email)[:3].lower()
    if confirmation != expected:
        messages.error(request, _("Saisissez « %(letters)s » pour confirmer l'anonymisation.") % {"letters": expected})
        return redirect("members:members_detail", pk=pk)
    log(request.user, "member.anonymized", "members", member, "Compte anonymisé par un administrateur",
        level="danger", request=request)
    services.revoke_all_sessions(member)
    member.anonymize()
    messages.success(request, _("Compte anonymisé : l'historique reste lisible sous ce nom pseudonymisé."))
    return redirect("members:members_list")


@administrator_required
@require_POST
def delete(request, pk: int):
    """Suppression définitive du compte, sans laisser de traces.

    À la différence de l'anonymisation (qui pseudonymise en conservant
    l'historique lisible), ici le compte et ses rattachements directs
    disparaissent. Réservé aux administrateurs, confirmation tapée.
    """
    member = get_object_or_404(User, pk=pk)
    if member.pk == request.user.pk:
        messages.error(request, _("Vous ne pouvez pas supprimer votre propre compte."))
        return redirect("members:members_detail", pk=pk)
    if (request.POST.get("confirmation") or "").strip().upper() != "SUPPRIMER":
        messages.error(request, _("Saisissez « SUPPRIMER » pour confirmer la suppression définitive."))
        return redirect("members:members_detail", pk=pk)
    email = member.email
    log(request.user, "member.deleted", "members", None,
        "Compte supprimé définitivement, sans traces : %(email)s" % {"email": email},
        level="danger", request=request)
    member.delete()
    messages.success(request, _("Compte %(email)s supprimé définitivement.") % {"email": email})
    return redirect("members:members_list")


@module_required("members", edit=True)
@require_POST
def invitation_resend(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    invitation = getattr(member, "invitation", None)
    if invitation is None or invitation.is_used:
        messages.error(request, _("Aucune invitation en cours pour ce compte."))
        return redirect("members:members_detail", pk=pk)
    invitation.renew()
    _alerte_envoi(request, _send_invitation(member, invitation), invitation)
    log(request.user, "member.invitation_resent", "members", member, "Invitation renvoyée", request=request)
    messages.success(request, _("Invitation renvoyée (nouveau lien, nouveau code)."))
    return redirect("members:members_detail", pk=pk)


@module_required("members", edit=True)
@require_POST
def invitation_revoke(request, pk: int):
    member = get_object_or_404(User, pk=pk)
    invitation = getattr(member, "invitation", None)
    if invitation:
        invitation.expires_at = timezone.now()
        invitation.save(update_fields=["expires_at"])
        log(request.user, "member.invitation_revoked", "members", member, "Invitation révoquée", level="warn",
            request=request)
        messages.success(request, _("Invitation révoquée."))
    return redirect("members:members_detail", pk=pk)


@module_required("members")
def export(request):
    queryset, _params = _filters(request)
    detailed = request.GET.get("detail") == "1"
    headers = ["Nom", "Prénom", "E-mail", "Fonction", "Rôle", "Statut", "Interne", "A2F", "Dernière activité"]
    if detailed:
        headers += ["Téléphone", "Invitation", "Sessions", "Dernière connexion"]
    rows = []
    for member in queryset.iterator(chunk_size=200):
        row = [member.last_name, member.first_name, member.email, member.display_function,
               member.role.name if member.role else "", member.get_status_display(),
               "oui" if member.is_boarder else "non", "oui" if member.two_factor_on else "non",
               member.last_seen.strftime("%d/%m/%Y") if member.last_seen else ""]
        if detailed:
            row += [member.phone,
                    getattr(member, "invitation", None).code if getattr(member, "invitation", None) else "",
                    member.sessions.count(),
                    member.login_attempts.first().at.strftime("%d/%m/%Y %H:%M")
                    if member.login_attempts.exists() else ""]
        rows.append(row)
    log(request.user, "member.exported", "members", None, "Export CSV des membres (%d lignes)" % len(rows),
        request=request)
    return csv_response("membres-%s.csv" % timezone.localdate().strftime("%Y%m%d"), headers, rows)
