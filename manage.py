#!/usr/bin/env python
"""Django manage.py para el proyecto SciBERT NER integrado."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Asegúrate de tenerlo instalado "
            "y de que el entorno virtual esté activo."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
