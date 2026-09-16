"""Ramassage des fichiers statiques.

WhiteNoise, avec CompressedManifestStaticFilesStorage, résout au post-traitement
les références `sourceMappingURL` des fichiers JS et CSS. Si la cible manque,
`collectstatic` échoue — ce qui casse le déploiement sur le serveur alors que la
suite de tests passe. D'où ces deux gardes.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

STATIC_DIR = Path(settings.BASE_DIR) / "static"
_SOURCE_MAP = re.compile(r"sourceMappingURL=(\S+)")


def test_collectstatic_reussit(tmp_path):
    """Le déploiement joue collectstatic : il doit rendre la main sans erreur."""
    cible = tmp_path / "staticfiles"
    with override_settings(STATIC_ROOT=str(cible)):
        call_command("collectstatic", "--noinput", verbosity=0)

    assert cible.is_dir(), "collectstatic n'a rien produit"
    assert list((cible / "vendor").glob("chart.umd.min*.js")), "Chart.js manque à l'arrivée"


def test_aucune_reference_de_source_map_pendante():
    """Aucun fichier statique ne doit pointer vers une carte source absente."""
    pendantes = []
    for fichier in STATIC_DIR.rglob("*"):
        if not fichier.is_file() or fichier.suffix not in {".js", ".css"}:
            continue
        for ref in _SOURCE_MAP.findall(fichier.read_text(encoding="utf-8", errors="ignore")):
            if not (fichier.parent / ref).exists():
                pendantes.append("%s -> %s" % (fichier.relative_to(STATIC_DIR), ref))

    assert not pendantes, "références de carte source pendantes : %s" % ", ".join(pendantes)


def test_le_bundle_chartjs_est_local():
    """Le dossier interdit tout CDN à l'exécution : Chart.js doit être embarqué."""
    bundle = STATIC_DIR / "vendor" / "chart.umd.min.js"
    assert bundle.is_file(), "static/vendor/chart.umd.min.js est absent"
    assert bundle.stat().st_size > 100_000, "le bundle Chart.js semble tronqué"
