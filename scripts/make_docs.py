#!/usr/bin/env python3
"""Génère la documentation Markdown depuis ``core/help_content.py``.

``core/help_content.py`` est la source unique du mode d'emploi en ligne
(``/aide/``) : ce script en dérive les fichiers Markdown de ``docs/`` pour
qu'aucune divergence ne puisse s'installer entre l'aide affichée et les
documents du dépôt.

Relancer :  .venv/bin/python scripts/make_docs.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from core.help_content import CHECKLIST_EMAIL, FAQ, GLOSSARY, SECTIONS  # noqa: E402

DOCS = ROOT / "docs"

#: Sections qui constituent le guide d'installation alwaysdata.
INSTALL_IDS = {"3", "4", "5", "6", "7", "8", "9", "10"}

EN_TETE = (
    "<!-- Ce fichier est généré par scripts/make_docs.py depuis core/help_content.py. -->\n"
    "<!-- Ne pas modifier à la main : corriger core/help_content.py puis relancer le script. -->\n"
)


def section_map() -> dict[str, tuple[str, str]]:
    return {num: (titre, corps) for num, titre, corps in SECTIONS}


def render(title: str, intro: str, nums: list[str]) -> str:
    """Rend une liste de sections numérotées en Markdown."""
    sections = section_map()
    parts = [EN_TETE, "# %s\n" % title, intro.strip(), ""]
    for num in nums:
        titre, corps = sections[num]
        parts.append("## %s. %s\n" % (num, titre))
        parts.append(corps.strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def write_mode_emploi() -> Path:
    nums = [num for num, _titre, _corps in SECTIONS if num not in INSTALL_IDS]
    sections = section_map()
    parts = [
        EN_TETE,
        "# Mode d'emploi\n",
        "Mode d'emploi de MDL Gestion, du premier démarrage à la rentrée scolaire.\n"
        "La même aide est disponible dans l'application à l'adresse `/aide/` ;\n"
        "l'installation sur alwaysdata est décrite dans "
        "[INSTALL-ALWAYSDATA.md](INSTALL-ALWAYSDATA.md).\n",
    ]
    for num in nums:
        titre, corps = sections[num]
        parts.append("## %s. %s\n" % (num, titre))
        parts.append(corps.strip())
        parts.append("")

    parts.append("## FAQ\n")
    for question, reponse in FAQ:
        parts.append("### %s\n" % question)
        parts.append(reponse.strip())
        parts.append("")

    parts.append("## Glossaire\n")
    for terme, definition in GLOSSARY:
        parts.append("* **%s** — %s" % (terme, definition.strip()))
    parts.append("")

    parts.append("## Check-list de rentrée\n")
    parts.append("```text%s```" % CHECKLIST_EMAIL.rstrip())
    parts.append("")
    return _write("MODE-EMPLOI.md", "\n".join(parts).rstrip() + "\n")


def write_install() -> Path:
    return _write(
        "INSTALL-ALWAYSDATA.md",
        render(
            "Installation sur alwaysdata (plan Free)",
            """
Déploiement de MDL Gestion sur l'offre gratuite d'alwaysdata : 1 Go de disque,
256 Mo de mémoire, 1/4 de CPU, sous-domaine `*.alwaysdata.net`, HTTPS, cron et
SMTP inclus. Comptez une demi-heure.

Les limites du plan Free sont suffisantes pour 10 à 25 comptes. Au-delà, passez
sur un plan payant ou découpez l'association en plusieurs installations.
""",
            sorted(INSTALL_IDS, key=int),
        ),
    )


def _write(name: str, content: str) -> Path:
    DOCS.mkdir(parents=True, exist_ok=True)
    path = DOCS / name
    path.write_text(content, encoding="utf-8")
    return path


if __name__ == "__main__":
    written = [write_mode_emploi(), write_install()]
    for path in written:
        print("%s — %d lignes" % (path.relative_to(ROOT), len(path.read_text(encoding="utf-8").splitlines())))
