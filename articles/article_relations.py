"""
Grafo de relaciones para la vista de un solo artículo (panel).

Las rutas `/api/articles/<id>/relations` deben importar desde aquí para dejar claro que no es el
flujo multi-artículo del workspace. La lógica vive en `workspace_relations` porque comparte
aristas, modo «ambos» y opciones con el grafo de workspace.
"""

from .workspace_relations import build_article_relations

__all__ = ["build_article_relations"]
