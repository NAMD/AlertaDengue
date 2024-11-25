"""
Django settings for AlertaDengue project.
"""

import os
from pathlib import Path
from typing import Optional

import ibis
import sentry_sdk
from django.contrib.messages import constants as messages
from dotenv import load_dotenv
from sentry_sdk.integrations.django import DjangoIntegration
from sqlalchemy import create_engine

# using existing module to specify location of the .env file
load_dotenv()
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


def read_admins(value):
    # ADMIN in settings.ini should be in the format:
    # admin 1, admin1@example.org; admin 2, admin2@example.org
    if value == "":
        return tuple()
    return tuple(tuple(v.split(",")) for v in value.split(";"))


ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent.parent

# AlertaDengue/
APPS_DIR = ROOT_DIR / "AlertaDengue"

# GENERAL
# ------------------------------------------------------------------------------

# You must set settings.ALLOWED_HOSTS if DEBUG is False
ADMINS = tuple(v.split(":") for v in os.getenv("ADMINS").split(","))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")

# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = os.getenv("DEBUG", "").lower() == "true"

ALLOWED_HOSTS = (
    os.getenv("ALLOWED_HOSTS").split(",") if os.getenv("ALLOWED_HOSTS") else []
)
# if True the maintenance-mode will be activated
MAINTENANCE_MODE = None

MAINTENANCE_MODE_TEMPLATE = str(APPS_DIR / "dados/templates/503.html")

# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "UTC"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "pt-br"
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(APPS_DIR / "locale")]
# Internationalization
LANGUAGES = (("pt-br", "Português"), ("en-us", "english"), ("es", "Spanish"))

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.admindocs",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "leaflet",
    "bootstrap4",
    "chunked_upload",
    "manager.router",
    "maintenance_mode",
    "django_celery_results",
    "django_celery_beat",
]

LOCAL_APPS = [
    "dados",
    "gis",
    "forecast",
    "dbf.apps.DbfConfig",
    "api",
    "upload",
]

# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = (
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.cache.UpdateCacheMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.cache.FetchFromCacheMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "maintenance_mode.middleware.MaintenanceModeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
)

if DEBUG:
    INSTALLED_APPS += ("django_extensions",)
    MIDDLEWARE += ("django_cprofile_middleware.middleware.ProfilerMiddleware",)
    DJANGO_CPROFILE_MIDDLEWARE_REQUIRE_STAFF = False


MESSAGE_TAGS = {
    messages.DEBUG: "alert-secondary",
    messages.INFO: "alert-info",
    messages.SUCCESS: "alert-success",
    messages.WARNING: "alert-warning",
    messages.ERROR: "alert-danger",
}


# URLS
# ------------------------------------------------------------------------------
ROOT_URLCONF = "ad_main.urls"
WSGI_APPLICATION = "ad_main.wsgi.application"
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
PSQL_DB = os.getenv("PSQL_DB")
PSQL_DBF = os.getenv("PSQL_DBF")
PSQL_USER = os.getenv("PSQL_USER")
PSQL_HOST = os.getenv("PSQL_HOST")
PSQL_PASSWORD = os.getenv("PSQL_PASSWORD")
PSQL_PORT = os.getenv("PSQL_PORT")

DATABASE_ROUTERS = ["manager.router.DatabaseAppsRouter"]

DATABASE_APPS_MAPPING = {
    "dados": "dados",
    "default": "default",
    "dbf": "infodengue",
    "forecast": "forecast",
}

DB_CONN_MAX_AGE = int(os.getenv("DB_CONN_MAX_AGE", "3600"))  # Time to keep the connection open (in seconds)
DATABASES = {
    "dados": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": PSQL_DB,
        "USER": PSQL_USER,
        "PASSWORD": PSQL_PASSWORD,
        "HOST": PSQL_HOST,
        "PORT": PSQL_PORT,
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
    },
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": PSQL_DB,
        "USER": PSQL_USER,
        "PASSWORD": PSQL_PASSWORD,
        "HOST": PSQL_HOST,
        "PORT": PSQL_PORT,
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
    },
    "infodengue": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": PSQL_DBF,
        "USER": PSQL_USER,
        "PASSWORD": PSQL_PASSWORD,
        "HOST": PSQL_HOST,
        "PORT": PSQL_PORT,
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
    },
    "forecast": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": PSQL_DB,
        "USER": "forecast",
        "PASSWORD": PSQL_PASSWORD,
        "HOST": PSQL_HOST,
        "PORT": PSQL_PORT,
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
    },
}


def get_ibis_conn(database: Optional[str] = PSQL_DB):
    """
    Returns:
        IBIS_CONN: Driver connection for Ibis.
    """
    try:
        connection = ibis.postgres.connect(
            user=PSQL_USER,
            password=PSQL_PASSWORD,
            host=PSQL_HOST,
            port=PSQL_PORT,
            database=database
        )

    except ConnectionError as e:
        print("Database error for Ibis connection")
        raise e
    return connection


def get_sqla_conn(database: Optional[str] = PSQL_DB):
    """
    Returns:
        DB_ENGINE: URI with driver connection.
    """
    try:
        connection = create_engine(
            f"postgresql://{PSQL_USER}:{PSQL_PASSWORD}@{PSQL_HOST}:{PSQL_PORT}/{database}"
        )

    except ConnectionError as e:
        print("Database error for SQLAlchemy connection")
        raise e
    return connection


MIGRATION_MODULES = {"dados": None, "gis": None, "api": None}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-browser-xss-filter
SECURE_BROWSER_XSS_FILTER = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "SAMEORIGIN"
# HTTP redirect is issued to the same URL
APPEND_SLASH = True

# EMAIL
# ------------------------------------------------------------------------------
# Console backend writes to stdout.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")
if EMAIL_BACKEND != "django.core.mail.backends.console.EmailBackend":
    EMAIL_HOST = os.getenv("EMAIL_HOST")
    EMAIL_PORT = os.getenv("EMAIL_PORT")
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = True

# SEND_MAIL DBF
EMAIL_CONNECTIONS = {
    "gmail": {
        "host": "smtp.gmail.com",
        "username": os.getenv("EMAIL_HOST_USER"),
        "password": os.getenv("EMAIL_HOST_PASSWORD"),
        "port": os.getenv("EMAIL_PORT"),
        "use_tls": False,
    },
    "outlook": {
        "host": "imap-mail.outlook.com",
        "username": os.getenv("EMAIL_OUTLOOK_USER"),
        "password": os.getenv("EMAIL_OUTLOOK_PASSWORD"),
        "port": os.getenv("EMAIL_PORT"),
        "use_tls": True,
    },
    "ses": {"backend": "django_ses.SESBackend"},
}
EMAIL_CONNECTION_DEFAULT = os.getenv("EMAIL_CONNECTION_DEFAULT")

# Uses the same credentials from email backend
EMAIL_FROM_USER = os.getenv("EMAIL_FROM_USER")
EMAIL_TO_ADDRESS = os.getenv("EMAIL_TO_ADDRESS")
EMAIL_OUTLOOK_USER = os.getenv("EMAIL_OUTLOOK_USER")

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(ROOT_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
# MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/img/"

# used to upload dbf
DBF_SINAN = os.getenv("DBF_SINAN")
MEDIA_ROOT = os.getenv("MEDIA_ROOT")
IMPORTED_FILES = os.getenv("IMPORTED_FILES")
TEMP_FILES_DIR = os.getenv("TEMP_FILES_DIR")

# Storage destination path between production and development are not the same
DATA_DIR = APPS_DIR.parent.parent / os.getenv("STORAGE")

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "maintenance_mode.context_processors.maintenance_mode",
            ],
        },
    }
]

# PATHS TO APPS
# ------------------------------------------------------------------------------
MAPSERVER_URL = os.getenv("MAPSERVER_URL")
MAPSERVER_LOG_PATH = os.getenv("MAPSERVER_LOG_PATH")

SHAPEFILE_PATH = os.getenv("SHAPEFILE_PATH")
MAPFILE_PATH = os.getenv("MAPFILE_PATH")

RASTER_PATH = os.getenv("RASTER_PATH")  # , str(ROOT_DIR / "tiffs"

RASTER_METEROLOGICAL_DATA_RANGE = {
    "ndvi": (-2000.0, +10000.0),
    "lst_day_1km": (0.0, 20000.0),
    "lst_night_1km": (-30.0, 30.0),
    "relative_humidity_2m_above_ground": (0.0, 100.0),
    "specific_humidity_2m_above_ground": (0.0, 1.0),
    "precipitation": (0, 200.0),
}
RASTER_METEROLOGICAL_FACTOR_INCREASE = os.getenv(
    "RASTER_METEROLOGICAL_FACTOR_INCREASE"
)  # VERIFICAR , default=4

# CACHES
# ------------------------------------------------------------------------------
MEMCACHED_HOST = os.getenv("MEMCACHED_HOST")
MEMCACHED_PORT = os.getenv("MEMCACHED_PORT")
QUERY_CACHE_TIMEOUT = int(os.getenv("QUERY_CACHE_TIMEOUT"))
CACHE_MIDDLEWARE_ALIAS = "default"
CACHE_MIDDLEWARE_SECONDS = 600
CACHE_MIDDLEWARE_KEY_PREFIX = "_"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.memcached.PyMemcacheCache",
        "LOCATION": f"{MEMCACHED_HOST}:{MEMCACHED_PORT}",
        "OPTIONS": {
            "no_delay": True,
            "ignore_exc": True,
            "max_pool_size": 4,
            "use_pooling": True,
        },
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "null": {"class": "logging.NullHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.security.DisallowedHost": {
            "handlers": ["null"],
            "propagate": False,
        }
    },
}

# CELERY
# ------------------------------------------------------------------------------
broker_url = os.getenv("CELERY_BROKER_URL")
broker_connection_retry = True
task_always_eager = os.getenv("CELERY_TASK_ALWAYS_EAGER")
accept_content = ["json"]
task_serializer = "json"
result_backend = f"cache+memcached://{MEMCACHED_HOST}:{MEMCACHED_PORT}/"
broker_connection_retry_on_startup = True


# broker_connection_retry_on_startup to True
# BOOTSTRAP4
# ------------------------------------------------------------------------------
# https://django-bootstrap4.readthedocs.io/en/latest/settings.html
BOOTSTRAP4 = {
    "form_renderers": {
        "default": "dbf.forms.FormRendererWithHiddenFieldErrors"
    }
}

# LEAFLET
# ------------------------------------------------------------------------------
LEAFLET_CONFIG = {
    # 'SPATIAL_EXTENT': (),
    "DEFAULT_CENTER": (-22.907000, -43.431000),
    "DEFAULT_ZOOM": 8,
    "MAXIMUM_ZOOM": 13,
    # 'http://{s}.tile.opencyclemap.org/cycle/{z}/{x}/{y}.png',
    "TILES": "http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "MINIMAP": False,
    "ATTRIBUTION_PREFIX": (
        "Fonte: <a href=http://info.dengue.mat.br>info.dengue.mat.br</a>"
    ),
    "PLUGINS": {
        "cluster": {
            "js": "js/leaflet.markercluster.js",
            "css": ["css/MarkerCluster.Default.css", "css/MarkerCluster.css"],
            "auto-include": True,
        },
        "heatmap": {
            "js": [
                "libs/heatmap/heatmap.js",
                "libs/heatmap/leaflet-heatmap.js",
                "js/QuadTree.js",
            ]
        },
    },
    "RESET_VIEW": False,
}

# MINIO
# ------------------------------------------------------------------------------
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME")

# Sentry
# ------------------------------------------------------------------------------
SENTRY_DSN = os.getenv("SENTRY_DSN", default=None)
if SENTRY_DSN:
    sentry_sdk.init(
        SENTRY_DSN,
        integrations=[DjangoIntegration()],
        send_default_pii=True,
    )
