"""Fixtures partagées : aucun compte de démonstration, tout est créé à la demande."""
from __future__ import annotations

import pytest
from django.utils import timezone

from tests.factories import make_admin, make_campaign, make_chore_campaign, make_role, make_user, make_year


@pytest.fixture
def year(db):
    return make_year()


@pytest.fixture
def admin_role(db):
    return make_role("Administrateur de test", administrator=True)


@pytest.fixture
def member_role(db):
    return make_role("Membre de test")


@pytest.fixture
def admin(db, admin_role):
    return make_admin("admin-test@example.test")


@pytest.fixture
def member(db, member_role):
    return make_user("membre-test@example.test", role=member_role)


@pytest.fixture
def admin_client(client, admin):
    client.force_login(admin)
    return client


@pytest.fixture
def member_client(client, member):
    client.force_login(member)
    return client


@pytest.fixture
def campaign(db, year):
    """Campagne publiée et ouverte : c'est l'état dans lequel les membres répondent."""
    return make_campaign(year, published=True)


@pytest.fixture
def chore_campaign(db, year):
    return make_chore_campaign(year)


@pytest.fixture
def today():
    return timezone.localdate()
