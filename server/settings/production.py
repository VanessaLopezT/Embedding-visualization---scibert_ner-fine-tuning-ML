"""
Configuración de producción (Docker / Gunicorn).
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

_DEV_SECRET = "dev-secret-key-change-in-production"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY or SECRET_KEY == _DEV_SECRET:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY debe definirse en producción (valor distinto al de desarrollo)."
    )

DEBUG = os.environ.get("DJANGO_DEBUG", "False").strip().lower() in ("1", "true", "yes")

_allowed = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").strip()
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS no puede estar vacío en producción.")

STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

_secure_ssl = os.environ.get("DJANGO_SECURE_SSL", "False").strip().lower() in (
    "1",
    "true",
    "yes",
)
SECURE_SSL_REDIRECT = _secure_ssl
SESSION_COOKIE_SECURE = _secure_ssl
CSRF_COOKIE_SECURE = _secure_ssl
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
