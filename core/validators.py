"""Validateurs de mot de passe et hachage (PBKDF2-SHA256 1 200 000 tours)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

MIN_LENGTH_DEFAULT = 10
_DATA = Path(__file__).resolve().parent / "data" / "common_passwords.txt"


class MdlPBKDF2SHA256Hasher(PBKDF2PasswordHasher):
    """PBKDF2-SHA256 avec 1 200 000 itérations (Argon2 prend le relais s'il existe)."""

    iterations = 1_200_000


@lru_cache(maxsize=1)
def common_passwords() -> frozenset[str]:
    try:
        raw = _DATA.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover
        return frozenset()
    return frozenset(line.strip().lower() for line in raw.splitlines() if line.strip() and not line.startswith("#"))


def strength(password: str, user=None) -> int:
    """Indicateur de robustesse 0-4 affiché sous le champ mot de passe."""
    score = 0
    if len(password) >= 10:
        score += 1
    if len(password) >= 14:
        score += 1
    kinds = sum(
        1
        for test in (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
        if test
    )
    if kinds >= 3:
        score += 1
    if kinds == 4 and len(password) >= 16:
        score += 1
    if password.lower() in common_passwords():
        return 0
    return min(score, 4)


class MinLengthValidator:
    """Longueur minimale (10 par défaut, réglable dans instance.json)."""

    def __init__(self, min_length: int | None = None):
        self.min_length = min_length

    def _min(self) -> int:
        if self.min_length:
            return int(self.min_length)
        try:
            from django.conf import settings

            from core.models import Setting

            return int(Setting.value("securite", "password_min_length", settings_min(settings)))
        except Exception:
            return MIN_LENGTH_DEFAULT

    def validate(self, password, user=None):
        minimum = self._min()
        if len(password or "") < minimum:
            raise ValidationError(
                _("Ce mot de passe est trop court : il faut au moins %(n)s caractères."),
                code="password_too_short",
                params={"n": minimum},
            )

    def get_help_text(self):
        return _("Utilisez au moins %(n)s caractères.") % {"n": self._min()}


def settings_min(settings) -> int:
    return int(getattr(settings, "MDL_PASSWORD_MIN_LENGTH", MIN_LENGTH_DEFAULT))


class CommonPasswordListValidator:
    """Refus d'une liste embarquée (~1 250 mots courants, claviers, années)."""

    def validate(self, password, user=None):
        if (password or "").strip().lower() in common_passwords():
            raise ValidationError(
                _("Ce mot de passe est trop connu : choisissez-en un autre (une phrase de trois mots fonctionne bien)."),
                code="password_too_common",
            )

    def get_help_text(self):
        return _("Les mots de passe les plus courants sont refusés.")


class NumericPasswordValidator:
    def validate(self, password, user=None):
        if (password or "").isdigit():
            raise ValidationError(
                _("Un mot de passe uniquement numérique est refusé : ajoutez des lettres."),
                code="password_entirely_numeric",
            )

    def get_help_text(self):
        return _("Le mot de passe ne peut pas être uniquement numérique.")


class PersonalDataValidator:
    """Refus du prénom, du nom et de l'e-mail du membre dans son mot de passe."""

    def validate(self, password, user=None):
        if user is None:
            return
        low = (password or "").lower()
        parts = []
        for attr in ("first_name", "last_name", "email", "display_function", "phone"):
            value = getattr(user, attr, None)
            if not value:
                continue
            parts.extend(str(value).lower().replace("@", " ").replace(".", " ").split())
        for part in parts:
            if len(part) >= 3 and part in low:
                raise ValidationError(
                    _("Ce mot de passe contient votre nom, votre prénom ou votre e-mail."),
                    code="password_too_similar",
                )

    def get_help_text(self):
        return _("N'utilisez pas votre nom, votre prénom ni votre adresse e-mail.")
