"""
Construccion y cache de relaciones globales por workspace.

Usa solo resultados ya procesados por articulo/modelo:
- tsne_<model>.json para contexto y coocurrencia
- aggregate_<model>.json para posiciones agregadas en 2D

No vuelve a correr NER ni embeddings del modelo.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings

from .workspace_projection import build_workspace_projection
from .workspace_service import get_workspace_summary


DATA_DIR = Path(settings.DATA_DIR)
ARTICLES_DIR = DATA_DIR / "articles"
WORKSPACES_DIR = DATA_DIR / "workspaces"


DEFAULT_OPTIONS = {
    "min_entity_frequency": 1,
    "min_sentence_cooccurrence": 2,
    "score_threshold": 0.24,
    "max_edges": 120,
}


def build_workspace_relations(workspace_id: str, model_key: str) -> dict:
    summary = get_workspace_summary(workspace_id)
    processed_articles = [
        article
        for article in summary.get("articles", [])
        if article.get("exists") and article.get("models", {}).get(model_key) == "processed"
    ]

    aggregate_payload = build_workspace_projection(workspace_id, model_key)
    cache_path = _workspace_relations_path(workspace_id, model_key)
    signature = _build_signature(processed_articles, model_key, aggregate_payload.get("signature", ""))
    cached = _read_cached_payload(cache_path)
    if cached and cached.get("signature") == signature:
        return cached

    points = aggregate_payload.get("points", [])
    point_map = {str(point.get("key") or ""): point for point in points}
    if not point_map:
        result = {
            "workspace_id": workspace_id,
            "workspace_name": summary.get("name", workspace_id),
            "model": model_key,
            "processed_article_count": len(processed_articles),
            "total_article_count": summary.get("article_count", 0),
            "unique_entity_count": 0,
            "total_entity_occurrences": 0,
            "nodes": [],
            "edges": [],
            "signature": signature,
        }
        _write_cached_payload(cache_path, result)
        return result

    sentence_entity_map: dict[str, set[str]] = defaultdict(set)
    chunk_entity_map: dict[str, set[str]] = defaultdict(set)
    entity_stats: dict[str, dict] = {}

    for article in processed_articles:
        article_id = str(article["id"])
        tsne_path = ARTICLES_DIR / article_id / f"tsne_{model_key}.json"
        if not tsne_path.exists():
            continue

        try:
            article_points = json.loads(tsne_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for point in article_points:
            entity = str(point.get("entity") or "").strip()
            key = _normalize_entity(entity)
            if not key or key not in point_map:
                continue

            stats = entity_stats.setdefault(key, {
                "labels": Counter(),
                "frequency": 0,
                "article_ids": set(),
                "sentences": set(),
                "chunks": set(),
            })

            stats["labels"][str(point.get("label") or "UNKNOWN")] += 1
            stats["frequency"] += 1
            stats["article_ids"].add(article_id)

            sentence_id = point.get("sentence_id")
            if sentence_id is not None:
                sentence_key = f"{article_id}::s::{sentence_id}"
                stats["sentences"].add(sentence_key)
                sentence_entity_map[sentence_key].add(key)

            chunk_id = point.get("text_index")
            if chunk_id is not None:
                chunk_key = f"{article_id}::c::{chunk_id}"
                stats["chunks"].add(chunk_key)
                chunk_entity_map[chunk_key].add(key)

    nodes = []
    for key, point in point_map.items():
        stats = entity_stats.get(key)
        if not stats:
            continue
        if stats["frequency"] < DEFAULT_OPTIONS["min_entity_frequency"]:
            continue

        nodes.append({
            "key": key,
            "entity": point.get("entity", key),
            "label": point.get("label") or _dominant_label(stats["labels"]),
            "frequency": int(stats["frequency"]),
            "article_count": len(stats["article_ids"]),
            "x": float(point.get("x", 0.0)),
            "y": float(point.get("y", 0.0)),
            "sentences": stats["sentences"],
            "chunks": stats["chunks"],
            "sentence_profile": _build_context_profile(stats["sentences"], sentence_entity_map, key),
            "chunk_profile": _build_context_profile(stats["chunks"], chunk_entity_map, key),
        })

    allowed_keys = {node["key"] for node in nodes}
    sentence_entity_map = {
        context_key: {entity_key for entity_key in entity_keys if entity_key in allowed_keys}
        for context_key, entity_keys in sentence_entity_map.items()
    }
    chunk_entity_map = {
        context_key: {entity_key for entity_key in entity_keys if entity_key in allowed_keys}
        for context_key, entity_keys in chunk_entity_map.items()
    }
    for node in nodes:
        node["sentence_profile"] = _build_context_profile(node["sentences"], sentence_entity_map, node["key"])
        node["chunk_profile"] = _build_context_profile(node["chunks"], chunk_entity_map, node["key"])

    totals = {
        "sentences": max(len(sentence_entity_map), 1),
        "chunks": max(len(chunk_entity_map), 1),
    }
    edges = _build_edges(nodes, totals)

    result = {
        "workspace_id": workspace_id,
        "workspace_name": summary.get("name", workspace_id),
        "model": model_key,
        "processed_article_count": len(processed_articles),
        "total_article_count": summary.get("article_count", 0),
        "unique_entity_count": int(aggregate_payload.get("unique_entity_count", len(point_map))),
        "total_entity_occurrences": int(aggregate_payload.get("total_entity_occurrences", sum(node["frequency"] for node in nodes))),
        "nodes": [
            {
                "key": node["key"],
                "entity": node["entity"],
                "label": node["label"],
                "frequency": node["frequency"],
                "article_count": node["article_count"],
                "x": node["x"],
                "y": node["y"],
            }
            for node in nodes
        ],
        "edges": edges,
        "signature": signature,
    }
    _write_cached_payload(cache_path, result)
    return result


def _build_edges(nodes: list[dict], totals: dict[str, int]) -> list[dict]:
    edges = []
    for index, source in enumerate(nodes):
        for target in nodes[index + 1:]:
            edge = _build_edge(source, target, totals)
            if edge:
                edges.append(edge)

    edges.sort(key=lambda item: (-item["score"], -item["sentence_cooccurrence"], item["source_entity"].lower()))
    return edges[: DEFAULT_OPTIONS["max_edges"]]


def _build_edge(source: dict, target: dict, totals: dict[str, int]) -> dict | None:
    sentence_intersection = _intersect_size(source["sentences"], target["sentences"])
    if sentence_intersection < DEFAULT_OPTIONS["min_sentence_cooccurrence"]:
        return None

    sentence_union = _union_size(source["sentences"], target["sentences"])
    chunk_intersection = _intersect_size(source["chunks"], target["chunks"])
    chunk_union = _union_size(source["chunks"], target["chunks"])

    sentence_jaccard = sentence_intersection / sentence_union if sentence_union else 0.0
    chunk_jaccard = chunk_intersection / chunk_union if chunk_union else 0.0
    overlap_strength = sentence_intersection / max(1, min(len(source["sentences"]), len(target["sentences"])))

    profile_sentence_cosine = _cosine_map_similarity(source["sentence_profile"], target["sentence_profile"])
    profile_chunk_cosine = _cosine_map_similarity(source["chunk_profile"], target["chunk_profile"])
    profile_similarity = (0.7 * profile_sentence_cosine) + (0.3 * profile_chunk_cosine)

    sentence_npmi = _compute_npmi(
        sentence_intersection,
        len(source["sentences"]),
        len(target["sentences"]),
        totals["sentences"],
    )
    chunk_npmi = _compute_npmi(
        chunk_intersection,
        len(source["chunks"]),
        len(target["chunks"]),
        totals["chunks"],
    )
    association_strength = (0.8 * sentence_npmi) + (0.2 * chunk_npmi)

    score = (
        (0.25 * sentence_jaccard) +
        (0.15 * chunk_jaccard) +
        (0.15 * overlap_strength) +
        (0.20 * profile_similarity) +
        (0.25 * association_strength)
    )
    if score < DEFAULT_OPTIONS["score_threshold"]:
        return None

    return {
        "key": f"{source['key']}__{target['key']}",
        "source": source["key"],
        "target": target["key"],
        "source_entity": source["entity"],
        "target_entity": target["entity"],
        "score": round(score, 6),
        "sentence_cooccurrence": sentence_intersection,
        "chunk_jaccard": round(chunk_jaccard, 6),
        "profile_similarity": round(profile_similarity, 6),
        "sentence_npmi": round(sentence_npmi, 6),
    }


def _workspace_relations_path(workspace_id: str, model_key: str) -> Path:
    return WORKSPACES_DIR / workspace_id / f"relations_{model_key}.json"


def _read_cached_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cached_payload(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_signature(processed_articles: list[dict], model_key: str, projection_signature: str) -> str:
    digest = hashlib.sha256()
    digest.update(model_key.encode("utf-8"))
    digest.update(projection_signature.encode("utf-8"))
    for article in processed_articles:
        article_id = article["id"]
        tsne_path = ARTICLES_DIR / article_id / f"tsne_{model_key}.json"
        stamp = tsne_path.stat().st_mtime_ns if tsne_path.exists() else 0
        digest.update(f"{article_id}|{stamp}".encode("utf-8"))
    return digest.hexdigest()


def _normalize_entity(value: str) -> str:
    return " ".join(str(value or "").lower().split()).strip()


def _dominant_label(counter: Counter) -> str:
    if not counter:
        return "UNKNOWN"
    return counter.most_common(1)[0][0] or "UNKNOWN"


def _build_context_profile(contexts: set[str], context_entity_map: dict[str, set[str]], self_key: str) -> dict[str, float]:
    profile: dict[str, float] = {}
    for context_key in contexts:
        for entity_key in context_entity_map.get(context_key, set()):
            if entity_key == self_key:
                continue
            profile[entity_key] = profile.get(entity_key, 0.0) + 1.0
    return profile


def _intersect_size(left: set[str], right: set[str]) -> int:
    if not left or not right:
        return 0
    if len(left) > len(right):
        left, right = right, left
    return sum(1 for item in left if item in right)


def _union_size(left: set[str], right: set[str]) -> int:
    return len(left) + len(right) - _intersect_size(left, right)


def _cosine_map_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    numerator = sum(value * right.get(key, 0.0) for key, value in left.items())
    if numerator <= 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _compute_npmi(intersection: int, left_count: int, right_count: int, total_contexts: int) -> float:
    if intersection <= 0 or left_count <= 0 or right_count <= 0 or total_contexts <= 0:
        return 0.0

    p_xy = intersection / total_contexts
    p_x = left_count / total_contexts
    p_y = right_count / total_contexts
    if p_xy <= 0 or p_x <= 0 or p_y <= 0:
        return 0.0

    denominator = -math.log(p_xy)
    if denominator <= 0:
        return 0.0

    pmi = math.log(p_xy / (p_x * p_y))
    npmi = pmi / denominator
    return max(0.0, min(1.0, npmi))
