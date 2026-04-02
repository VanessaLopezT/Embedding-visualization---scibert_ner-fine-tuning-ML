"""
Registro centralizado de modelos soportados por la aplicacion.
"""

from django.conf import settings


MODEL_REGISTRY = {
    "tech": {
        "label": "ML / Technology",
        "checkpoint": settings.MODEL_TECH_CHECKPOINT,
        "description": "SciBERT fine-tuned en literatura ML y NLP",
        "color_scheme": "blue",
    },
    "cmt": {
        "label": "Canine Mammary Tumor",
        "checkpoint": settings.MODEL_CMT_CHECKPOINT,
        "description": "PubMedBERT fine-tuned en oncologia veterinaria (CMT)",
        "color_scheme": "green",
    },
}
