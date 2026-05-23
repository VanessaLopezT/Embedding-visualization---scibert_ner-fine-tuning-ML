"""
Configuración Django compartida (desarrollo y producción).
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "articles.apps.ArticlesConfig",
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

_data_dir = os.environ.get("DATA_DIR", "").strip()
DATA_DIR = Path(_data_dir) if _data_dir else BASE_DIR / "data"

# Modelo ML / Technology (SciBERT fine-tuned)
MODEL_TECH_CHECKPOINT = os.environ.get("MODEL_TECH_CHECKPOINT", r"TechBERT\best_model")

# Modelo Canine Mammary Tumor (PubMedBERT fine-tuned)
MODEL_CMT_CHECKPOINT = os.environ.get("MODEL_CMT_CHECKPOINT", r"PatVetBERT\best_model")

PROCESSING_MAX_ACTIVE_JOBS = int(os.environ.get("PROCESSING_MAX_ACTIVE_JOBS", "1"))
PROCESSING_WORKER_IDLE_SECONDS = int(os.environ.get("PROCESSING_WORKER_IDLE_SECONDS", "600"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
