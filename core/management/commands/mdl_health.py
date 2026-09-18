"""État de santé : à consulter après un déploiement ou un incident."""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from core import services


class Command(BaseCommand):
    help = "Affiche l'état de santé de l'installation (volumes, quotas, alertes)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Sortie JSON.")

    def handle(self, *args, **options):
        data = services.health()
        if options["json"]:
            self.stdout.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            return
        for key, value in data.items():
            self.stdout.write("%-22s %s" % (key, value))
