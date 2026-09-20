"""Vue côté instance : écran de verrouillage / déblocage hors ligne.

Le code de la centrale (supervision, signature des ordres) vit dans un dépôt
privé séparé ; ce module ne contient que ce dont une instance a besoin pour
afficher l'écran de verrouillage et importer un fichier de déblocage signé.
"""
from __future__ import annotations

import json

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _


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
            return redirect("deblocage")
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
        return redirect("deblocage")
    return render(request, "core/deblocage.html", {
        "page_title": _("Instance verrouillée"),
        "verrou": verrou, "motif": motif,
        "contact": centrale.CONTACT_DEBLOCAGE,
        "delai": centrale.DELAI_SANS_CENTRALE_JOURS,
        "grace": install.grace_until,
    })
