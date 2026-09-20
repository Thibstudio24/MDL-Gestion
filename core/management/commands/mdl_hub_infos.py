"""Affiche les infos de raccordement à transmettre à la centrale.

Sortie lisible par le script : ``INSTALL_ID=...`` et ``SECRET=...``.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core.models import Installation


class Command(BaseCommand):
    help = "Affiche install_id + secret de cette installation (à coller dans la centrale)."

    def handle(self, *args, **options):
        installation = Installation.get()
        self.stdout.write("INSTALL_ID=%s" % installation.install_id)
        self.stdout.write("SECRET=%s" % installation.secret)
