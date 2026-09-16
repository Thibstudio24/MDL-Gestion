"""Signaux du noyau (invalidation du cache de droits, réglages)."""
from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Setting


@receiver(post_save, sender=Setting)
def _flush_setting_cache(sender, instance, **kwargs):  # pragma: no cover - trivial
    Setting.flush()
