from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InstallerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "installer"
    verbose_name = _("Assistant d'installation")
