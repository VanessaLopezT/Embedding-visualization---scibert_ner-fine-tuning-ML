"""
Compatibilidad: `server.settings` sigue siendo el módulo por defecto en desarrollo local.
"""
from server.settings.development import *  # noqa: F403
