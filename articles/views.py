from pathlib import Path
import threading
import re

from django.conf import settings
from django.http import JsonResponse, Http404
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import services
from .storage import create_article_record, list_articles as list_article_records, load_json, update_status


def index(request):
    return render(request, "index.html")


@require_GET
def list_articles(request):
    return JsonResponse({"articles": list_article_records()})


@csrf_exempt
@require_POST
def upload_article(request):
    if "file" not in request.FILES:
        return JsonResponse({"error": "No file provided"}, status=400)

    uploaded_file = request.FILES["file"]
    if not uploaded_file.name:
        return JsonResponse({"error": "No file selected"}, status=400)

    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in [".txt", ".pdf"]:
        return JsonResponse({"error": "Solo archivos .txt y .pdf son permitidos"}, status=400)

    metadata, paths = create_article_record(uploaded_file)
    metadata = update_status(paths, "processing", stage="queued")

    def _worker():
        try:
            update_status(paths, "processing", stage="processing")
            services.process_article(paths)
            update_status(paths, "processed", stage="completed")
        except Exception as exc:
            update_status(paths, "failed", error=str(exc), stage="failed")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    return JsonResponse({"success": True, "article": metadata})


@require_GET
def get_article_tsne(request, article_id):
    paths = _resolve_article_paths(article_id)
    if not paths["tsne"].exists() and paths["embeddings"].exists():
        try:
            services.generate_tsne_from_embeddings(paths["embeddings"], paths["tsne"])
        except Exception:
            return JsonResponse({"error": "No tsne data available"}, status=404)
    if not paths["tsne"].exists():
        return JsonResponse({"error": "No tsne data available"}, status=404)
    return JsonResponse({"data": load_json(paths["tsne"]), "source": "article"})


@require_GET
def get_article_ner(request, article_id):
    paths = _resolve_article_paths(article_id)
    if not paths["ner"].exists():
        return JsonResponse({"error": "No ner data available"}, status=404)
    return JsonResponse({"data": load_json(paths["ner"]), "source": "article"})


@require_GET
def get_article_meta(request, article_id):
    paths = _resolve_article_paths(article_id)
    if not paths["meta"].exists():
        return JsonResponse({"error": "No metadata available"}, status=404)
    progress = None
    if paths["progress"].exists():
        try:
            progress = load_json(paths["progress"])
        except Exception:
            progress = None
    title = None
    cleaned = paths.get("cleaned_text")
    if cleaned and cleaned.exists():
        try:
            with open(cleaned, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Buscar TITLE en las primeras líneas (no asumir que está en la 1).
            for raw in lines[:30]:
                line = (raw or "").strip()
                if not line:
                    continue
                match = re.match(r"^TITLE:\s*(.+)$", line, flags=re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                    break

            # Fallback: usar primer párrafo narrativo corto si no hay TITLE.
            if not title:
                for raw in lines[:60]:
                    line = (raw or "").strip()
                    if not line:
                        continue
                    low = line.lower()
                    if low.startswith(("abstract", "keywords", "introduction")):
                        continue
                    if len(line) < 15 or len(line) > 220:
                        continue
                    if "journal homepage" in low or "contents lists available" in low:
                        continue
                    title = line
                    break
        except Exception:
            title = None

    return JsonResponse({"article": load_json(paths["meta"]), "progress": progress, "title": title})


@require_GET
def get_article_cleaned_text(request, article_id):
    paths = _resolve_article_paths(article_id)
    cleaned_path = paths.get("cleaned_text")
    if not cleaned_path or not cleaned_path.exists():
        return JsonResponse({"error": "No cleaned text available"}, status=404)
    try:
        with open(cleaned_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return JsonResponse({"error": "No cleaned text available"}, status=404)
    return JsonResponse({"text": text, "source": "article"})


@require_GET
def get_example_tsne(request):
    example_path = Path(settings.BASE_DIR) / "web" / "tsne_data.json"
    if not example_path.exists():
        return JsonResponse({"error": "No example data available"}, status=404)
    return JsonResponse({"data": load_json(example_path), "source": "example"})


def _resolve_article_paths(article_id):
    root = Path(settings.DATA_DIR) / "articles" / article_id
    if not root.exists():
        raise Http404("Article not found")
    return {
        "meta": root / "metadata.json",
        "ner": root / "outputs" / "ner_results.json",
        "embeddings": root / "outputs" / "entity_embeddings.npz",
        "tsne": root / "outputs" / "tsne_data.json",
        "progress": root / "progress.json",
        "cleaned_text": root / "outputs" / "cleaned_text.txt",
    }
