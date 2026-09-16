"""Aide-intervention : jeton Ed25519 hors ligne (/aide-intervention/)."""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from audit import services as audit
from core import crypto, services
from core.decorators import administrator_required
from core.models import Installation, Intervention


@administrator_required
def index(request):
    install = Installation.get()
    return render(request, "core/intervention.html", {
        "install": install,
        "pending": Intervention.pending(),
        "allowed": crypto.ALLOWED_ACTIONS,
        "page_title": "Aide-intervention",
    })


@administrator_required
@require_POST
def apply_token(request):
    token = (request.POST.get("token") or "").strip()
    install = Installation.get()
    public_pem = install.public_key_pem
    if not token:
        messages.error(request, _("Collez le jeton fourni par l'éditeur."))
        return redirect("devhub:devhub_index")
    result = crypto.verify(token, public_pem, install.install_id)
    if not result["ok"]:
        messages.error(request, _("Jeton refusé : %(erreur)s.") % {"erreur": result["error"]})
        return redirect("devhub:devhub_index")
    intervention, created = Intervention.objects.get_or_create(
        code="token-%s" % result["code"],
        defaults={
            "token": token,
            "action": result["action"],
            "target": result["target"],
            "reason": result["reason"],
            "origin": "token",
            "expires_at": timezone.datetime.fromtimestamp(result["expires_at"]) if hasattr(timezone, "datetime")
            else None,
            "status": "queued",
        },
    )
    outcome = services.apply_intervention(intervention, actor=request.user)
    audit.log(request.user, "devhub.token_applied", "devhub", intervention,
              "Jeton d'intervention appliqué : %s" % result["action"],
              level="danger", request=request)
    if outcome.get("ok"):
        messages.success(request, _("Intervention appliquée : %(detail)s") % {"detail": outcome.get("message", "")})
    else:
        messages.error(request, _("Échec : %(erreur)s") % {"erreur": outcome.get("error", "?")})
    return redirect("devhub:devhub_index")
