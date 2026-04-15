"""
Registro centralizado de modelos soportados por la aplicacion.
"""

from django.conf import settings


MODEL_REGISTRY = {
    "tech": {
        "label": "TechBERT",
        "checkpoint": settings.MODEL_TECH_CHECKPOINT,
        "description": "TechBERT — BERT/SciBERT fine-tuned en literatura ML y NLP",
        "color_scheme": "blue",
    },
    "cmt": {
        "label": "PatVetBERT",
        "checkpoint": settings.MODEL_CMT_CHECKPOINT,
        "description": "PatVetBERT — BioBERT/biomedical-ner-all fine-tuned en oncologia veterinaria",
        "color_scheme": "green",
    },
}
