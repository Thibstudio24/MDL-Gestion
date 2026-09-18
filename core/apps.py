from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = _("Noyau")

    def ready(self):  # pragma: no cover - chargement des signaux
        from . import signals  # noqa: F401
