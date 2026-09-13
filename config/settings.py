import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-kryptolens-secret")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = [item.strip() for item in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if item.strip()]
CSRF_TRUSTED_ORIGINS = [
    item.strip()
    for item in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080",
    ).split(",")
    if item.strip()
]

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

database_url = os.getenv("DATABASE_URL", "")
if database_url.startswith("postgres"):
    import urllib.parse as urlparse

    parsed = urlparse.urlparse(database_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/"
LOGIN_REDIRECT_URL = "/home"
LOGOUT_REDIRECT_URL = "/"

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
EVENT_COOLDOWN_MINUTES = int(os.getenv("EVENT_COOLDOWN_MINUTES", "60"))
APP_EMAIL = os.getenv("APP_EMAIL") or os.getenv("DEMO_EMAIL", "operator@kryptolens.app")
APP_PASSWORD = os.getenv("APP_PASSWORD") or os.getenv("DEMO_PASSWORD", "kryptolens-operator")
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
