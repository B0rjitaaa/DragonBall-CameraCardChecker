import os
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(int(default))).lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "*")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
# Nginx indica si la petición llegó por HTTPS: así las URLs absolutas (fotos de
# los escaneos) salen con https:// y Safari no las bloquea por contenido mixto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "cards",
    "scans",
    "collection",
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

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Sin POSTGRES_HOST (p. ej. `make test`) se usa SQLite.
if env("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "dbs"),
            "USER": env("POSTGRES_USER", "dbs"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "HOST": env("POSTGRES_HOST"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "es-es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Las subidas de escaneos se procesan en memoria antes de guardarse.
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 30,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    # Uso en red local sin cuentas de usuario (v1).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

# --- Celery ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
# Reintentar la conexión con Redis al arrancar (Redis puede tardar más en la Pi).
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_RESULT_EXPIRES = 3600
# Cada cuántos segundos se "toca" el pipeline para que no acabe en swap (0 = nunca).
KEEP_WARM_SECONDS = int(env("KEEP_WARM_SECONDS", "60"))
CELERY_BEAT_SCHEDULE = {
    "sync-bandai-catalog": {
        "task": "cards.tasks.sync_bandai_catalog",
        "schedule": crontab(hour=int(env("BANDAI_SYNC_HOUR", "4")), minute=0),
    },
    **(
        {
            "keep-worker-warm": {
                "task": "scans.tasks.keep_warm",
                "schedule": KEEP_WARM_SECONDS,
                # Si el worker está ocupado, no acumular ejecuciones atrasadas.
                "options": {"expires": KEEP_WARM_SECONDS * 0.8},
            }
        }
        if KEEP_WARM_SECONDS > 0
        else {}
    ),
    "cleanup-old-scans": {
        "task": "scans.tasks.cleanup_old_scans",
        "schedule": crontab(hour=5, minute=0, day_of_week="mon"),
    },
}

# --- Catálogo Bandai ---
BANDAI_API_URL = env("BANDAI_API_URL", "")
BANDAI_GAME_TITLE_ID = env("BANDAI_GAME_TITLE_ID", "")
BANDAI_PAGE_SIZE = int(env("BANDAI_PAGE_SIZE", "100"))

# Caché local de imágenes oficiales (volumen ./data, ver cards/images.py).
CARD_IMAGES_DIR = env("CARD_IMAGES_DIR", str(BASE_DIR / "data" / "card_images"))

# --- Identificación ---
MATCH_HASH_THRESHOLD = int(env("MATCH_HASH_THRESHOLD", "20"))
MATCH_ORB_CANDIDATES = int(env("MATCH_ORB_CANDIDATES", "8"))
MATCH_MIN_CONFIDENCE = float(env("MATCH_MIN_CONFIDENCE", "0.55"))
SCAN_RETENTION_DAYS = int(env("SCAN_RETENTION_DAYS", "30"))

# --- Cámara ---
CAMERA_URL = env("CAMERA_URL", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
