"""Tâche planifiée : à lancer toutes les heures par le cron alwaysdata."""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from core import services


class Command(BaseCommand):
    help = "Exécute la chaîne de traitement horaire : file SMTP, diffusions, rappels, bilan, purges."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Sortie JSON (pour les journaux).")

    def handle(self, *args, **options):
        report = services.cron_run()
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            return
        self.stdout.write("Cron du %s" % report.get("lance_le", ""))
        for name, value in (report.get("etapes") or {}).items():
            self.stdout.write("  %-14s %s" % (name, value))
