import ipaddress
import os
from decouple import Csv, config
from pathlib import Path
from django.core.management.utils import get_random_secret_key

from dStats.engines import engine_names


def is_auth_enabled():
    HAS_USE_AUTH = config("USE_AUTH", "false").lower() in ("true", "1", "yes")
    HAS_AUTH_USERNAME = config("AUTH_USERNAME", None)
    HAS_AUTH_PASSWORD = config("AUTH_PASSWORD", None)

    if HAS_USE_AUTH and HAS_AUTH_USERNAME and HAS_AUTH_PASSWORD:
        data = True
    else:
        data = False
    # print(f"Auth enabled: {data}")
    return data


# Fail at startup on a typo like DSTATS_ENGINE=podmn, not on the first request
DSTATS_ENGINES = engine_names()


def listen_host():
    """Interface the server binds to: only this machine unless a login protects it."""
    return config(
        "DSTATS_HOST", default="0.0.0.0" if is_auth_enabled() else "127.0.0.1"
    )


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def default_allowed_hosts():
    # Without a login on a local-only server, accept only localhost names, so a
    # malicious web page can't reach dStats through DNS rebinding
    if is_auth_enabled() or not is_loopback(listen_host()):
        return "*"
    return "localhost,127.0.0.1,[::1]"


# Random per start unless set, so sessions end when the server restarts
SECRET_KEY = config("SECRET_KEY", default="") or get_random_secret_key()

# Never on by default: debug pages expose settings and stack traces to visitors
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default=default_allowed_hosts(), cast=Csv())

# Needed when dStats is served over HTTPS behind a reverse proxy, e.g. https://stats.example.com
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Turn on when serving over HTTPS so cookies are never sent over plain HTTP
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = config(
    "SECURE_COOKIES", default=False, cast=bool
)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dStats",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dStats.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "dStats.asgi.application"

if is_auth_enabled():
    INSTALLED_APPS.append("authboot")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "dStats.sqlite3",
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
