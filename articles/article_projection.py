"""
Proyección 2D agregada por entidad para un solo artículo (vista panel individual).

Usa la misma lógica de buckets + t-SNE que el agregado multi-artículo del workspace
(`build_workspace_projection` en `workspace_projection`), pero con un único miembro.

Se guarda caché en disco por artículo (`projection_aggregate_<modelo>.json`) con la misma
firma que `workspace_projection`, para no repetir PCA/t-SNE cuando la caché de relaciones
se invalida pero los embeddings no cambiaron.

El consumidor típico es el grafo de relaciones del artículo (`build_article_relations`).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from django.conf import settings

from .combined_results import canonical_model_key, is_combined_model
from .workspace_projection import (
    _accumulate_entity_buckets,
    _build_signature,
    _project_entity_buckets,
)
from .workspace_service import _get_article_model_state, _read_article_meta

DATA_DIR = Path(settings.DATA_DIR)
ARTICLES_DIR = DATA_DIR / "articles"


def _article_projection_cache_paths(article_id: str, model_key: str) -> tuple[Path, Path]:
    base = ARTICLES_DIR / article_id
    return (
        base / f"projection_aggregate_{model_key}.json",
        base / f"projection_aggregate_{model_key}.meta.json",
    )


def _try_read_article_projection_cache(
    article_id: str,
    model_key: str,
    signature: str,
) -> dict | None:
    body_path, meta_path = _article_projection_cache_paths(article_id, model_key)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        meta = {}
    if meta.get("signature") != signature or not body_path.exists():
        return None
    try:
        cached = json.loads(body_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(cached, dict) or cached.get("signature") != signature:
        return None
    # Igual que workspace: no devolver agregado ambos vacío “pegado” si puede recomputarse.
    if (
        is_combined_model(model_key)
        and not (cached.get("points") or [])
    ):
        return None
    return cached


def _write_article_projection_cache(article_id: str, model_key: str, signature: str, payload: dict) -> None:
    body_path, meta_path = _article_projection_cache_paths(article_id, model_key)
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps({"signature": signature}, ensure_ascii=False, indent=2), encoding="utf-8")


def _infer_embedding_dim_article(article_id: str, model_key: str) -> int:
    path = ARTICLES_DIR / article_id / f"embeddings_{model_key}.npz"
    if not path.exists():
        return 0
    with np.load(path) as data:
        emb = data["embeddings"] if "embeddings" in data.files else np.empty((0, 0), dtype=np.float32)
    if emb.ndim >= 2 and emb.shape[1] > 0:
        return int(emb.shape[1])
    return 0


def _ambos_buckets_merge_mono(
    tech_buckets: dict[str, dict],
    cmt_buckets: dict[str, dict],
    dim_hint_article_id: str,
) -> dict[str, dict]:
    """
    Cuando la ruta concat/joint no produce filas pero sí hay embeddings mono por modelo,
    arma buckets «ambos» con vectores [tech|cmt] para la proyección agregada y relaciones.
    """
    dim_tech = max((len(b["sum_embedding"]) for b in tech_buckets.values()), default=0)
    dim_cmt = max((len(b["sum_embedding"]) for b in cmt_buckets.values()), default=0)
    if dim_tech <= 0:
        dim_tech = _infer_embedding_dim_article(dim_hint_article_id, "tech")
    if dim_cmt <= 0:
        dim_cmt = _infer_embedding_dim_article(dim_hint_article_id, "cmt")
    zero_t = np.zeros(dim_tech, dtype=np.float64)
    zero_c = np.zeros(dim_cmt, dtype=np.float64)
    out: dict[str, dict] = {}
    for key in set(tech_buckets.keys()) | set(cmt_buckets.keys()):
        tb = tech_buckets.get(key)
        cb = cmt_buckets.get(key)
        nt = int(tb["count"]) if tb else 0
        nc = int(cb["count"]) if cb else 0
        if nt <= 0 and nc <= 0:
            continue
        labels: Counter = Counter()
        origins: Counter = Counter()
        article_ids: set = set()
        articles_occurrences: defaultdict = defaultdict(int)

        if tb and cb:
            mean_t = tb["sum_embedding"] / max(nt, 1)
            mean_c = cb["sum_embedding"] / max(nc, 1)
            sum_emb = np.concatenate([mean_t, mean_c]) * (nt + nc)
            count = nt + nc
            labels.update(tb["labels"])
            labels.update(cb["labels"])
            origins["tech"] += nt
            origins["cmt"] += nc
            entity_name = tb["entity"] if nt >= nc else cb["entity"]
            article_ids |= tb["article_ids"] | cb["article_ids"]
            for aid, v in tb["articles_occurrences"].items():
                articles_occurrences[aid] += int(v)
            for aid, v in cb["articles_occurrences"].items():
                articles_occurrences[aid] += int(v)
        elif tb:
            sum_emb = np.concatenate([tb["sum_embedding"], zero_c])
            count = nt
            labels.update(tb["labels"])
            origins["tech"] += nt
            entity_name = tb["entity"]
            article_ids |= tb["article_ids"]
            for aid, v in tb["articles_occurrences"].items():
                articles_occurrences[aid] += int(v)
        else:
            sum_emb = np.concatenate([zero_t, cb["sum_embedding"]])
            count = nc
            labels.update(cb["labels"])
            origins["cmt"] += nc
            entity_name = cb["entity"]
            article_ids |= cb["article_ids"]
            for aid, v in cb["articles_occurrences"].items():
                articles_occurrences[aid] += int(v)

        out[key] = {
            "entity": entity_name or key,
            "sum_embedding": sum_emb,
            "count": count,
            "labels": labels,
            "origins": origins,
            "article_ids": article_ids,
            "articles_occurrences": articles_occurrences,
        }
    return out


def build_article_aggregate_projection(article_id: str, model_key: str) -> dict:
    model_key = canonical_model_key(model_key)
    aid = str(article_id).strip()
    meta = _read_article_meta(aid)
    if not meta:
        return {
            "article_id": aid,
            "article_original_name": aid,
            "model": model_key,
            "points": [],
            "signature": "",
            "processed_article_count": 0,
            "unique_entity_count": 0,
            "total_entity_occurrences": 0,
        }

    if _get_article_model_state(aid, meta, model_key) != "processed":
        return {
            "article_id": aid,
            "article_original_name": str(meta.get("original_name") or aid),
            "model": model_key,
            "points": [],
            "signature": "",
            "processed_article_count": 0,
            "unique_entity_count": 0,
            "total_entity_occurrences": 0,
        }

    processed_articles = [{"id": aid, "exists": True}]
    article_name_map = {aid: str(meta.get("original_name") or aid)}
    summary = {"updated_at": str(meta.get("updated_at") or ""), "article_ids": [aid]}
    signature = _build_signature(summary, processed_articles, model_key)

    cached_projection = _try_read_article_projection_cache(aid, model_key, signature)
    if cached_projection is not None:
        return cached_projection

    entity_buckets, processed_count = _accumulate_entity_buckets(processed_articles, model_key)
    if not entity_buckets and is_combined_model(model_key):
        tech_buckets, _ = _accumulate_entity_buckets(processed_articles, "tech")
        cmt_buckets, _ = _accumulate_entity_buckets(processed_articles, "cmt")
        if tech_buckets or cmt_buckets:
            entity_buckets = _ambos_buckets_merge_mono(tech_buckets, cmt_buckets, aid)
            processed_count = len(processed_articles)
    points = _project_entity_buckets(entity_buckets, article_name_map)
    total_entity_occurrences = int(sum(point.get("frequency", 0) for point in points))

    result = {
        "article_id": aid,
        "article_original_name": article_name_map[aid],
        "model": model_key,
        "processed_article_count": processed_count,
        "total_article_count": 1,
        "unique_entity_count": len(points),
        "total_entity_occurrences": total_entity_occurrences,
        "points": points,
        "signature": signature,
    }
    # No persistir ambos vacío: igual que la lectura de caché, evita archivos inútiles y recomputos coherentes.
    if points or not is_combined_model(model_key):
        _write_article_projection_cache(aid, model_key, signature, result)
    return result
