"""Sauvegarde : base + fichiers dans backups/, à lancer chaque nuit."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core import services


class Command(BaseCommand):
    help = "Crée une sauvegarde (base de données et fichiers) dans le dossier backups/."

    def add_arguments(self, parser):
        parser.add_argument("--no-media", action="store_true", help="Ne pas inclure le dossier media/.")
        parser.add_argument("--output", default=None, help="Chemin de sortie (défaut : backups/mdl-<date>.zip).")

    def handle(self, *args, **options):
        path = services.backup(output=options["output"], with_media=not options["no_media"])
        self.stdout.write("Sauvegarde créée : %s (%s octets)" % (path, path.stat().st_size))
