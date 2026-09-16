"""Référentiels par défaut. Ne crée jamais de compte ni de donnée de démonstration."""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crée les rôles, catégories et comptes par défaut (aucune donnée de démonstration)."

    def handle(self, *args, **options):
        from accounts.services import create_board_roles, ensure_base_roles
        from documents.services import ensure_default_categories
        from finance.services import ensure_accounts, ensure_default_categories as finance_categories
        from finance.services import ensure_gap_category

        ensure_base_roles()
        created = create_board_roles()
        ensure_default_categories()
        finance_categories()
        ensure_gap_category()
        ensure_accounts()
        from accounts.models import Role
        from documents.models import Category as DocCategory
        from finance.models import Account, Category as FinCategory

        self.stdout.write("rôles : %s (%d créés par la trame du bureau)" % (Role.objects.count(), len(created)))
        self.stdout.write("catégories de documents : %s" % DocCategory.objects.count())
        self.stdout.write("catégories de trésorerie : %s" % FinCategory.objects.count())
        self.stdout.write("comptes : %s" % ", ".join(Account.objects.values_list("name", flat=True)))
        self.stdout.write("Aucun compte utilisateur ni donnée de démonstration n'a été créé.")
