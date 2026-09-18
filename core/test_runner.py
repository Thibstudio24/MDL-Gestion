"""Runner de test : refuse de tourner hors SQLite ou avec DEBUG actif."""
from __future__ import annotations

import sys

from django.conf import settings
from django.test.runner import DiscoverRunner


class MdlTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        engine = str(settings.DATABASES["default"].get("ENGINE", ""))
        if settings.MDL_TEST_ENVIRONMENT_CHECK and not engine.endswith("sqlite3"):
            sys.stderr.write(
                "\n[mdl] Tests refusés : MDL_DB_ENGINE doit valoir « sqlite » pour la suite de tests "
                "(moteur courant : %s).\n" % engine
            )
            raise SystemExit(2)
        if settings.MDL_TEST_ENVIRONMENT_CHECK and settings.DEBUG:
            sys.stderr.write("\n[mdl] Tests refusés : DEBUG doit être désactivé pendant les tests.\n")
            raise SystemExit(2)
        return super().setup_databases(**kwargs)
