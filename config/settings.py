"""Réglages de MDL Gestion.

La configuration est lue dans ``config/instance.json`` (posé par l'assistant
d'installation ou par ``install.py``). Les variables d'environnement
``MDL_*`` sont toujours prioritaires — c'est ce qui permet de coller les
réglages dans le panneau alwaysdata sans toucher au fichier.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
INSTANCE_FILE = CONFIG_DIR / "instance.json"


def _read_instance() -> dict:
    try:
        with open(INSTANCE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


_INSTANCE = _read_instance()


def read_instance() -> dict:
    """Contenu courant de config/instance.json (lecture publique pour l'assistant)."""
    return dict(_read_instance())
_TRUE = {"1", "true", "oui", "yes", "on"}
_FALSE = {"0", "false", "non", "no", "off"}


def _coerce(raw: str, default):
    if isinstance(default, bool):
        return raw.strip().lower() in _TRUE if raw.strip().lower() in _TRUE | _FALSE else bool(raw)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(raw)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    if isinstance(default, list):
        return [x.strip() for x in raw.split(",") if x.strip()]
    return raw


def cfg(section: str, key: str, default=None, env: str | None = None):
    """Lit un réglage : environnement d'abord, puis instance.json, puis défaut."""
    env_name = env or "MDL_%s" % key.upper()
    if env_name in os.environ and os.environ[env_name] != "":
        return _coerce(os.environ[env_name], default)
    value = (_INSTANCE.get(section) or {}).get(key, None)
    return default if value is None else value


def cfg_section(section: str) -> dict:
    return dict(_INSTANCE.get(section) or {})


def installed() -> bool:
    return bool((_INSTANCE.get("meta") or {}).get("installed")) or cfg("app", "installed", False, "MDL_INSTALLED")


def write_instance(data: dict, chmod: int = 0o600) -> None:
    """Écrit config/instance.json en UTF-8, droits 600."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INSTANCE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.chmod(tmp, chmod)
    os.replace(tmp, INSTANCE_FILE)
    global _INSTANCE
    _INSTANCE = data


# --------------------------------------------------------------------------- #
# Identité
# --------------------------------------------------------------------------- #
#: Valeur publique du dépôt. Elle n'est acceptable que le temps de l'installation :
#: l'assistant la remplace dès l'étape 2 (« identité »). Quiconque la connaît peut
#: forger un cookie de session, donc aucune session ne doit être ouverte avec.
DEFAULT_SECRET_KEY = "dev-insecure-change-me"
SECRET_KEY = cfg("security", "secret_key", DEFAULT_SECRET_KEY, "MDL_SECRET_KEY")
DEBUG = cfg("app", "debug", False, "MDL_DEBUG")
ALLOWED_HOSTS = cfg("app", "allowed_hosts", ["*"], "MDL_ALLOWED_HOSTS")
if isinstance(ALLOWED_HOSTS, str):
    ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS.split(",") if h.strip()]
BASE_URL = cfg("app", "base_url", "", "MDL_BASE_URL")

# L'application est servie en HTTPS uniquement (sous-domaine *.alwaysdata.net)

VERSION = "1.0.0"
try:
    VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() or VERSION
except OSError:  # pragma: no cover
    pass

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "audit.apps.AuditConfig",
    "notifications.apps.NotificationsConfig",
    "documents.apps.DocumentsConfig",
    "finance.apps.FinanceConfig",
    "plannings.apps.PlanningsConfig",
    "chores.apps.ChoresConfig",
    "mail.apps.MailConfig",
    "installer.apps.InstallerConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.MaintenanceModeMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.RequireLoginMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "core.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.association",
                "core.context_processors.theme",
                "core.context_processors.nav",
            ],
            "builtins": ["core.templatetags.ui"],
        },
    },
]

# --------------------------------------------------------------------------- #
# Base de données (sqlite par défaut, PostgreSQL/MariaDB en production)
# --------------------------------------------------------------------------- #
DB_ENGINE = cfg("database", "engine", "sqlite", "MDL_DB_ENGINE")
_ENGINES = {
    "sqlite": "django.db.backends.sqlite3",
    "postgres": "django.db.backends.postgresql",
    "postgresql": "django.db.backends.postgresql",
    "mysql": "django.db.backends.mysql",
    "mariadb": "django.db.backends.mysql",
}
DATABASES = {
    "default": {
        "ENGINE": _ENGINES.get(str(DB_ENGINE).lower(), "django.db.backends.sqlite3"),
        "NAME": cfg("database", "name", str(BASE_DIR / "db.sqlite3"), "MDL_DB_NAME"),
        "USER": cfg("database", "user", "", "MDL_DB_USER"),
        "PASSWORD": cfg("database", "password", "", "MDL_DB_PASSWORD"),
        "HOST": cfg("database", "host", "", "MDL_DB_HOST"),
        "PORT": str(cfg("database", "port", "", "MDL_DB_PORT") or ""),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {},
    }
}
if str(DB_ENGINE).lower() in ("mysql", "mariadb"):
    try:  # PyMySQL évite la compilation de mysqlclient sur alwaysdata
        import pymysql

        pymysql.install_as_MySQLdb()
    except ImportError:  # pragma: no cover
        pass
    DATABASES["default"]["OPTIONS"] = {"charset": "utf8mb4"}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --------------------------------------------------------------------------- #
# Sécurité
# --------------------------------------------------------------------------- #
SESSION_COOKIE_AGE = int(cfg("security", "session_days", 14, "MDL_SESSION_DAYS")) * 86400
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# En test, les requêtes passent par le client Django en HTTP : la redirection HTTPS
# et les cookies « Secure » rendraient toute page inaccessible (301 au lieu de 200).
TESTING = "pytest" in sys.modules or "test" in sys.argv
SESSION_COOKIE_SECURE = False if TESTING else cfg("security", "cookie_secure", not DEBUG,
                                                  "MDL_COOKIE_SECURE")
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = False if TESTING else cfg("security", "ssl_redirect", not DEBUG,
                                                "MDL_SSL_REDIRECT")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

PASSWORD_HASHERS = [
    "core.validators.MdlPBKDF2SHA256Hasher",
]
try:  # Argon2 s'il est présent sur le serveur
    import argon2  # noqa: F401

    PASSWORD_HASHERS.insert(0, "django.contrib.auth.hashers.Argon2PasswordHasher")
except ImportError:  # pragma: no cover
    pass

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "core.validators.MinLengthValidator"},
    {"NAME": "core.validators.CommonPasswordListValidator"},
    {"NAME": "core.validators.NumericPasswordValidator"},
    {"NAME": "core.validators.PersonalDataValidator"},
]

LOGIN_URL = "auth:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# --------------------------------------------------------------------------- #
# Internationalisation (interface française, formats FR)
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "fr"
TIME_ZONE = cfg("app", "timezone", "Europe/Paris", "MDL_TIME_ZONE")
USE_I18N = True
USE_TZ = True
DATE_FORMAT = "d/m/Y"
DATETIME_FORMAT = "d/m/Y H:i"
SHORT_DATE_FORMAT = "d/m/Y"
TIME_FORMAT = "H:i"
FIRST_DAY_OF_WEEK = 1
DECIMAL_SEPARATOR = ","
THOUSAND_SEPARATOR = "\u202f"
USE_THOUSAND_SEPARATOR = True
LANGUAGES = [("fr", "Français")]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --------------------------------------------------------------------------- #
# Fichiers
# --------------------------------------------------------------------------- #
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(cfg("app", "media_root", str(BASE_DIR / "media"), "MDL_MEDIA_ROOT"))
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_MIMETYPES = {
    ".webmanifest": "application/manifest+json",
    ".js": "text/javascript",
}
WHITENOISE_ALLOW_ALL_ORIGINS = False

DATA_UPLOAD_MAX_NUMBER_FIELDS = 3000
FILE_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

# --------------------------------------------------------------------------- #
# E-mails : file en base + cron (pas de Celery sur alwaysdata Free)
# --------------------------------------------------------------------------- #
MAIL_ENABLED = cfg("mail", "enabled", False, "MDL_EMAIL_ENABLED")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if MAIL_ENABLED and not DEBUG
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = cfg("mail", "host", "localhost", "MDL_EMAIL_HOST")
EMAIL_PORT = int(cfg("mail", "port", 587, "MDL_EMAIL_PORT"))
EMAIL_HOST_USER = cfg("mail", "user", "", "MDL_EMAIL_USER")
EMAIL_HOST_PASSWORD = cfg("mail", "password", "", "MDL_EMAIL_PASSWORD")
EMAIL_USE_SSL = cfg("mail", "use_ssl", EMAIL_PORT == 465, "MDL_EMAIL_SSL")
EMAIL_USE_TLS = cfg("mail", "use_tls", EMAIL_PORT == 587, "MDL_EMAIL_TLS")
DEFAULT_FROM_EMAIL = cfg("mail", "from", "mdl@localhost", "MDL_EMAIL_FROM")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_SUBJECT_PREFIX = ""
MAIL_RATE_PER_MINUTE = int(cfg("mail", "rate_per_minute", 15, "MDL_EMAIL_RATE"))

# --------------------------------------------------------------------------- #
# Cache, tests, logs
# --------------------------------------------------------------------------- #
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mdl",
        "TIMEOUT": 300,
    }
}
TEST_RUNNER = "core.test_runner.MdlTestRunner"
LOGGING_CONFIG = None
import logging.config  # noqa: E402

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"simple": {"format": "[mdl] %(levelname)s %(name)s %(message)s"}},
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
        "root": {"handlers": ["console"], "level": "WARNING"},
        "loggers": {"mdl": {"handlers": ["console"], "level": "INFO", "propagate": False}},
    }
)
LOG = logging.getLogger("mdl")

# --------------------------------------------------------------------------- #
# Push (Web Push / VAPID)
# --------------------------------------------------------------------------- #
PUSH_ENABLED = cfg("push", "enabled", True, "MDL_PUSH_ENABLED")
VAPID_PUBLIC_KEY = cfg("push", "public_key", "", "MDL_VAPID_PUBLIC")
VAPID_PRIVATE_KEY = cfg("push", "private_key", "", "MDL_VAPID_PRIVATE")
VAPID_CLAIMS_EMAIL = cfg("push", "claims_email", "mdl@localhost", "MDL_VAPID_CLAIMS_EMAIL")

# --------------------------------------------------------------------------- #
# Hub éditeur
# --------------------------------------------------------------------------- #
HUB_URL = cfg("hub", "url", "", "MDL_HUB_URL")
HUB_INSTALL_ID = cfg("hub", "install_id", "", "MDL_HUB_INSTALL_ID")
HUB_INSTALL_SECRET = cfg("hub", "install_secret", "", "MDL_HUB_INSTALL_SECRET")
HUB_TELEMETRY = cfg("hub", "telemetry", False, "MDL_HUB_TELEMETRY")
GITHUB_REPO = cfg("hub", "github_repo", "Thibstudio24/MDL-Gestion", "MDL_GITHUB_REPO")
GITHUB_TOKEN = cfg("hub", "github_token", "", "MDL_GITHUB_TOKEN")

# --------------------------------------------------------------------------- #
# Réglages internes à l'application
# --------------------------------------------------------------------------- #
MDL_PASSWORD_MIN_LENGTH = int(cfg("security", "password_min_length", 10, "MDL_PASSWORD_MIN_LENGTH"))
MDL_LOGIN_MAX_ATTEMPTS = int(cfg("security", "login_max_attempts", 5, "MDL_LOGIN_MAX_ATTEMPTS"))
MDL_LOGIN_LOCKOUT_MINUTES = int(cfg("security", "login_lockout_minutes", 15, "MDL_LOGIN_LOCKOUT_MINUTES"))
MDL_REAUTH_MINUTES = int(cfg("security", "reauth_minutes", 10, "MDL_REAUTH_MINUTES"))
MDL_AUDIT_KEEP_YEARS = int(cfg("security", "audit_keep_years", 5, "MDL_AUDIT_KEEP_YEARS"))
MDL_TEST_ENVIRONMENT_CHECK = cfg("app", "test_environment_check", True, "MDL_TEST_CHECK")
MDL_PUBLIC_URLS = (
    "/connexion/", "/mot-de-passe/oubli/", "/reinitialiser/", "/inviter/", "/installation/",
    "/theme.css", "/manifest.webmanifest", "/service-worker.js", "/hors-ligne/", "/sante/",
    "/favicon.ico", "/robots.txt", "/static/",
)

MAINTENANCE = cfg("app", "maintenance", False, "MDL_MAINTENANCE")
MAINTENANCE_MESSAGE = cfg("app", "maintenance_message", "", "MDL_MAINTENANCE_MESSAGE")

DEFAULT_CHARSET = "utf-8"
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
