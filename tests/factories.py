"""Fabriques de test (aucun utilisateur fictif n'est créé en production)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import Role, User
from core.models import SchoolYear
from core.permissions import DEFAULT_LEVELS


def make_role(name: str = "Testeur", administrator: bool = False, levels: dict | None = None,
              fine: list | None = None) -> Role:
    from accounts.services import _apply_levels

    role = Role.objects.create(
        name=name, slug=name.lower().replace(" ", "-"), is_administrator=administrator,
        is_system=False, order=90,
    )
    if levels is None:
        levels = DEFAULT_LEVELS["Administrateur"] if administrator else {"dashboard": 1, "documents": 2,
                                                                        "planning_salle": 2,
                                                                        "planning_menage": 2, "mail": 1}
    _apply_levels(role, levels, fine or [])
    return role


def make_user(email: str = "membre@example.test", password: str = "MotDePasse-Solide-2026",
              role: Role | None = None, administrator: bool = False, **kwargs) -> User:
    if role is None:
        role = Role.objects.filter(is_administrator=administrator).first() or make_role(administrator=administrator)
    user = User.objects.create_user(email=email, password=password, role=role,
                                    first_name=kwargs.pop("first_name", "Camille"),
                                    last_name=kwargs.pop("last_name", "Test"), status="active", **kwargs)
    return user


def make_admin(email: str = "admin@example.test") -> User:
    return make_user(email=email, administrator=True)


def make_year(label: str | None = None, start: date | None = None, current: bool = True) -> SchoolYear:
    today = timezone.localdate()
    start = start or date(today.year if today.month >= 9 else today.year - 1, 9, 1)
    end = date(start.year + 1, 8, 31)
    label = label or "%d-%d" % (start.year, start.year + 1)
    return SchoolYear.objects.create(label=label, start_date=start, end_date=end, is_current=current)


def make_entry(year: SchoolYear, day: date, title: str = "Achat", amount: str = "10.00", kind: str = "D",
               account=None, category=None, user=None):
    from finance.models import Entry

    return Entry.objects.create(year=year, day=day, title=title, amount=Decimal(amount), kind=kind,
                                account=account, category=category, created_by=user)


def make_campaign(year: SchoolYear, label: str = "Campagne test", **kwargs):
    from plannings.models import Campaign

    return Campaign.objects.create(year=year, label=label,
                                   start_date=kwargs.pop("start_date", timezone.localdate()),
                                   weeks_count=kwargs.pop("weeks_count", 4), **kwargs)
