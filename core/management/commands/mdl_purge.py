"""Purges : versions de documents, corbeille, notifications lues, photos de ménage."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core import services


class Command(BaseCommand):
    help = "Purge les données anciennes selon les quotas réglés dans l'application."

    def add_arguments(self, parser):
        parser.add_argument("quoi", nargs="?", default="tout",
                            choices=["tout", "versions", "trash", "notifications", "menage", "mail"],
                            help="Ce qu'il faut purger (défaut : tout).")
        parser.add_argument("--dry-run", action="store_true", help="Compter sans supprimer.")

    def handle(self, *args, **options):
        target = options["quoi"]
        dry = options["dry_run"]
        if target in ("tout", "menage"):
            from chores.services import purge_photos

            self.stdout.write("photos de ménage : %s" % purge_photos(dry_run=dry))
        if target in ("tout", "mail"):
            from mail.services import purge_read_emails

            self.stdout.write("messages lus : %s" % purge_read_emails(dry_run=dry))
        if target in ("tout", "versions", "trash", "notifications"):
            for what in (["versions", "trash", "notifications"] if target == "tout" else [target]):
                result = services.purge(what, dry_run=dry)
                self.stdout.write("%-14s %s" % (what, result))
