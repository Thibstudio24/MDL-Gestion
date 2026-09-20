"""Crée (non interactif) le compte super-administrateur d'une instance.

Utilisé par ``scripts/nouvelle_instance.sh`` pour monter une instance sans
passer par l'assistant : ``manage.py mdl_admin --email a@b.c --password '...'``.
"""
from __future__ import annotations

import secrets

from django.core.management.base import BaseCommand

from accounts.models import User
from accounts.services import ensure_admin_role


class Command(BaseCommand):
    help = "Crée le compte administrateur (idempotent : ne touche pas à un compte existant)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", default="",
                            help="Laisser vide pour générer un mot de passe robuste (affiché une fois).")
        parser.add_argument("--first-name", default="Administration")
        parser.add_argument("--last-name", default="Centrale")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            self.stdout.write("COMPTE_EXISTANT email=%s" % email)
            return
        password = options["password"] or (secrets.token_urlsafe(12) + "Aa1!")
        role = ensure_admin_role()
        User.objects.create_user(email=email, password=password, role=role,
                                 first_name=options["first_name"], last_name=options["last_name"])
        self.stdout.write("COMPTE_CREE email=%s password=%s" % (email, password))
