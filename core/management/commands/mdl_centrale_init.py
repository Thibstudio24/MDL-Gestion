"""Initialise la clé privée de la centrale (jamais dans le dépôt).

Le code des instances embarque uniquement la clé publique correspondante ;
collez ici la clé privée fournie avec le projet, puis vérifiez que la clé
publique affichée est bien celle du code :

    manage.py mdl_centrale_init --cle-privee "-----BEGIN PRIVATE KEY----- …"
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.models import Setting


class Command(BaseCommand):
    help = "Enregistre la clé privée Ed25519 de la centrale et affiche la clé publique."

    def add_arguments(self, parser):
        parser.add_argument("--cle-privee", dest="cle_privee", default="",
                            help="PEM de la clé privée de la centrale.")

    def handle(self, *args, **options):
        pem = (options["cle_privee"] or "").strip().replace("\\n", "\n")
        if not pem:
            pem = Setting.data().get("centrale", {}).get("cle_privee", "")
            if not pem:
                raise CommandError("Fournissez --cle-privee (PEM transmis avec le projet).")
        from core.crypto import load_private

        if load_private(pem) is None:
            raise CommandError("Clé privée illisible.")
        Setting.update_section("centrale", {"cle_privee": pem})
        from cryptography.hazmat.primitives import serialization

        cle = load_private(pem)
        publique = cle.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.stdout.write("CLE_PRIVEE_ENREGISTREE")
        self.stdout.write(publique)
