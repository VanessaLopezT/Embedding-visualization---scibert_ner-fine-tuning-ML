"""
Vistas Django para la app de visualizacion NER dual-modelo.

Modelos soportados:
  - "tech": SciBERT fine-tuned en literatura ML/Tech
  - "cmt" : PubMedBERT fine-tuned en oncologia veterinaria (CMT)

La logica pesada de procesamiento vive en articles.processing_runtime:
  - cola por modelo
  - worker persistente
  - reuso del modelo cargado
  - reuso de cleaned_text cuando ya existe
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .model_registry import MODEL_REGISTRY
from .processing_runtime import submit_article_job
from .workspace_projection import build_workspace_projection
from .workspace_relations import build_workspace_relations
from .workspace_service import (
    add_workspace_articles,
    create_workspace_with_validation,
    delete_workspace_with_validation,
    enqueue_workspace_processing,
    get_workspace_summary,
    list_workspace_summaries,
    remove_workspace_articles,
    update_workspace_metadata,
)


DATA_DIR = settings.DATA_DIR
ARTICLES_DIR = DATA_DIR / "articles"
EXAMPLE_DIR = DATA_DIR / "example"

ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)


MODEL_REGISTRY["tech"]["example_tsne"] = EXAMPLE_DIR / "tsne_tech.json"
MODEL_REGISTRY["cmt"]["example_tsne"] = EXAMPLE_DIR / "tsne_cmt.json"


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


def _iter_uploaded_files(request) -> list:
    files = request.FILES.getlist("file")
    if files:
        return files

    uploaded = request.FILES.get("file")
    return [uploaded] if uploaded is not None else []


def index(request):
    return render(request, "index.html")


@require_http_methods(["GET"])
def get_models(request):
    models = [
        {
            "key": key,
            "label": value["label"],
            "description": value["description"],
            "color_scheme": value["color_scheme"],
        }
        for key, value in MODEL_REGISTRY.items()
    ]
    return JsonResponse({"models": models})


@require_http_methods(["GET"])
def list_articles(request):
    articles = []
    if ARTICLES_DIR.exists():
        for article_dir in sorted(ARTICLES_DIR.iterdir()):
            meta_file = article_dir / "meta.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if meta.get("status") != "processed":
                continue
            articles.append({
                "id": meta.get("id", article_dir.name),
                "original_name": meta.get("original_name", article_dir.name),
                "status": meta.get("status", "unknown"),
                "model": meta.get("model", "tech"),
            })
    return JsonResponse({"articles": articles})


@csrf_exempt
@require_http_methods(["POST"])
def upload_article(request):
    """
    Recibe uno o varios archivos PDF/TXT y los encola para procesar.

    Compatibilidad:
    - Si llega un solo archivo, conserva la respuesta {"article": ...}
    - Si llegan varios archivos, responde {"articles": [...], "rejected": [...]}
    """
    uploaded_files = _iter_uploaded_files(request)
    if not uploaded_files:
        return JsonResponse({"error": "No file provided"}, status=400)

    model_key = request.POST.get("model", "tech")
    if model_key not in MODEL_REGISTRY:
        return JsonResponse({"error": f"Modelo desconocido: '{model_key}'"}, status=400)
    workspace_id = str(request.POST.get("workspace_id", "")).strip()
    if workspace_id:
        try:
            get_workspace_summary(workspace_id)
        except FileNotFoundError:
            return JsonResponse({"error": "Workspace no encontrado"}, status=404)

    accepted = []
    rejected = []

    for uploaded in uploaded_files:
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in (".pdf", ".txt"):
            rejected.append({
                "original_name": uploaded.name,
                "error": "Solo se aceptan archivos .pdf y .txt",
            })
            continue

        article_id = str(uuid.uuid4())[:8]
        article_dir = _article_dir(article_id)
        article_dir.mkdir(parents=True, exist_ok=True)

        raw_path = article_dir / f"raw{suffix}"
        with open(raw_path, "wb") as file_obj:
            for chunk in uploaded.chunks():
                file_obj.write(chunk)

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
        _write_progress(article_id, {
            "stage": "queued",
            "percent": 0,
            "processed": 0,
            "total": 0,
        })

        submit_article_job(article_id, raw_path, model_key, MODEL_REGISTRY[model_key]["checkpoint"])
        accepted.append(meta)

    if workspace_id and accepted:
        add_workspace_articles(workspace_id, [item["id"] for item in accepted])

    if not accepted:
        error = rejected[0]["error"] if rejected else "No se pudo procesar la solicitud"
        return JsonResponse({"error": error, "rejected": rejected}, status=400)

    if len(uploaded_files) == 1 and len(accepted) == 1:
        return JsonResponse({"article": accepted[0]})

    return JsonResponse({
        "articles": accepted,
        "count": len(accepted),
        "rejected": rejected,
    })


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


@csrf_exempt
@require_http_methods(["GET", "POST"])
def workspaces(request):
    if request.method == "GET":
        return JsonResponse({"workspaces": list_workspace_summaries()})

    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        body = {}

    name = str(body.get("name", "")).strip()
    if not name:
        return JsonResponse({"error": "El workspace requiere un nombre"}, status=400)

    description = str(body.get("description", "")).strip()
    article_ids = body.get("article_ids") or []
    workspace = create_workspace_with_validation(name, description, article_ids)
    return JsonResponse({"workspace": workspace}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def workspace_detail(request, workspace_id):
    if request.method == "GET":
        try:
            return JsonResponse({"workspace": get_workspace_summary(workspace_id)})
        except FileNotFoundError:
            return JsonResponse({"error": "Workspace no encontrado"}, status=404)

    if request.method == "DELETE":
        deleted = delete_workspace_with_validation(workspace_id)
        if not deleted:
            return JsonResponse({"error": "Workspace no encontrado"}, status=404)
        return JsonResponse({"deleted": True, "workspace_id": workspace_id})

    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        body = {}

    try:
        workspace = update_workspace_metadata(
            workspace_id,
            name=body.get("name"),
            description=body.get("description"),
        )
    except FileNotFoundError:
        return JsonResponse({"error": "Workspace no encontrado"}, status=404)

    return JsonResponse({"workspace": workspace})


@csrf_exempt
@require_http_methods(["POST"])
def workspace_articles(request, workspace_id):
    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        body = {}

    article_ids = body.get("article_ids") or []
    mode = body.get("mode", "add")

    try:
        if mode == "remove":
            workspace = remove_workspace_articles(workspace_id, article_ids)
        else:
            workspace = add_workspace_articles(workspace_id, article_ids)
    except FileNotFoundError:
        return JsonResponse({"error": "Workspace no encontrado"}, status=404)

    return JsonResponse({"workspace": workspace})


@csrf_exempt
@require_http_methods(["POST"])
def workspace_process(request, workspace_id):
    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        body = {}

    model_key = body.get("model", "tech")
    if model_key not in MODEL_REGISTRY:
        return JsonResponse({"error": f"Modelo desconocido: '{model_key}'"}, status=400)

    try:
        result = enqueue_workspace_processing(workspace_id, model_key)
    except FileNotFoundError:
        return JsonResponse({"error": "Workspace no encontrado"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(result)


@require_http_methods(["GET"])
def workspace_aggregate(request, workspace_id):
    model_key = request.GET.get("model", "tech")
    if model_key not in MODEL_REGISTRY:
        return JsonResponse({"error": f"Modelo desconocido: '{model_key}'"}, status=400)

    try:
        payload = build_workspace_projection(workspace_id, model_key)
    except FileNotFoundError:
        return JsonResponse({"error": "Workspace no encontrado"}, status=404)
    except Exception as exc:
        return JsonResponse({"error": f"No se pudo construir la proyeccion del workspace: {exc}"}, status=500)

    return JsonResponse(payload)


@require_http_methods(["GET"])
def workspace_relations(request, workspace_id):
    model_key = request.GET.get("model", "tech")
    if model_key not in MODEL_REGISTRY:
        return JsonResponse({"error": f"Modelo desconocido: '{model_key}'"}, status=400)

    try:
        payload = build_workspace_relations(workspace_id, model_key)
    except FileNotFoundError:
        return JsonResponse({"error": "Workspace no encontrado"}, status=404)
    except Exception as exc:
        return JsonResponse({"error": f"No se pudieron construir las relaciones del workspace: {exc}"}, status=500)

    return JsonResponse(payload)


@csrf_exempt
@require_http_methods(["POST"])
def reprocess_article(request, article_id):
    """
    Reprocesa un artículo ya subido con un modelo diferente.
    Reutiliza el archivo raw original sin volver a subirlo.

    Body JSON:
      { "model": "tech" | "cmt" }
    """
    try:
        body = json.loads(request.body or b"{}")
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

    original_meta = dict(meta)
    meta["model"] = model_key
    meta["status"] = "queued"
    meta["stage"] = "queued"
    meta["error"] = None
    _write_json(_meta_path(article_id), meta)
    _write_progress(article_id, {
        "stage": "queued",
        "percent": 0,
        "processed": 0,
        "total": 0,
    })

    submitted = submit_article_job(article_id, raw_path, model_key, MODEL_REGISTRY[model_key]["checkpoint"])
    if not submitted:
        _write_json(_meta_path(article_id), original_meta)
        return JsonResponse({
            "error": "Ese artículo ya está en cola o procesándose para ese modelo",
        }, status=409)
    return JsonResponse({"article": meta})


def _extract_title_from_cleaned_text(cleaned_path: Path) -> str | None:
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
