"""
Construccion y cache de proyecciones globales por workspace.

La proyeccion usa solo resultados ya procesados por articulo/modelo:
- embeddings_<model>.npz
- meta del workspace

No vuelve a correr NER ni embeddings del modelo. Agrega entidades
homonimas entre articulos y proyecta sus centroides en 2D.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from django.conf import settings
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE

from .workspace_service import get_workspace_summary


DATA_DIR = Path(settings.DATA_DIR)
ARTICLES_DIR = DATA_DIR / "articles"
WORKSPACES_DIR = DATA_DIR / "workspaces"


def build_workspace_projection(workspace_id: str, model_key: str) -> dict:
    summary = get_workspace_summary(workspace_id)
    article_name_map = {
        str(article.get("id")): str(article.get("original_name") or article.get("id"))
        for article in summary.get("articles", [])
        if article.get("exists")
    }
    processed_articles = [
        article
        for article in summary.get("articles", [])
        if article.get("exists") and article.get("models", {}).get(model_key) == "processed"
    ]

    cache_path = _workspace_projection_path(workspace_id, model_key)
    signature = _build_signature(processed_articles, model_key)
    cached = _read_cached_projection(cache_path)
    if cached and cached.get("signature") == signature:
        return cached

    entity_buckets: dict[str, dict] = {}
    processed_count = 0

    for article in processed_articles:
        article_id = article["id"]
        embeddings_path = ARTICLES_DIR / article_id / f"embeddings_{model_key}.npz"
        if not embeddings_path.exists():
            continue

        data = np.load(embeddings_path, allow_pickle=True)
        embeddings = data["embeddings"]
        labels = data["labels"]
        texts = data["texts"]
        data.close()

        if embeddings.size == 0:
            continue

        processed_count += 1
        seen_in_article = set()

        for index, raw_text in enumerate(texts):
            entity = str(raw_text or "").strip()
            key = _normalize_entity(entity)
            if not key:
                continue

            bucket = entity_buckets.setdefault(key, {
                "entity": entity,
                "sum_embedding": np.zeros(embeddings.shape[1], dtype=np.float64),
                "count": 0,
                "labels": Counter(),
                "article_ids": set(),
                "articles_occurrences": defaultdict(int),
            })

            bucket["sum_embedding"] += embeddings[index].astype(np.float64)
            bucket["count"] += 1
            bucket["labels"][str(labels[index] or "")] += 1
            bucket["article_ids"].add(article_id)
            bucket["articles_occurrences"][article_id] += 1

            if key not in seen_in_article:
                seen_in_article.add(key)

    points = _project_entity_buckets(entity_buckets, article_name_map)
    total_entity_occurrences = int(sum(point.get("frequency", 0) for point in points))
    result = {
        "workspace_id": workspace_id,
        "workspace_name": summary.get("name", workspace_id),
        "model": model_key,
        "processed_article_count": processed_count,
        "total_article_count": summary.get("article_count", 0),
        "unique_entity_count": len(points),
        "total_entity_occurrences": total_entity_occurrences,
        "points": points,
        "signature": signature,
    }
    _write_cached_projection(cache_path, result)
    return result


def _project_entity_buckets(entity_buckets: dict[str, dict], article_name_map: dict[str, str]) -> list[dict]:
    if not entity_buckets:
        return []

    items = []
    vectors = []
    for key, bucket in entity_buckets.items():
        count = max(int(bucket["count"]), 1)
        centroid = bucket["sum_embedding"] / count
        items.append((key, bucket, centroid))
        vectors.append(centroid)

    matrix = np.vstack(vectors).astype(np.float32)
    coords = _reduce_to_2d(matrix)

    points = []
    for (key, bucket, _), coord in zip(items, coords):
        article_ids = sorted(bucket["article_ids"])
        points.append({
            "key": key,
            "entity": bucket["entity"],
            "label": _dominant_label(bucket["labels"]),
            "frequency": int(bucket["count"]),
            "article_count": len(article_ids),
            "article_ids": article_ids,
            "article_breakdown": [
                {
                    "article_id": article_id,
                    "article_name": article_name_map.get(article_id, article_id),
                    "frequency": int(bucket["articles_occurrences"].get(article_id, 0)),
                }
                for article_id in article_ids
            ],
            "x": float(coord[0]),
            "y": float(coord[1]),
        })

    points.sort(key=lambda item: (-item["article_count"], -item["frequency"], item["entity"].lower()))
    return points


def _reduce_to_2d(matrix: np.ndarray) -> np.ndarray:
    n_samples = matrix.shape[0]
    if n_samples == 1:
        return np.array([[0.0, 0.0]], dtype=np.float32)
    if n_samples == 2:
        return np.array([[-1.0, 0.0], [1.0, 0.0]], dtype=np.float32)

    n_components = min(30, matrix.shape[1], n_samples)
    reduced = PCA(n_components=n_components, random_state=42).fit_transform(matrix)

    if n_samples < 8:
        final = PCA(n_components=2, random_state=42).fit_transform(reduced)
        return final.astype(np.float32)

    perplexity = min(25, max(5, n_samples // 3))
    perplexity = min(perplexity, n_samples - 1)
    final = TSNE(
        n_components=2,
        random_state=42,
        perplexity=perplexity,
        learning_rate="auto",
        init="pca",
        max_iter=600,
    ).fit_transform(reduced)
    return final.astype(np.float32)


def _workspace_projection_path(workspace_id: str, model_key: str) -> Path:
    return WORKSPACES_DIR / workspace_id / f"aggregate_{model_key}.json"


def _read_cached_projection(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cached_projection(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_signature(processed_articles: list[dict], model_key: str) -> str:
    digest = hashlib.sha256()
    digest.update(model_key.encode("utf-8"))
    for article in processed_articles:
        article_id = article["id"]
        embeddings_path = ARTICLES_DIR / article_id / f"embeddings_{model_key}.npz"
        meta = f"{article_id}|{embeddings_path.stat().st_mtime_ns if embeddings_path.exists() else 0}"
        digest.update(meta.encode("utf-8"))
    return digest.hexdigest()


def _normalize_entity(value: str) -> str:
    return " ".join(str(value or "").lower().split()).strip()


def _dominant_label(counter: Counter) -> str:
    if not counter:
        return "UNKNOWN"
    return counter.most_common(1)[0][0] or "UNKNOWN"
