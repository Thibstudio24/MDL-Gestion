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


# --------------------------------------------------------------------------- #
# Garde-fous globaux : aucun test ne doit toucher au vrai config/instance.json
# ni laisser fuir les réglages mail appliqués à chaud dans django.conf.settings.
# --------------------------------------------------------------------------- #
_CLES_MAIL = ["MAIL_ENABLED", "EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT",
              "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "EMAIL_USE_SSL",
              "EMAIL_USE_TLS", "DEFAULT_FROM_EMAIL", "SERVER_EMAIL",
              "MAIL_RATE_PER_MINUTE"]


@pytest.fixture(autouse=True)
def _hub_coupe(settings):
    """Aucun test ne doit contacter la vraie centrale (URL par défaut réelle).

    Vide aussi les caches : les réglages (Setting) y sont conservés d'un test
    à l'autre alors que la base, elle, est déroulée.
    """
    from django.core.cache import cache

    cache.clear()
    settings.HUB_URL = ""


@pytest.fixture(autouse=True)
def _instance_json_en_memoire(monkeypatch):
    """write_instance capture en mémoire au lieu d'écrire config/instance.json."""
    from config import settings as instance

    store = {}

    def fake_write(data, **kwargs):
        store.clear()
        store.update(data)

    monkeypatch.setattr(instance, "write_instance", fake_write)
    return store


@pytest.fixture(autouse=True)
def _restaure_reglages_mail():
    """Les vues appliquent le SMTP à chaud : on restaure après chaque test."""
    from django.conf import settings as s

    avant = {cle: getattr(s, cle, None) for cle in _CLES_MAIL}
    yield
    for cle, valeur in avant.items():
        setattr(s, cle, valeur)
