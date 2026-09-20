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
    en_attente = list(instance.pending_actions or [])
    instance.pending_actions = []
    instance.save(update_fields=["counters", "version", "last_ping_at", "last_error",
                                 "pending_actions"])
    from django.conf import settings

    return JsonResponse({
        "ok": True,
        "latest_version": getattr(settings, "VERSION", ""),
        "pending_actions": en_attente,
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

def deblocage(request):
    """Écran de verrouillage : motif, contact de la centrale, import du fichier
    de déblocage signé (fonctionne hors connexion)."""
    from django.core.cache import cache

    from core import centrale
    from core.models import Installation

    install = Installation.get()
    verrou, motif = centrale.etat_verrou(install)
    if request.method == "POST":
        fichier = request.FILES.get("fichier")
        if fichier is None:
            messages.error(request, _("Choisissez le fichier de déblocage reçu par courriel."))
            return redirect("centrale:deblocage")
        contenu = fichier.read(20000).decode("utf-8", "replace").strip()
        try:
            jeton = json.loads(contenu).get("jeton", contenu)
        except json.JSONDecodeError:
            jeton = contenu
        resultat = centrale.appliquer_jeton(jeton)
        if resultat.get("ok"):
            cache.delete("verrou_centrale")
            messages.success(request, _("Déblocage accepté : %(detail)s.")
                             % {"detail": resultat.get("message", "")})
            return redirect("/")
        messages.error(request, _("Fichier refusé : %(erreur)s.") % {"erreur": resultat.get("error", "?")})
        return redirect("centrale:deblocage")
    return render(request, "core/deblocage.html", {
        "page_title": _("Instance verrouillée"),
        "verrou": verrou, "motif": motif,
        "contact": centrale.CONTACT_DEBLOCAGE,
        "delai": centrale.DELAI_SANS_CENTRALE_JOURS,
        "grace": install.grace_until,
    })


def cle_privee_centrale() -> str:
    from core.models import Setting

    return str(Setting.data().get("centrale", {}).get("cle_privee", "") or "")


def _jeton_pour(instance, action: str, target: str = "", code: str = "",
                ttl_minutes: int = 60 * 24 * 14, reason: str = "") -> dict:
    from core import centrale

    token = centrale.signer_jeton(cle_privee_centrale(), instance.install_id, action,
                                  target=target, code=code, ttl_minutes=ttl_minutes, reason=reason)
    return {"code": (instance.install_id + action)[:32], "action": action, "target": target,
            "token": token, "reason": reason,
            "expires_at": (timezone.now() + timezone.timedelta(minutes=ttl_minutes)).isoformat()}


@administrator_required
@require_POST
def instance_action(request, pk):
    """Prépare un ordre signé (livré au prochain heartbeat de l'instance)."""
    from core import centrale

    instance = get_object_or_404(HubInstance, pk=pk)
    if not cle_privee_centrale():
        messages.error(request, _("La clé privée de la centrale n'est pas initialisée : "
                                  "lancez « manage.py mdl_centrale_init --cle-privee … »."))
        return redirect("centrale:index")
    type_action = request.POST.get("action", "")
    cible = (request.POST.get("target") or "").strip()
    if type_action not in centrale.ACTIONS_CENTRALE:
        messages.error(request, _("Action inconnue."))
        return redirect("centrale:index")
    if type_action in ("reset_password", "disable_2fa") and not cible:
        messages.error(request, _("Précisez le courriel du compte administrateur visé."))
        return redirect("centrale:index")
    code = ""
    raison = (request.POST.get("reason") or "").strip()
    if type_action == "reset_password":
        import secrets as _secrets

        code = _secrets.token_urlsafe(9) + "Aa1"
    if type_action == "unblock":
        code = str(request.POST.get("jours") or 30)
    ordre = _jeton_pour(instance, type_action, cible, code,
                        reason=raison or "décision de la centrale")
    pending = list(instance.pending_actions or [])
    pending.append(ordre)
    instance.pending_actions = pending
    instance.save(update_fields=["pending_actions"])
    audit.log(request.user, "centrale.action_queued", "settings", instance,
              "Ordre %s préparé pour %s%s" % (type_action, instance.label,
                                              (" (compte %s)" % cible) if cible else ""),
              level="danger", request=request)
    if type_action == "reset_password":
        messages.success(request, _("Ordre prêt. Mot de passe provisoire à transmettre à "
                                    "l'association : %(mdp)s (livré au prochain heartbeat).") % {"mdp": code})
    else:
        messages.success(request, _("Ordre « %(action)s » en file : il partira au prochain "
                                    "heartbeat de l'instance.") % {"action": type_action})
    return redirect("centrale:index")


@administrator_required
@require_POST
def instance_cle(request, pk):
    """Fichier de déblocage hors ligne à envoyer par courriel à l'association."""
    from django.http import HttpResponse

    instance = get_object_or_404(HubInstance, pk=pk)
    if not cle_privee_centrale():
        messages.error(request, _("La clé privée de la centrale n'est pas initialisée."))
        return redirect("centrale:index")
    try:
        jours = max(1, int(request.POST.get("jours") or 90))
    except ValueError:
        jours = 90
    ordre = _jeton_pour(instance, "unblock", code=str(jours),
                        ttl_minutes=jours * 24 * 60 + 60,
                        reason="déblocage hors ligne après courriel")
    reponse = HttpResponse(json.dumps({"jeton": ordre["token"]}, indent=2),
                           content_type="application/json")
    reponse["Content-Disposition"] = 'attachment; filename="deblocage-%s.json"' % instance.install_id[:8]
    audit.log(request.user, "centrale.action_queued", "settings", instance,
              "Fichier de déblocage hors ligne (%d jours) téléchargé" % jours,
              level="danger", request=request)
    return reponse
