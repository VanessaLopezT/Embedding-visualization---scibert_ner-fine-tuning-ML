"""
Servicios de dominio para workspaces.

Encapsula:
- validacion de articulos
- resumen de estado por modelo
- operaciones de membresia
- encolado de procesamiento por workspace
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from .model_registry import MODEL_REGISTRY
from .processing_runtime import submit_article_job
from .workspace_storage import (
    add_articles,
    create_workspace,
    delete_workspace,
    list_workspaces,
    read_workspace,
    remove_articles,
    update_workspace,
)


ARTICLES_DIR = Path(settings.DATA_DIR) / "articles"


def list_workspace_summaries() -> list[dict]:
    return [get_workspace_summary(item["id"]) for item in list_workspaces()]


def get_workspace_summary(workspace_id: str) -> dict:
    workspace = read_workspace(workspace_id)
    article_items = []
    model_summary = {
        model_key: {
            "processed": 0,
            "missing": 0,
            "queued_or_processing": 0,
            "failed": 0,
        }
        for model_key in MODEL_REGISTRY.keys()
    }

    for article_id in workspace.get("article_ids", []):
        article_meta = _read_article_meta(article_id)
        if not article_meta:
            article_items.append({
                "id": article_id,
                "exists": False,
                "models": {model_key: "missing_article" for model_key in MODEL_REGISTRY.keys()},
            })
            continue

        model_states = {}
        for model_key in MODEL_REGISTRY.keys():
            state = _get_article_model_state(article_id, article_meta, model_key)
            model_states[model_key] = state
            if state == "processed":
                model_summary[model_key]["processed"] += 1
            elif state in {"queued", "processing"}:
                model_summary[model_key]["queued_or_processing"] += 1
            elif state == "failed":
                model_summary[model_key]["failed"] += 1
            else:
                model_summary[model_key]["missing"] += 1

        article_items.append({
            "id": article_id,
            "exists": True,
            "original_name": article_meta.get("original_name", article_id),
            "status": article_meta.get("status", "unknown"),
            "stage": article_meta.get("stage", "unknown"),
            "models": model_states,
        })

    return {
        **workspace,
        "article_count": len(workspace.get("article_ids", [])),
        "articles": article_items,
        "model_summary": model_summary,
    }


def create_workspace_with_validation(name: str, description: str = "", article_ids: list[str] | None = None) -> dict:
    valid_ids = [article_id for article_id in (article_ids or []) if _article_exists(article_id)]
    workspace = create_workspace(name=name, description=description, article_ids=valid_ids)
    return get_workspace_summary(workspace["id"])


def update_workspace_metadata(workspace_id: str, *, name: str | None = None, description: str | None = None) -> dict:
    update_workspace(workspace_id, name=name, description=description)
    return get_workspace_summary(workspace_id)


def add_workspace_articles(workspace_id: str, article_ids: list[str]) -> dict:
    valid_ids = [article_id for article_id in article_ids if _article_exists(article_id)]
    add_articles(workspace_id, valid_ids)
    return get_workspace_summary(workspace_id)


def remove_workspace_articles(workspace_id: str, article_ids: list[str]) -> dict:
    remove_articles(workspace_id, article_ids)
    return get_workspace_summary(workspace_id)


def delete_workspace_with_validation(workspace_id: str) -> bool:
    return delete_workspace(workspace_id)


def enqueue_workspace_processing(workspace_id: str, model_key: str) -> dict:
    if model_key not in MODEL_REGISTRY:
        raise ValueError(f"Modelo desconocido: '{model_key}'")

    summary = get_workspace_summary(workspace_id)
    conflicting_jobs = []

    for article in summary["articles"]:
        if not article.get("exists"):
            continue
        article_status = article.get("status")
        article_model = article.get("model")
        if article_status in {"queued", "processing"} and article_model and article_model != model_key:
            conflicting_jobs.append({
                "article_id": article["id"],
                "model": article_model,
                "status": article_status,
            })

    if conflicting_jobs:
        active_models = ", ".join(sorted({item["model"] for item in conflicting_jobs}))
        raise ValueError(
            f"Hay articulos del workspace en cola o procesandose con otro modelo ({active_models}). "
            f"Espera a que terminen antes de procesar con '{model_key}'."
        )

    accepted = []
    skipped = []

    for article in summary["articles"]:
        if not article.get("exists"):
            skipped.append({
                "article_id": article["id"],
                "reason": "missing_article",
            })
            continue

        state = article["models"].get(model_key, "missing")
        if state == "processed":
            skipped.append({
                "article_id": article["id"],
                "reason": "already_processed",
            })
            continue
        if state in {"queued", "processing"}:
            skipped.append({
                "article_id": article["id"],
                "reason": "already_pending",
            })
            continue

        article_meta = _read_article_meta(article["id"])
        raw_path = Path(article_meta["raw_file"])
        submitted = submit_article_job(
            article["id"],
            raw_path,
            model_key,
            MODEL_REGISTRY[model_key]["checkpoint"],
        )
        if submitted:
            accepted.append(article["id"])
        else:
            skipped.append({
                "article_id": article["id"],
                "reason": "already_pending",
            })

    return {
        "workspace": get_workspace_summary(workspace_id),
        "model": model_key,
        "enqueued_article_ids": accepted,
        "skipped": skipped,
    }


def _article_exists(article_id: str) -> bool:
    return (_article_dir(article_id) / "meta.json").exists()


def _article_dir(article_id: str) -> Path:
    return ARTICLES_DIR / article_id


def _article_meta_path(article_id: str) -> Path:
    return _article_dir(article_id) / "meta.json"


def _tsne_path(article_id: str, model_key: str) -> Path:
    return _article_dir(article_id) / f"tsne_{model_key}.json"


def _read_article_meta(article_id: str) -> dict:
    path = _article_meta_path(article_id)
    if not path.exists():
        return {}
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_article_model_state(article_id: str, article_meta: dict, model_key: str) -> str:
    if not article_meta:
        return "missing_article"

    if _tsne_path(article_id, model_key).exists():
        return "processed"

    if article_meta.get("model") == model_key and article_meta.get("status") in {"queued", "processing"}:
        return article_meta.get("status")

    if article_meta.get("model") == model_key and article_meta.get("status") == "failed":
        return "failed"

    return "missing"
