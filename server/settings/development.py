"""
Configuración de desarrollo local (comportamiento original).
"""
from .base import *  # noqa: F403

SECRET_KEY = "dev-secret-key-change-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

# En desarrollo los estáticos se sirven vía urls.static() apuntando a web/
