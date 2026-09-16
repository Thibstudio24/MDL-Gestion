from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChoresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chores"
    verbose_name = _("Planning de ménage")
