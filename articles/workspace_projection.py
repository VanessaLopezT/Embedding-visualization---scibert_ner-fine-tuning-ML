"""
Construcción y caché de proyecciones agregadas para workspaces (varios artículos).

Para un solo artículo en el panel (sin workspace), ver `article_projection.build_article_aggregate_projection`:
reutiliza `_accumulate_entity_buckets` y `_project_entity_buckets` de este módulo.

La proyección usa solo resultados ya procesados por artículo/modelo:
- embeddings_<model>.npz
- meta del workspace

No vuelve a correr NER ni embeddings del modelo. Agrega entidades
homónimas entre artículos y proyecta sus centroides en 2D.
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

from .combined_results import (
    canonical_model_key,
    is_combined_model,
    pad_workspace_concat_embedding,
    workspace_combined_occurrence_rows,
)
from .workspace_service import get_workspace_summary


DATA_DIR = Path(settings.DATA_DIR)
ARTICLES_DIR = DATA_DIR / "articles"
WORKSPACES_DIR = DATA_DIR / "workspaces"


def _accumulate_entity_buckets(
    processed_articles: list[dict],
    model_key: str,
) -> tuple[dict[str, dict], int]:
    """
    Acumula buckets de embedding por entidad (misma lógica workspace y artículo aislado).
    Devuelve (entity_buckets, processed_count).
    """
    max_ambos_concat_len = 0
    if is_combined_model(model_key):
        for art in processed_articles:
            for row in workspace_combined_occurrence_rows(art["id"]):
                max_ambos_concat_len = max(max_ambos_concat_len, int(np.asarray(row["vector"]).size))

    entity_buckets: dict[str, dict] = {}
    processed_count = 0

    for article in processed_articles:
        article_id = article["id"]
        if is_combined_model(model_key):
            if max_ambos_concat_len <= 0:
                continue
            rows = workspace_combined_occurrence_rows(article_id)
            if not rows:
                continue
            processed_count += 1
            for row in rows:
                key = _normalize_entity(row.get("norm_entity") or "")
                if not key:
                    continue
                vec = pad_workspace_concat_embedding(row["vector"], max_ambos_concat_len)
                bucket = entity_buckets.setdefault(key, {
                    "entity": str(row.get("entity_display") or key),
                    "sum_embedding": np.zeros(max_ambos_concat_len, dtype=np.float64),
                    "count": 0,
                    "labels": Counter(),
                    "origins": Counter(),
                    "article_ids": set(),
                    "articles_occurrences": defaultdict(int),
                })
                bucket["sum_embedding"] += vec
                bucket["count"] += 1
                bucket["labels"][str(row.get("label") or "")] += 1
                origin = str(row.get("origin") or "joint").strip().lower() or "joint"
                bucket["origins"][origin] += 1
                bucket["article_ids"].add(article_id)
                bucket["articles_occurrences"][article_id] += 1
            continue

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

    return entity_buckets, processed_count


def build_workspace_projection(workspace_id: str, model_key: str) -> dict:
    model_key = canonical_model_key(model_key)
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
    signature = _build_signature(summary, processed_articles, model_key)
    cached = _read_cached_projection(cache_path)
    if cached and cached.get("signature") == signature:
        # En modo combinado, un cache vacío puede venir de una corrida previa
        # incompleta; si hay artículos "processed", intentamos recomputar.
        if not (
            is_combined_model(model_key)
            and processed_articles
            and not (cached.get("points") or [])
        ):
            return cached

    entity_buckets, processed_count = _accumulate_entity_buckets(processed_articles, model_key)
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
    coords = np.asarray(_reduce_to_2d(matrix), dtype=np.float64)
    coords = _center_xy_coords(coords)
    coords = _scale_xy_visual_extent(coords)

    points = []
    for (key, bucket, _), coord in zip(items, coords):
        article_ids = sorted(bucket["article_ids"])
        row = {
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
        }
        origins = bucket.get("origins")
        if origins:
            row["dominant_origin"] = _dominant_label(origins)
        points.append(row)

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


def _center_xy_coords(coords: np.ndarray) -> np.ndarray:
    """Quita traslación arbitraria del embedding 2D para que la nube quede centrada al cambiar de modelo."""
    arr = np.asarray(coords, dtype=np.float64)
    if arr.size == 0:
        return arr
    arr = arr - arr.mean(axis=0)
    return arr


def _scale_xy_visual_extent(coords: np.ndarray, target_rms: float = 52.0) -> np.ndarray:
    """Amplía la nube centrada (~zoom) para que ocupe mejor el lienzo sin cambiar la forma relativa."""
    arr = np.asarray(coords, dtype=np.float64)
    if arr.size == 0:
        return arr
    rms = float(np.sqrt(np.mean(arr ** 2)))
    if rms < 1e-15:
        return arr
    return arr * (target_rms / rms)


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


def _build_signature(summary: dict, processed_articles: list[dict], model_key: str) -> str:
    digest = hashlib.sha256()
    digest.update(model_key.encode("utf-8"))
    digest.update(b"|ws_proj_xy_center_scale_v2|")
    digest.update(str(summary.get("updated_at") or "").encode("utf-8"))
    digest.update(
        "|".join(str(aid) for aid in (summary.get("article_ids") or [])).encode("utf-8"),
    )
    for article in sorted(processed_articles, key=lambda a: str(a.get("id") or "")):
        article_id = article["id"]
        if is_combined_model(model_key):
            tech_path = ARTICLES_DIR / article_id / "embeddings_tech.npz"
            cmt_path = ARTICLES_DIR / article_id / "embeddings_cmt.npz"
            tech_stamp = tech_path.stat().st_mtime_ns if tech_path.exists() else 0
            cmt_stamp = cmt_path.stat().st_mtime_ns if cmt_path.exists() else 0
            digest.update(f"{article_id}|{tech_stamp}|{cmt_stamp}|ambos_agg_concat_emb_v3_pad_ws".encode("utf-8"))
            continue
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
