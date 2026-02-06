import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from django.conf import settings


@dataclass
class ArticlePaths:
    article_id: str
    root_dir: Path
    source_dir: Path
    outputs_dir: Path
    source_file: Path
    metadata_file: Path
    progress_file: Path
    ner_results: Path
    embeddings: Path
    tsne_data: Path
    cleaned_text: Path


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _articles_root():
    root = Path(settings.DATA_DIR) / "articles"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_paths(article_id, original_name):
    root_dir = _articles_root() / article_id
    source_dir = root_dir / "source"
    outputs_dir = root_dir / "outputs"
    source_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / original_name
    return ArticlePaths(
        article_id=article_id,
        root_dir=root_dir,
        source_dir=source_dir,
        outputs_dir=outputs_dir,
        source_file=source_file,
        metadata_file=root_dir / "metadata.json",
        progress_file=root_dir / "progress.json",
        ner_results=outputs_dir / "ner_results.json",
        embeddings=outputs_dir / "entity_embeddings.npz",
        tsne_data=outputs_dir / "tsne_data.json",
        cleaned_text=outputs_dir / "cleaned_text.txt",
    )


def create_article_record(uploaded_file):
    article_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    original_name = Path(uploaded_file.name).name
    paths = _build_paths(article_id, original_name)

    with open(paths.source_file, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    metadata = {
        "id": article_id,
        "original_name": original_name,
        "uploaded_at": _now_iso(),
        "status": "uploaded",
        "source_path": str(paths.source_file.relative_to(settings.BASE_DIR)),
        "outputs": {
            "ner_results": str(paths.ner_results.relative_to(settings.BASE_DIR)),
            "embeddings": str(paths.embeddings.relative_to(settings.BASE_DIR)),
            "tsne_data": str(paths.tsne_data.relative_to(settings.BASE_DIR)),
            "cleaned_text": str(paths.cleaned_text.relative_to(settings.BASE_DIR)),
        },
    }

    _write_metadata(paths.metadata_file, metadata)
    _write_progress(
        paths.progress_file,
        {
            "stage": "queued",
            "percent": 0,
            "processed": 0,
            "total": 0,
            "eta_seconds": None,
        },
    )
    return metadata, paths


def update_status(paths, status, error=None, stage=None):
    metadata = read_metadata(paths.metadata_file)
    metadata["status"] = status
    metadata["processed_at"] = _now_iso()
    if error:
        metadata["error"] = error
    if stage:
        metadata["stage"] = stage
    metadata["updated_at"] = _now_iso()
    _write_metadata(paths.metadata_file, metadata)
    return metadata


def list_articles():
    articles = []
    root = _articles_root()
    for meta_file in root.glob("*/metadata.json"):
        try:
            meta = read_metadata(meta_file)
            outputs = meta.get("outputs", {})
            tsne_rel = outputs.get("tsne_data")
            tsne_path = None
            if tsne_rel:
                tsne_path = Path(settings.BASE_DIR) / tsne_rel
            if meta.get("status") == "processed" and tsne_path and tsne_path.exists():
                articles.append(meta)
        except Exception:
            continue
    articles.sort(key=lambda m: m.get("uploaded_at", ""), reverse=True)
    return articles


def read_metadata(metadata_file):
    with open(metadata_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_metadata(path, metadata):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _write_progress(path, progress):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
