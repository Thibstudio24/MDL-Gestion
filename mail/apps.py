from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mail"
    verbose_name = _("Messagerie interne")

    def ready(self):
        """Démarre la pompe SMTP, sauf en test ou si désactivée.

        Sous runserver, seul le processus fils (RUN_MAIN) pompe : le
        reloader ne doit pas doubler les envois.
        """
        import os
        import sys

        from django.conf import settings as s

        if getattr(s, "TESTING", False) or not getattr(s, "MAIL_PUMP", True):
            return
        if "runserver" in " ".join(sys.argv) and os.environ.get("RUN_MAIN") != "true":
            return
        from mail.pump import demarrer

        demarrer()
