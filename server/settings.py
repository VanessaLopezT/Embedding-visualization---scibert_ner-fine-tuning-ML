"""
Django settings — SciBERT / PubMedBERT dual-model NER visualization app.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-secret-key-change-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "articles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "server.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    }
]

WSGI_APPLICATION = "server.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "web"]

# Directorio de datos (artículos procesados y datos de ejemplo)
DATA_DIR = BASE_DIR / "data"

# ─────────────────────────────────────────────────────────────
# MODEL CHECKPOINTS
# Rutas relativas a BASE_DIR (o absolutas).
# ─────────────────────────────────────────────────────────────

# Modelo ML / Technology (SciBERT fine-tuned)
MODEL_TECH_CHECKPOINT = r"scibert_20260304_171958\best_model"

# Modelo Canine Mammary Tumor (PubMedBERT fine-tuned)
MODEL_CMT_CHECKPOINT = r"biobert_20260304_200826\best_model"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
