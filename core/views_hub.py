"""La « centrale » : superviser d'autres instances MDL Gestion.

Chaque instance distante envoie son heartbeat signé (install_id + secret
partagé, HMAC-SHA256 du corps) vers ``/api/heartbeat/`` de ce site quand son
réglage ``hub.url`` pointe ici. Le super-administrateur de la centrale
enregistre les instances avec les infos transmises par le script de
déploiement (``scripts/nouvelle_instance.sh`` / ``manage.py mdl_hub_infos``).
"""
from __future__ import annotations

import hashlib
import json

from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from audit import services as audit
from core.decorators import administrator_required
from core.models import HubInstance

DERIVE_SECONDS = 300


@csrf_exempt
@require_POST
def heartbeat(request):
    """Reçoit le ping signé d'une instance raccordée.

    Signature attendue : sha256("<install_id>|<secret>|<corps JSON>").
    Horodatage accepté à ±5 minutes.
    """
    install_id = request.headers.get("X-Install-Id", "")
    signature = request.headers.get("X-Signature", "")
    horodatage = request.headers.get("X-Timestamp", "")
    instance = HubInstance.objects.filter(install_id=install_id).first()
    if instance is None:
        return JsonResponse({"ok": False, "message": "instance inconnue"}, status=404)
    corps = request.body.decode("utf-8", "replace")
    attendu = hashlib.sha256(("%s|%s|%s" % (install_id, instance.secret, corps)).encode()).hexdigest()
    if attendu != signature:
        instance.last_error = "signature invalide"
        instance.save(update_fields=["last_error"])
        return HttpResponseForbidden("signature invalide")
    try:
        ecart = abs(int(timezone.now().timestamp()) - int(horodatage or "0"))
    except ValueError:
        ecart = DERIVE_SECONDS + 1
    if ecart > DERIVE_SECONDS:
        instance.last_error = "horodatage trop ancien"
        instance.save(update_fields=["last_error"])
        return HttpResponseForbidden("horodatage invalide")
    try:
        payload = json.loads(corps or "{}")
    except json.JSONDecodeError:
        payload = {}
    battement = payload.get("heartbeat") or {}
    instance.counters = battement if isinstance(battement, dict) else {}
    instance.version = str(battement.get("version", "") or "")[:20]
    instance.last_ping_at = timezone.now()
    instance.last_error = ""
    instance.save(update_fields=["counters", "version", "last_ping_at", "last_error"])
    from django.conf import settings

    return JsonResponse({
        "ok": True,
        "latest_version": getattr(settings, "VERSION", ""),
        "pending_actions": [],
    })


@administrator_required
def index(request):
    """Tableau de bord de la centrale : instances raccordées et leur état."""
    return render(request, "core/centrale.html", {
        "page_title": _("Centrale"),
        "instances": HubInstance.objects.all(),
        "maintenant": timezone.now(),
    })


@administrator_required
@require_POST
def instance_add(request):
    """Enregistre une instance avec les infos transmises par son administrateur."""
    install_id = (request.POST.get("install_id") or "").strip()
    secret = (request.POST.get("secret") or "").strip()
    label = (request.POST.get("label") or "").strip() or install_id[:24]
    if not install_id or not secret:
        messages.error(request, _("Identifiant et secret de l'instance sont obligatoires."))
        return redirect("centrale:index")
    instance, cree = HubInstance.objects.update_or_create(
        install_id=install_id,
        defaults={"secret": secret, "label": label,
                  "url": (request.POST.get("url") or "").strip()[:200]},
    )
    audit.log(request.user, "centrale.instance_added", "settings", instance,
              "Instance %s : %s" % ("ajoutée" if cree else "mise à jour", label),
              level="warn", request=request)
    messages.success(request, _("Instance « %(nom)s » raccordée : son prochain heartbeat "
                                "la fera apparaître en ligne.") % {"nom": label})
    return redirect("centrale:index")


@administrator_required
@require_POST
def instance_delete(request, pk):
    instance = get_object_or_404(HubInstance, pk=pk)
    nom = instance.label
    instance.delete()
    audit.log(request.user, "centrale.instance_deleted", "settings", None,
              "Instance débranchée : %s" % nom, level="warn", request=request)
    messages.success(request, _("Instance « %(nom)s » débranchée.") % {"nom": nom})
    return redirect("centrale:index")
