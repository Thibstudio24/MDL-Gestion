"""Gestionnaire du modèle User (e-mail = identifiant)."""
from __future__ import annotations

from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.full_clean(exclude=["email"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("status", "active")
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        from accounts.models import Role

        role = Role.objects.filter(is_administrator=True).first()
        extra.setdefault("status", "active")
        extra.setdefault("role", role)
        return self._create(email, password, **extra)
