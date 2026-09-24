import os
import re
import socket
import sys
import urllib.parse as urlparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-kryptolens-secret")
_ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PUBLIC_DOMAIN"))
DEBUG = os.getenv("DEBUG", "0" if _ON_RAILWAY else "1") == "1"


def _csv_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = _csv_env(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080",
)
for _host in (
    os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip(),
    os.getenv("RAILWAY_PRIVATE_DOMAIN", "").strip(),
):
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)
    if _host:
        _origin = f"https://{_host}"
        if _origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_origin)
if _ON_RAILWAY:
    for _suffix in (".railway.app", ".up.railway.app", ".railway.internal"):
        if _suffix not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_suffix)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    if os.getenv("PUBLIC_BASE_URL", "").startswith("https://"):
        CSRF_TRUSTED_ORIGINS.append(os.getenv("PUBLIC_BASE_URL", "").rstrip("/"))
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.users.apps.UsersConfig",
    "apps.lenses.apps.LensesConfig",
    "apps.intelligence.apps.IntelligenceConfig",
    "apps.monitoring.apps.MonitoringConfig",
    "apps.events.apps.EventsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.cmc.apps.CmcConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "users.User"

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
                "apps.users.context_processors.agent_status",
            ],
        },
    }
]

def _sqlite_default():
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


def _database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip().strip("'\"")


def _supabase_ipv4_url(database_url: str) -> str:
    """Direct db.<ref>.supabase.co hosts are IPv6-only. Use the IPv4 pooler when needed."""
    parsed = urlparse.urlparse(database_url)
    host = parsed.hostname or ""
    match = re.fullmatch(r"db\.([a-z0-9]+)\.supabase\.co", host)
    if not match:
        return database_url
    try:
        socket.getaddrinfo(host, parsed.port or 5432, socket.AF_INET)
        return database_url
    except OSError:
        pass
    ref = match.group(1)
    pooler = os.getenv("SUPABASE_POOLER_HOST", "aws-1-eu-west-1.pooler.supabase.com")
    user = f"postgres.{ref}"
    password = urlparse.quote(urlparse.unquote(parsed.password or ""), safe="")
    return (
        f"{parsed.scheme}://{user}:{password}@{pooler}:6543/postgres?sslmode=require"
    )


def _postgres_from_url(database_url: str):
    parsed = urlparse.urlparse(_supabase_ipv4_url(database_url))
    query = dict(urlparse.parse_qsl(parsed.query))
    name = parsed.path.lstrip("/").split("?", 1)[0] or "postgres"
    host = parsed.hostname or ""
    port = parsed.port or 5432
    sslmode = query.get("sslmode")
    if not sslmode and "supabase" in host:
        sslmode = "require"
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": urlparse.unquote(parsed.username or ""),
        "PASSWORD": urlparse.unquote(parsed.password or ""),
        "HOST": host,
        "PORT": port,
        "CONN_MAX_AGE": 0 if port == 6543 else 60,
        "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": port == 6543,
    }
    if sslmode:
        config["OPTIONS"] = {"sslmode": sslmode}
    return config


def _sqlite_from_url(database_url: str) -> dict:
    parsed = urlparse.urlparse(database_url)
    name = parsed.path.lstrip("/") or str(BASE_DIR / "db.sqlite3")
    if parsed.netloc in {"", "relative"} and parsed.path:
        name = parsed.path
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": name,
    }


def _engine_from_url(database_url: str) -> dict:
    scheme = urlparse.urlparse(database_url).scheme.lower()
    if scheme in {"postgres", "postgresql", "pgsql"}:
        return _postgres_from_url(database_url)
    if scheme.startswith("sqlite"):
        return _sqlite_from_url(database_url)
    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme or 'missing'}")


def _running_tests() -> bool:
    if "pytest" in sys.modules:
        return True
    return len(sys.argv) > 1 and sys.argv[1] == "test"


def _default_database() -> dict:
    if _running_tests():
        return _sqlite_default()
    url = _database_url()
    if url:
        return _engine_from_url(url)
    if _ON_RAILWAY:
        raise ValueError("DATABASE_URL is required and is used as Django's default database.")
    return _sqlite_default()


DATABASES = {"default": _default_database()}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
_css_path = BASE_DIR / "static" / "css" / "app.css"
STATIC_VERSION = str(int(_css_path.stat().st_mtime)) if _css_path.exists() else "1"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/home"
LOGOUT_REDIRECT_URL = "/"
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "KryptoLens <noreply@kryptolens.app>")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "run-active-lenses": {
        "task": "apps.monitoring.tasks.run_active_lenses",
        "schedule": 15 * 60,
    }
}

CMC_API_KEY = os.getenv("CMC_API_KEY", "")
CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "composer-2.5")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
EVENT_COOLDOWN_MINUTES = int(os.getenv("EVENT_COOLDOWN_MINUTES", "60"))
MONITOR_INTERVAL_MINUTES = 15
SCORE_HIGH_MIN = int(os.getenv("SCORE_HIGH_MIN", "4"))
SCORE_MEDIUM_MIN = int(os.getenv("SCORE_MEDIUM_MIN", "2"))
SCORE_STRONG_MOVE_MULTIPLIER = float(os.getenv("SCORE_STRONG_MOVE_MULTIPLIER", "2"))
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") == "1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(name)s %(levelname)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "kryptolens": {"handlers": ["console"], "level": "INFO"},
    },
}
