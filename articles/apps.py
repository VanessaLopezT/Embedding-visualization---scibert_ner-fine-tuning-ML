from __future__ import annotations

import os

from django.apps import AppConfig
from django.conf import settings


class ArticlesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "articles"

    def ready(self):
        if not _should_preload_models():
            return

        from .processing_runtime import preload_registered_models

        preload_registered_models()


def _should_preload_models() -> bool:
    run_main = os.environ.get("RUN_MAIN")
    if settings.DEBUG:
        return run_main == "true"
    return True
