"""
articles/views.py
Vistas Django para la app de visualización NER dual-modelo.

Modelos soportados:
  - "tech" : SciBERT fine-tuned en literatura ML/Tech
  - "cmt"  : PubMedBERT fine-tuned en oncología veterinaria (CMT)

Pipeline de procesamiento:
  - Extracción de PDF: mod_extractor (selección inteligente de motor)
  - Limpieza de secciones: mod_sections
  - Detección de tablas: mod_tables
  - Limpieza de símbolos: mod_symbols
  - Chunking BERT-compatible: mod_chunker
  - Fallback: prepare_article.ArticlePreprocessor
  - NER + embeddings: process_ner.SciBERTNERProcessor (optimizado RAM)
  - Proyección t-SNE/PCA: visualize_tsne_prepare
"""

import gc
import json
import os
import re
import sys
import threading
import traceback
import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# ─────────────────────────────────────────────────────────────
# RUTAS BASE
# ─────────────────────────────────────────────────────────────
DATA_DIR = settings.DATA_DIR
ARTICLES_DIR = DATA_DIR / "articles"
EXAMPLE_DIR = DATA_DIR / "example"
PROCESSING_DIR = settings.BASE_DIR / "processing"

ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# REGISTRO DE MODELOS
# ─────────────────────────────────────────────────────────────
MODEL_REGISTRY = {
    "tech": {
        "label": "ML / Technology",
        "checkpoint": settings.MODEL_TECH_CHECKPOINT,
        "example_tsne": EXAMPLE_DIR / "tsne_tech.json",
        "description": "SciBERT fine-tuned en literatura ML y NLP",
        "color_scheme": "blue",
    },
    "cmt": {
        "label": "Canine Mammary Tumor",
        "checkpoint": settings.MODEL_CMT_CHECKPOINT,
        "example_tsne": EXAMPLE_DIR / "tsne_cmt.json",
        "description": "PubMedBERT fine-tuned en oncología veterinaria (CMT)",
        "color_scheme": "green",
    },
}


# ─────────────────────────────────────────────────────────────
# HELPERS DE RUTAS Y METADATOS
# ─────────────────────────────────────────────────────────────

def _article_dir(article_id: str) -> Path:
    return ARTICLES_DIR / article_id


def _meta_path(article_id: str) -> Path:
    return _article_dir(article_id) / "meta.json"


def _progress_path(article_id: str) -> Path:
    return _article_dir(article_id) / "progress.json"


def _tsne_path(article_id: str, model_key: str) -> Path:
    return _article_dir(article_id) / f"tsne_{model_key}.json"


def _ner_path(article_id: str, model_key: str) -> Path:
    return _article_dir(article_id) / f"ner_{model_key}.json"


def _cleaned_text_path(article_id: str) -> Path:
    return _article_dir(article_id) / "cleaned_text.txt"


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_progress(article_id: str, payload: dict):
    try:
        _write_json(_progress_path(article_id), payload)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# VISTAS
# ─────────────────────────────────────────────────────────────

def index(request):
    return render(request, "index.html")


@require_http_methods(["GET"])
def get_models(request):
    """Devuelve la lista de modelos disponibles."""
    models = [
        {
            "key": k,
            "label": v["label"],
            "description": v["description"],
            "color_scheme": v["color_scheme"],
        }
        for k, v in MODEL_REGISTRY.items()
    ]
    return JsonResponse({"models": models})


@require_http_methods(["GET"])
def list_articles(request):
    """Lista todos los artículos con su estado actual."""
    articles = []
    if ARTICLES_DIR.exists():
        for d in sorted(ARTICLES_DIR.iterdir()):
            meta_file = d / "meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    articles.append({
                        "id": meta.get("id", d.name),
                        "original_name": meta.get("original_name", d.name),
                        "status": meta.get("status", "unknown"),
                        "model": meta.get("model", "tech"),
                    })
                except Exception:
                    pass
    return JsonResponse({"articles": articles})


@csrf_exempt
@require_http_methods(["POST"])
def upload_article(request):
    """
    Recibe un archivo PDF o TXT y lo procesa en background.

    Parámetros (multipart/form-data):
      - file  : el documento
      - model : "tech" | "cmt"  (por defecto: "tech")
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "No file provided"}, status=400)

    model_key = request.POST.get("model", "tech")
    if model_key not in MODEL_REGISTRY:
        return JsonResponse({"error": f"Modelo desconocido: '{model_key}'"}, status=400)

    suffix = Path(uploaded.name).suffix.lower()
    if suffix not in (".pdf", ".txt"):
        return JsonResponse({"error": "Solo se aceptan archivos .pdf y .txt"}, status=400)

    article_id = str(uuid.uuid4())[:8]
    article_dir = _article_dir(article_id)
    article_dir.mkdir(parents=True, exist_ok=True)

    raw_path = article_dir / f"raw{suffix}"
    with open(raw_path, "wb") as f:
        for chunk in uploaded.chunks():
            f.write(chunk)

    meta = {
        "id": article_id,
        "original_name": uploaded.name,
        "status": "queued",
        "stage": "queued",
        "model": model_key,
        "raw_file": str(raw_path),
        "error": None,
    }
    _write_json(_meta_path(article_id), meta)
    _write_progress(article_id, {"stage": "queued", "percent": 0, "processed": 0, "total": 0})

    thread = threading.Thread(
        target=_process_article_background,
        args=(article_id, raw_path, model_key),
        daemon=True,
    )
    thread.start()

    return JsonResponse({"article": meta})


@require_http_methods(["GET"])
def get_article_tsne(request, article_id):
    model_key = request.GET.get("model", "tech")
    tsne_file = _tsne_path(article_id, model_key)
    if not tsne_file.exists():
        return JsonResponse({"error": "Datos t-SNE no disponibles aún"}, status=404)
    data = json.loads(tsne_file.read_text(encoding="utf-8"))
    return JsonResponse({"data": data})


@require_http_methods(["GET"])
def get_article_ner(request, article_id):
    model_key = request.GET.get("model", "tech")
    ner_file = _ner_path(article_id, model_key)
    if not ner_file.exists():
        return JsonResponse({"error": "Resultados NER no disponibles aún"}, status=404)
    data = json.loads(ner_file.read_text(encoding="utf-8"))
    return JsonResponse({"results": data})


@require_http_methods(["GET"])
def get_article_meta(request, article_id):
    meta = _read_json(_meta_path(article_id))
    if not meta:
        return JsonResponse({"error": "Artículo no encontrado"}, status=404)
    progress = _read_json(_progress_path(article_id))

    # Extraer título del texto limpio
    title = _extract_title_from_cleaned_text(_cleaned_text_path(article_id))

    return JsonResponse({"article": meta, "progress": progress, "title": title})


@require_http_methods(["GET"])
def get_article_cleaned_text(request, article_id):
    cleaned_path = _cleaned_text_path(article_id)
    if not cleaned_path.exists():
        return JsonResponse({"error": "Texto limpio no disponible"}, status=404)
    try:
        text = cleaned_path.read_text(encoding="utf-8")
    except Exception:
        return JsonResponse({"error": "Error leyendo texto limpio"}, status=404)
    return JsonResponse({"text": text, "source": "article"})


@require_http_methods(["GET"])
def get_example_tsne(request):
    model_key = request.GET.get("model", "tech")
    example_file = MODEL_REGISTRY.get(model_key, MODEL_REGISTRY["tech"])["example_tsne"]
    if not example_file.exists():
        return JsonResponse({"data": []})
    data = json.loads(example_file.read_text(encoding="utf-8"))
    return JsonResponse({"data": data})


# ─────────────────────────────────────────────────────────────
# PIPELINE DE PROCESAMIENTO EN BACKGROUND
# ─────────────────────────────────────────────────────────────

def _process_article_background(article_id: str, raw_path: Path, model_key: str):
    """
    Pipeline completo:
      1. Extracción y limpieza (módulos modulares → fallback prepare_article)
      2. NER con el modelo seleccionado
      3. Proyección t-SNE / PCA
      4. Guardado de resultados
    """
    sys.path.insert(0, str(PROCESSING_DIR))

    meta = _read_json(_meta_path(article_id))
    checkpoint = MODEL_REGISTRY[model_key]["checkpoint"]

    try:
        # ── Etapa 1: Extracción y limpieza ──────────────────────────────
        _write_json(_meta_path(article_id), {**meta, "status": "processing", "stage": "processing"})
        _write_progress(article_id, {"stage": "processing", "percent": 10, "processed": 0, "total": 0})

        paragraphs, cleaned_text = _extract_and_clean(raw_path, article_id)

        if not paragraphs:
            raise ValueError("No se pudo extraer texto del documento.")

        # Guardar texto limpio para el panel de texto
        cleaned_path = _cleaned_text_path(article_id)
        cleaned_path.write_text(cleaned_text, encoding="utf-8")

        _write_progress(article_id, {
            "stage": "ner", "percent": 30,
            "processed": 0, "total": len(paragraphs),
        })

        # ── Etapa 2: NER ─────────────────────────────────────────────────
        _write_json(_meta_path(article_id), {**meta, "status": "processing", "stage": "ner"})

        from process_ner import SciBERTNERProcessor

        processor = SciBERTNERProcessor.__new__(SciBERTNERProcessor)
        _init_processor(processor, checkpoint)

        article_dir = _article_dir(article_id)
        ner_output = str(_ner_path(article_id, model_key))
        embeddings_output = str(article_dir / f"embeddings_{model_key}.npz")
        tsne_output = str(_tsne_path(article_id, model_key))
        progress_file = str(_progress_path(article_id))

        processor.process_texts(
            paragraphs,
            output_file=ner_output,
            entity_embeddings_file=embeddings_output,
            tsne_output=tsne_output,
            progress_file=progress_file,
        )
        processor.unload()
        del processor
        gc.collect()

        # ── Completado ───────────────────────────────────────────────────
        _write_json(_meta_path(article_id), {
            **meta,
            "status": "processed",
            "stage": "completed",
            "error": None,
        })

    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[ERROR] Procesando artículo {article_id}:\n{tb}")
        _write_json(_meta_path(article_id), {
            **meta,
            "status": "failed",
            "stage": "failed",
            "error": str(exc),
        })
        _write_progress(article_id, {"stage": "failed", "percent": 100, "error": str(exc)})


def _init_processor(processor, checkpoint_path: str):
    """Inicializa SciBERTNERProcessor con un checkpoint explícito."""
    import torch
    from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = Path(checkpoint_path)
    if not ckpt.is_absolute():
        ckpt = settings.BASE_DIR / checkpoint_path
    ckpt = ckpt.resolve()

    if not ckpt.exists():
        raise FileNotFoundError(f"Checkpoint no encontrado: {ckpt}")

    # En Windows, HuggingFace rechaza rutas absolutas con backslash.
    # Solución: hacer os.chdir() al directorio del checkpoint y cargar con ".".
    original_cwd = os.getcwd()
    try:
        os.chdir(str(ckpt))
        processor.device = device
        processor.tokenizer = AutoTokenizer.from_pretrained(".", local_files_only=True)
        # Forzar límite de 512 tokens — algunos checkpoints no lo declaran explícitamente
        processor.tokenizer.model_max_length = 512
        processor.model = AutoModelForTokenClassification.from_pretrained(".", local_files_only=True)
    finally:
        os.chdir(original_cwd)

    processor.model.to(device)
    processor.model.eval()
    processor.ner_pipeline = pipeline(
        "token-classification",
        model=processor.model,
        tokenizer=processor.tokenizer,
        device=0 if device == "cuda" else -1,
        aggregation_strategy="simple",
    )
    processor._loaded = True


def _extract_and_clean(raw_path: Path, article_id: str):
    """
    Pipeline modular de extracción y limpieza:
      mod_extractor → mod_sections → mod_tables → mod_symbols → mod_chunker

    Devuelve: (chunks: list[str], cleaned_text: str)
    Fallback: prepare_article.ArticlePreprocessor si el pipeline modular falla.
    """
    sys.path.insert(0, str(PROCESSING_DIR))
    suffix = raw_path.suffix.lower()

    try:
        from mod_extractor import extract_text
        from mod_sections import clean_all_sections
        from mod_tables import mark_tables
        from mod_symbols import clean_symbols
        from mod_chunker import chunk_text

        # 1. Extracción de texto
        if suffix == ".pdf":
            result = extract_text(str(raw_path))
            raw_text = result["text"] if result["success"] else ""
            print(f"  [extractor] motor={result['engine']} layout={result['layout']}")
        else:
            raw_text = raw_path.read_text(encoding="utf-8", errors="replace")

        if not raw_text.strip():
            raise ValueError("Extracción vacía")

        # 2. Limpieza de secciones (referencias, cabeceras, pies, figuras)
        text = clean_all_sections(raw_text)

        # 3. Marcado y eliminación de tablas
        text = mark_tables(text)
        import re
        text = re.sub(r"<<TABLE_START>>.*?<<TABLE_END>>", "", text, flags=re.DOTALL)

        # 4. Limpieza de símbolos y encoding
        text = clean_symbols(text)

        # 5. Chunking BERT-compatible
        chunks = chunk_text(text)
        chunks = [c for c in chunks if c.strip()]

        print(f"  [pipeline] {len(chunks)} chunks tras limpieza modular")
        return chunks, text

    except Exception as e:
        print(f"  [pipeline] Error en pipeline modular: {e}. Usando prepare_article como fallback.")

    # ── Fallback: prepare_article.ArticlePreprocessor ────────────────────
    try:
        from prepare_article import ArticlePreprocessor
        preprocessor = ArticlePreprocessor()
        if not preprocessor.load_article(str(raw_path)):
            return [], ""
        preprocessor.clean()
        paragraphs = preprocessor.get_paragraphs()
        cleaned_text = preprocessor.text
        print(f"  [fallback] {len(paragraphs)} párrafos desde prepare_article")
        return paragraphs, cleaned_text
    except Exception as e2:
        print(f"  [fallback] prepare_article también falló: {e2}")
        return [], ""




@csrf_exempt
@require_http_methods(["POST"])
def reprocess_article(request, article_id):
    """
    Reprocesa un artículo ya subido con un modelo diferente.
    Reutiliza el archivo raw original sin volver a subirlo.

    Body JSON:
      { "model": "tech" | "cmt" }
    """
    import json as _json

    try:
        body = _json.loads(request.body or b"{}")
    except Exception:
        body = {}

    model_key = body.get("model", "tech")
    if model_key not in MODEL_REGISTRY:
        return JsonResponse({"error": f"Modelo desconocido: '{model_key}'"}, status=400)

    meta = _read_json(_meta_path(article_id))
    if not meta:
        return JsonResponse({"error": "Artículo no encontrado"}, status=404)

    raw_file = meta.get("raw_file")
    if not raw_file:
        return JsonResponse({"error": "Archivo original no disponible"}, status=404)

    raw_path = Path(raw_file)
    if not raw_path.exists():
        return JsonResponse({"error": "Archivo original no encontrado en disco"}, status=404)

    # Actualizar meta con el nuevo modelo y estado
    meta["model"] = model_key
    meta["status"] = "queued"
    meta["stage"] = "queued"
    meta["error"] = None
    _write_json(_meta_path(article_id), meta)
    _write_progress(article_id, {"stage": "queued", "percent": 0, "processed": 0, "total": 0})

    thread = threading.Thread(
        target=_process_article_background,
        args=(article_id, raw_path, model_key),
        daemon=True,
    )
    thread.start()

    return JsonResponse({"article": meta})

# ─────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────

def _extract_title_from_cleaned_text(cleaned_path: Path) -> str | None:
    """Extrae el título del archivo de texto limpio (busca prefijo TITLE:)."""
    if not cleaned_path.exists():
        return None
    try:
        lines = cleaned_path.read_text(encoding="utf-8").splitlines()
        for line in lines[:30]:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^TITLE:\s*(.+)$", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        # Fallback: primer párrafo narrativo razonable
        for line in lines[:60]:
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith(("abstract", "keywords", "introduction")):
                continue
            if len(line) < 15 or len(line) > 220:
                continue
            if "journal homepage" in low or "contents lists available" in low:
                continue
            return line
    except Exception:
        pass
    return None