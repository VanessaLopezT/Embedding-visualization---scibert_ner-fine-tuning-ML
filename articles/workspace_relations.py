"""
Construcción y caché de grafos de coocurrencia / relaciones.

Incluye:
- Workspace multi-artículo: `build_workspace_relations` (posiciones desde aggregate del workspace).
- Artículo individual (panel): `build_article_relations` — usa `article_projection` para posiciones,
  no el agregado en disco del workspace.

Comparte utilidades (_build_edges, modo ambos, etc.) entre ambos casos.

Usa solo resultados ya procesados por artículo/modelo:
- tsne_<model>.json para contexto y coocurrencia
- aggregate_<model>.json para posiciones agregadas en 2D

No vuelve a correr NER ni embeddings del modelo.

Modo vista combinada (ambos):
- Capas mono TechBERT-only y PatVet-only = mismas aristas que `build_workspace_relations(..., tech|cmt)`
  restringidas a claves que existen en el agregado combinado (vértices = lienzo TSNE ambos).
- Base global = union mono-tech + mono-cmt + cruces dominant_origin tech × cmt (y puentes semánticos).
- Aristas Tech↔PatVetBERT contextuales: dominant_origin tech × cmt con coocurrencia de frase o,
  si no hay frases comparables, solape fuerte de chunk entre modelos.
- Aristas Tech↔PatVetBERT semanticas: similitud coseno entre centroides del embedding concatenado
  tech+cmt (el mismo espacio que la proyeccion ambos), limitadas a entidades que comparten al menos
  un articulo del workspace.

El grafo combinado ya no usa el atajo «solo chunks» para pares mismo-modelo: chunk_key es
compartido entre origenes y relacionaba casi todas las entidades del mismo parrafo.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from django.conf import settings

from .combined_results import (
    canonical_model_key,
    is_combined_model,
    pad_workspace_concat_embedding,
    workspace_combined_occurrence_rows,
    workspace_combined_points_for_relations,
)
from .article_projection import build_article_aggregate_projection
from .workspace_projection import build_workspace_projection
from .workspace_service import get_workspace_summary


DATA_DIR = Path(settings.DATA_DIR)
ARTICLES_DIR = DATA_DIR / "articles"
WORKSPACES_DIR = DATA_DIR / "workspaces"


DEFAULT_OPTIONS = {
    "min_entity_frequency": 1,
    "min_sentence_cooccurrence": 2,
    "score_threshold": 0.24,
    # Tope por grafo mono (tech/cmt): evita payloads enormes; las mejores aristas por score.
    "max_edges": 250,
}

# PatVetBERT suele densificar entidades y multiplica pares triviales: más estricto que TechBERT.
CMT_WORKSPACE_RELATION_OPTIONS = {
    **DEFAULT_OPTIONS,
    "score_threshold": 0.30,
    "profile_term_damp": 0.62,
    "association_term_damp": 0.88,
}

# Vista combinada: los sentence_id de tech y cmt no siempre son comparables; se
# namespacen por origen y se endurecen aristas que solo apoyan en párrafo + perfil.
COMBINED_RELATION_OPTIONS = {
    "min_entity_frequency": 1,
    "min_sentence_cooccurrence": 2,
    # Solo aristas tech↔cmt sin coocurrencia de frase comparable: exigir varios chunks compartidos.
    "min_chunk_cross_model": 4,
    "cross_model_score_relief": 0.045,
    "score_threshold": 0.24,
    "max_edges": 90,
    "profile_term_damp": 0.58,
    "association_term_damp": 0.85,
    # Puentes semanticos tech×cmt (cos sobre centroides concat tech+cmt en articulos del workspace).
    "semantic_cosine_min": 0.76,
    "semantic_profile_min": 0.10,
    "cross_model_min_shared_articles": 1,
    "cross_model_min_shared_articles_weak": 2,
    # Penaliza pares dominados por nodos "hub" (muy conectivos) en cruces tech↔cmt.
    "cross_hub_gamma": 0.24,
    "semantic_cross_max_edges": 110,
}

RELATIONS_ALGO_VERSION = "merge_tc_v28_cmt_stricter_mono_cap"

# max_edges / max_total / semantic_cross_max_edges <= 0 en la vista ambos = sin recorte por cantidad
# (sigue aplicando score_threshold y coocurrencia mínima).


def _edges_respecting_max_cap(edges: list[dict], options: dict) -> list[dict]:
    raw = options.get("max_edges", DEFAULT_OPTIONS["max_edges"])
    try:
        mx = int(raw)
    except (TypeError, ValueError):
        mx = int(DEFAULT_OPTIONS["max_edges"])
    if mx <= 0:
        return edges
    return edges[:mx]


def _undirected_pair_key(source_key: str, target_key: str) -> tuple[str, str]:
    if source_key <= target_key:
        return (source_key, target_key)
    return (target_key, source_key)


def _dedupe_edges_by_pair_best_score(edges: list[dict]) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for edge in edges:
        sk = str(edge.get("source") or "").strip()
        tk = str(edge.get("target") or "").strip()
        if not sk or not tk:
            continue
        pk = _undirected_pair_key(sk, tk)
        sc = float(edge.get("score") or 0.0)
        prev = best.get(pk)
        if prev is None or sc > float(prev.get("score") or 0.0):
            best[pk] = edge
    return list(best.values())


def _ambos_stamp_mono_edge_key(edge: dict, layer: str) -> None:
    """Claves únicas entre capas mono (mismo par existe en tech y en cmt con evidencia distinta)."""
    sk = str(edge.get("source") or "").strip()
    tk = str(edge.get("target") or "").strip()
    if not sk or not tk:
        return
    a, b = _undirected_pair_key(sk, tk)
    edge["key"] = f"{a}__{b}__{layer}"
    edge["relation_mono_layer"] = layer


def _mono_workspace_edges_from_standalone(
    workspace_id: str,
    model_mk: str,
    combined_node_keys: set[str],
    *,
    mono_payload: dict | None = None,
) -> list[dict]:
    base = canonical_model_key(model_mk)
    if base not in {"tech", "cmt"}:
        return []
    layer = "mono_tech" if base == "tech" else "mono_cmt"
    payload = mono_payload if mono_payload is not None else build_workspace_relations(workspace_id, base)
    out: list[dict] = []
    for raw in payload.get("edges") or []:
        sk = str(raw.get("source") or "").strip()
        tk = str(raw.get("target") or "").strip()
        if not sk or not tk:
            continue
        if sk not in combined_node_keys or tk not in combined_node_keys:
            continue
        e = dict(raw)
        _ambos_stamp_mono_edge_key(e, layer)
        out.append(e)
    return out


def _mono_article_edges_from_standalone(
    article_id: str,
    model_mk: str,
    combined_node_keys: set[str],
    *,
    mono_payload: dict | None = None,
) -> list[dict]:
    base = canonical_model_key(model_mk)
    if base not in {"tech", "cmt"}:
        return []
    layer = "mono_tech" if base == "tech" else "mono_cmt"
    payload = mono_payload if mono_payload is not None else build_article_relations(article_id, base)
    out: list[dict] = []
    for raw in payload.get("edges") or []:
        sk = str(raw.get("source") or "").strip()
        tk = str(raw.get("target") or "").strip()
        if not sk or not tk:
            continue
        if sk not in combined_node_keys or tk not in combined_node_keys:
            continue
        e = dict(raw)
        _ambos_stamp_mono_edge_key(e, layer)
        out.append(e)
    return out


def _inject_missing_mono_nodes_into_combined(
    combined_nodes: list[dict],
    mono_nodes: list[dict],
    origin: str,
) -> None:
    by_key = {
        str(node.get("key") or "").strip(): node
        for node in combined_nodes
        if str(node.get("key") or "").strip()
    }
    for raw in mono_nodes:
        key = str(raw.get("key") or "").strip()
        if not key or key in by_key:
            continue
        node = {
            "key": key,
            "entity": raw.get("entity", key),
            "label": raw.get("label") or "UNKNOWN",
            "frequency": int(raw.get("frequency") or 0),
            "article_count": int(raw.get("article_count") or 0),
            "x": float(raw.get("x", 0.0)),
            "y": float(raw.get("y", 0.0)),
            "sentences": set(),
            "chunks": set(),
            "sentence_profile": {},
            "chunk_profile": {},
            "_article_ids": set(),
            "dominant_origin": origin,
        }
        combined_nodes.append(node)
        by_key[key] = node


def build_workspace_relations(workspace_id: str, model_key: str) -> dict:
    model_key = canonical_model_key(model_key)
    summary = get_workspace_summary(workspace_id)
    workspace_articles_exists = [
        article for article in summary.get("articles", []) if article.get("exists")
    ]
    workspace_mono_tech_articles = [
        a for a in workspace_articles_exists if a.get("models", {}).get("tech") == "processed"
    ]
    workspace_mono_cmt_articles = [
        a for a in workspace_articles_exists if a.get("models", {}).get("cmt") == "processed"
    ]
    processed_articles = [
        article
        for article in summary.get("articles", [])
        if article.get("exists") and article.get("models", {}).get(model_key) == "processed"
    ]

    aggregate_payload = build_workspace_projection(workspace_id, model_key)
    cache_path = _workspace_relations_path(workspace_id, model_key)
    signature = _build_signature(
        processed_articles,
        model_key,
        aggregate_payload.get("signature", ""),
        is_combined_model(model_key),
        mono_tech_articles=(
            workspace_mono_tech_articles if is_combined_model(model_key) else None
        ),
        mono_cmt_articles=(
            workspace_mono_cmt_articles if is_combined_model(model_key) else None
        ),
    )
    cached = _read_cached_payload(cache_path)
    if cached and cached.get("signature") == signature:
        # En ambos, no fijar un cache sin nodos cuando el workspace ya reporta
        # artículos procesados para esta vista.
        if not (
            is_combined_model(model_key)
            and processed_articles
            and not (cached.get("nodes") or [])
        ):
            return cached

    points = aggregate_payload.get("points", [])
    point_map = {str(point.get("key") or ""): point for point in points}
    if not point_map:
        if is_combined_model(model_key):
            _floor_opts = COMBINED_RELATION_OPTIONS
        elif canonical_model_key(model_key) == "cmt":
            _floor_opts = CMT_WORKSPACE_RELATION_OPTIONS
        else:
            _floor_opts = DEFAULT_OPTIONS
        result = {
            "workspace_id": workspace_id,
            "workspace_name": summary.get("name", workspace_id),
            "model": model_key,
            "score_threshold_used": float(_floor_opts["score_threshold"]),
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
        if is_combined_model(model_key):
            article_points = workspace_combined_points_for_relations(article_id)
        else:
            tsne_path = ARTICLES_DIR / article_id / f"tsne_{model_key}.json"
            if not tsne_path.exists():
                continue
            try:
                article_points = json.loads(tsne_path.read_text(encoding="utf-8"))
            except Exception:
                continue

        combined = is_combined_model(model_key)
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
                **({"origins": Counter()} if combined else {}),
            })

            stats["labels"][str(point.get("label") or "UNKNOWN")] += 1
            stats["frequency"] += 1
            stats["article_ids"].add(article_id)
            if combined:
                o = str(point.get("origin") or "joint").strip().lower() or "joint"
                stats["origins"][o] += 1

            sentence_id = point.get("sentence_id")
            if sentence_id is not None:
                if combined:
                    origin = str(point.get("origin") or "joint").strip() or "joint"
                    sentence_key = f"{article_id}::{origin}::s::{sentence_id}"
                    # Misma frase lógica para tech y cmt (como en vista por artículo con sentence_id compartido).
                    cross_sentence_key = f"{article_id}::cross::s::{sentence_id}"
                    stats["sentences"].add(sentence_key)
                    stats["sentences"].add(cross_sentence_key)
                    sentence_entity_map[sentence_key].add(key)
                    sentence_entity_map[cross_sentence_key].add(key)
                else:
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

        node_dict = {
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
            "_article_ids": stats["article_ids"],
        }
        if is_combined_model(model_key):
            origins = stats.get("origins", Counter())
            node_dict["dominant_origin"] = _dominant_label(origins) if origins else "joint"
        nodes.append(node_dict)

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
    if is_combined_model(model_key):
        edge_options = COMBINED_RELATION_OPTIONS
    elif canonical_model_key(model_key) == "cmt":
        edge_options = CMT_WORKSPACE_RELATION_OPTIONS
    else:
        edge_options = DEFAULT_OPTIONS

    if is_combined_model(model_key):
        tech_payload = build_workspace_relations(workspace_id, "tech")
        cmt_payload = build_workspace_relations(workspace_id, "cmt")
        _inject_missing_mono_nodes_into_combined(
            nodes,
            list(tech_payload.get("nodes") or []),
            "tech",
        )
        _inject_missing_mono_nodes_into_combined(
            nodes,
            list(cmt_payload.get("nodes") or []),
            "cmt",
        )
        allowed_node_keys = {str(n.get("key") or "") for n in nodes if n.get("key")}

        try:
            tech_edges = _mono_workspace_edges_from_standalone(
                workspace_id, "tech", allowed_node_keys, mono_payload=tech_payload,
            )
            cmt_edges = _mono_workspace_edges_from_standalone(
                workspace_id, "cmt", allowed_node_keys, mono_payload=cmt_payload,
            )
            cross_opts = {**edge_options, "max_edges": 0}
            cross_edges = _build_edges_cross_model_only(nodes, totals, cross_opts)
            unit_emb, articles_for = _ambos_unit_centroids(processed_articles, allowed_node_keys)
            semantic_opts = {**edge_options, "semantic_cross_max_edges": 0}
            semantic_edges = _build_semantic_cross_edges_ambos(
                nodes, unit_emb, articles_for, semantic_opts,
            )
            edges = _merge_ambos_relation_layers(
                tech_edges,
                cmt_edges,
                cross_edges + semantic_edges,
                max_total=0,
                nodes=nodes,
            )
        except Exception:
            try:
                tech_edges = _mono_workspace_edges_from_standalone(
                    workspace_id, "tech", allowed_node_keys, mono_payload=tech_payload,
                )
                cmt_edges = _mono_workspace_edges_from_standalone(
                    workspace_id, "cmt", allowed_node_keys, mono_payload=cmt_payload,
                )
                edges = _merge_ambos_relation_layers(
                    tech_edges,
                    cmt_edges,
                    [],
                    max_total=0,
                    nodes=nodes,
                )
            except Exception:
                edges = []
                _annotate_workspace_edge_endpoint_mix(nodes, edges)
    else:
        edges = _build_edges(nodes, totals, edge_options, combined=False)
        _annotate_workspace_edge_endpoint_mix(nodes, edges)

    result = {
        "workspace_id": workspace_id,
        "workspace_name": summary.get("name", workspace_id),
        "model": model_key,
        "score_threshold_used": float(edge_options["score_threshold"]),
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
                **({"dominant_origin": node["dominant_origin"]} if is_combined_model(model_key) else {}),
            }
            for node in nodes
        ],
        "edges": edges,
        "edge_breakdown": _workspace_edge_breakdown(edges) if is_combined_model(model_key) else {},
        "signature": signature,
    }
    _write_cached_payload(cache_path, result)
    return result


def build_article_relations(article_id: str, model_key: str) -> dict:
    from .workspace_service import _get_article_model_state, _read_article_meta

    model_key = canonical_model_key(model_key)
    aid = str(article_id).strip()
    meta = _read_article_meta(aid)
    if not meta:
        return {"error": "missing_article", "article_id": aid, "model": model_key}

    workspace_mono_tech_articles = (
        [{"id": aid, "exists": True}]
        if _get_article_model_state(aid, meta, "tech") == "processed"
        else []
    )
    workspace_mono_cmt_articles = (
        [{"id": aid, "exists": True}]
        if _get_article_model_state(aid, meta, "cmt") == "processed"
        else []
    )
    processed_articles = (
        [{"id": aid, "exists": True}]
        if _get_article_model_state(aid, meta, model_key) == "processed"
        else []
    )

    aggregate_payload = build_article_aggregate_projection(aid, model_key)
    cache_path = _article_relations_path(aid, model_key)
    signature = _build_signature(
        processed_articles,
        model_key,
        aggregate_payload.get("signature", ""),
        is_combined_model(model_key),
        mono_tech_articles=(
            workspace_mono_tech_articles if is_combined_model(model_key) else None
        ),
        mono_cmt_articles=(
            workspace_mono_cmt_articles if is_combined_model(model_key) else None
        ),
    )
    cached = _read_cached_payload(cache_path)
    if cached and cached.get("signature") == signature:
        if not (
            is_combined_model(model_key)
            and processed_articles
            and not (cached.get("nodes") or [])
        ):
            return cached

    article_display_name = aggregate_payload.get("article_original_name") or aid

    points = aggregate_payload.get("points", [])
    point_map = {str(point.get("key") or ""): point for point in points}
    if not point_map:
        if is_combined_model(model_key):
            _floor_opts = COMBINED_RELATION_OPTIONS
        elif canonical_model_key(model_key) == "cmt":
            _floor_opts = CMT_WORKSPACE_RELATION_OPTIONS
        else:
            _floor_opts = DEFAULT_OPTIONS
        result = {
            "article_id": aid,
            "article_name": article_display_name,
            "model": model_key,
            "score_threshold_used": float(_floor_opts["score_threshold"]),
            "processed_article_count": len(processed_articles),
            "total_article_count": 1,
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
        article_pid = str(article["id"])
        if is_combined_model(model_key):
            article_points = workspace_combined_points_for_relations(article_pid)
        else:
            tsne_path = ARTICLES_DIR / article_pid / f"tsne_{model_key}.json"
            if not tsne_path.exists():
                continue
            try:
                article_points = json.loads(tsne_path.read_text(encoding="utf-8"))
            except Exception:
                continue

        combined = is_combined_model(model_key)
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
                **({"origins": Counter()} if combined else {}),
            })

            stats["labels"][str(point.get("label") or "UNKNOWN")] += 1
            stats["frequency"] += 1
            stats["article_ids"].add(article_pid)
            if combined:
                o = str(point.get("origin") or "joint").strip().lower() or "joint"
                stats["origins"][o] += 1

            sentence_id = point.get("sentence_id")
            if sentence_id is not None:
                if combined:
                    origin = str(point.get("origin") or "joint").strip() or "joint"
                    sentence_key = f"{article_pid}::{origin}::s::{sentence_id}"
                    cross_sentence_key = f"{article_pid}::cross::s::{sentence_id}"
                    stats["sentences"].add(sentence_key)
                    stats["sentences"].add(cross_sentence_key)
                    sentence_entity_map[sentence_key].add(key)
                    sentence_entity_map[cross_sentence_key].add(key)
                else:
                    sentence_key = f"{article_pid}::s::{sentence_id}"
                    stats["sentences"].add(sentence_key)
                    sentence_entity_map[sentence_key].add(key)

            chunk_id = point.get("text_index")
            if chunk_id is not None:
                chunk_key = f"{article_pid}::c::{chunk_id}"
                stats["chunks"].add(chunk_key)
                chunk_entity_map[chunk_key].add(key)

    nodes = []
    for key, point in point_map.items():
        stats = entity_stats.get(key)
        if not stats:
            continue
        if stats["frequency"] < DEFAULT_OPTIONS["min_entity_frequency"]:
            continue

        node_dict = {
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
            "_article_ids": stats["article_ids"],
        }
        if is_combined_model(model_key):
            origins = stats.get("origins", Counter())
            node_dict["dominant_origin"] = _dominant_label(origins) if origins else "joint"
        nodes.append(node_dict)

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
    if is_combined_model(model_key):
        edge_options = COMBINED_RELATION_OPTIONS
    elif canonical_model_key(model_key) == "cmt":
        edge_options = CMT_WORKSPACE_RELATION_OPTIONS
    else:
        edge_options = DEFAULT_OPTIONS

    if is_combined_model(model_key):
        tech_payload = build_article_relations(aid, "tech")
        cmt_payload = build_article_relations(aid, "cmt")
        _inject_missing_mono_nodes_into_combined(
            nodes,
            list(tech_payload.get("nodes") or []),
            "tech",
        )
        _inject_missing_mono_nodes_into_combined(
            nodes,
            list(cmt_payload.get("nodes") or []),
            "cmt",
        )
        allowed_node_keys = {str(n.get("key") or "") for n in nodes if n.get("key")}

        try:
            tech_edges = _mono_article_edges_from_standalone(
                aid, "tech", allowed_node_keys, mono_payload=tech_payload,
            )
            cmt_edges = _mono_article_edges_from_standalone(
                aid, "cmt", allowed_node_keys, mono_payload=cmt_payload,
            )
            cross_opts = {**edge_options, "max_edges": 0}
            cross_edges = _build_edges_cross_model_only(nodes, totals, cross_opts)
            unit_emb, articles_for = _ambos_unit_centroids(processed_articles, allowed_node_keys)
            semantic_opts = {**edge_options, "semantic_cross_max_edges": 0}
            semantic_edges = _build_semantic_cross_edges_ambos(
                nodes, unit_emb, articles_for, semantic_opts,
            )
            edges = _merge_ambos_relation_layers(
                tech_edges,
                cmt_edges,
                cross_edges + semantic_edges,
                max_total=0,
                nodes=nodes,
            )
        except Exception:
            try:
                tech_edges = _mono_article_edges_from_standalone(
                    aid, "tech", allowed_node_keys, mono_payload=tech_payload,
                )
                cmt_edges = _mono_article_edges_from_standalone(
                    aid, "cmt", allowed_node_keys, mono_payload=cmt_payload,
                )
                edges = _merge_ambos_relation_layers(
                    tech_edges,
                    cmt_edges,
                    [],
                    max_total=0,
                    nodes=nodes,
                )
            except Exception:
                edges = []
                _annotate_workspace_edge_endpoint_mix(nodes, edges)
    else:
        edges = _build_edges(nodes, totals, edge_options, combined=False)
        _annotate_workspace_edge_endpoint_mix(nodes, edges)

    result = {
        "article_id": aid,
        "article_name": article_display_name,
        "model": model_key,
        "score_threshold_used": float(edge_options["score_threshold"]),
        "processed_article_count": len(processed_articles),
        "total_article_count": 1,
        "unique_entity_count": int(aggregate_payload.get("unique_entity_count", len(point_map))),
        "total_entity_occurrences": int(
            aggregate_payload.get("total_entity_occurrences", sum(node["frequency"] for node in nodes))
        ),
        "nodes": [
            {
                "key": node["key"],
                "entity": node["entity"],
                "label": node["label"],
                "frequency": node["frequency"],
                "article_count": node["article_count"],
                "x": node["x"],
                "y": node["y"],
                **({"dominant_origin": node["dominant_origin"]} if is_combined_model(model_key) else {}),
            }
            for node in nodes
        ],
        "edges": edges,
        "edge_breakdown": _workspace_edge_breakdown(edges) if is_combined_model(model_key) else {},
        "signature": signature,
    }
    _write_cached_payload(cache_path, result)
    return result


def _annotate_workspace_edge_endpoint_mix(nodes: list[dict], edges: list[dict]) -> None:
    """Marca aristas entre entidad mayoritaria tech y otra cmt (vista ambos), etc."""
    origin = {
        str(n.get("key") or ""): str(n.get("dominant_origin") or "joint").lower()
        for n in nodes
        if n.get("key")
    }
    for e in edges:
        oa = origin.get(str(e.get("source") or ""), "joint")
        ob = origin.get(str(e.get("target") or ""), "joint")
        if {oa, ob} == {"tech", "cmt"}:
            e["endpoint_model_mix"] = "tech_cmt"
        elif oa != ob and (oa == "joint" or ob == "joint"):
            e["endpoint_model_mix"] = "joint_mix"
        else:
            e["endpoint_model_mix"] = "mono"
        e.setdefault("weak_sentence_evidence", False)


def _workspace_edge_breakdown(edges: list[dict]) -> dict:
    return {
        "total": len(edges),
        "mono_tech": sum(1 for e in edges if e.get("relation_mono_layer") == "mono_tech"),
        "mono_cmt": sum(1 for e in edges if e.get("relation_mono_layer") == "mono_cmt"),
        "tech_cmt_cross": sum(1 for e in edges if e.get("endpoint_model_mix") == "tech_cmt"),
        "joint_mix": sum(1 for e in edges if e.get("endpoint_model_mix") == "joint_mix"),
        "mono_other": sum(1 for e in edges if e.get("endpoint_model_mix") == "mono"),
        "semantic_bridges": sum(1 for e in edges if bool(e.get("semantic_embedding_bridge"))),
    }


def _ambos_unit_centroids(
    processed_articles: list[dict],
    allowed_keys: set[str],
) -> tuple[dict[str, np.ndarray], dict[str, set[str]]]:
    """Centroides por entidad normalizada en espacio concat tech+cmt; vectores unitarios para coseno."""
    concat_len_max = 0
    rows_by_article: dict[str, list] = {}
    for article in processed_articles:
        aid = str(article.get("id") or "")
        if not aid:
            continue
        rows = workspace_combined_occurrence_rows(aid)
        rows_by_article[aid] = rows
        for row in rows:
            key_p = str(row.get("norm_entity") or "").strip()
            if not key_p or key_p not in allowed_keys:
                continue
            concat_len_max = max(concat_len_max, int(np.asarray(row["vector"]).size))

    sums: dict[str, np.ndarray] = {}
    counts: dict[str, int] = defaultdict(int)
    articles_for: dict[str, set[str]] = defaultdict(set)
    if concat_len_max <= 0:
        return {}, {}

    for article in processed_articles:
        aid = str(article.get("id") or "")
        if not aid:
            continue
        rows = rows_by_article.get(aid) or []
        if not rows:
            continue
        for row in rows:
            key = str(row.get("norm_entity") or "").strip()
            if not key or key not in allowed_keys:
                continue
            vec = pad_workspace_concat_embedding(row["vector"], concat_len_max)
            if key not in sums:
                sums[key] = vec.copy()
            else:
                sums[key] += vec
            counts[key] += 1
            articles_for[key].add(aid)
    unit: dict[str, np.ndarray] = {}
    for key, s in sums.items():
        c = s / max(counts[key], 1)
        norm = float(np.linalg.norm(c))
        if norm < 1e-12:
            continue
        unit[key] = c / norm
    return unit, articles_for


def _semantic_cosine_to_edge_score(cos: float, cos_min: float) -> float:
    span = max(1e-9, 1.0 - cos_min)
    u = max(0.0, min(1.0, (cos - cos_min) / span))
    return 0.37 + 0.51 * u


def _build_semantic_cross_edges_ambos(
    nodes: list[dict],
    unit_emb: dict[str, np.ndarray],
    articles_for: dict[str, set[str]],
    options: dict,
) -> list[dict]:
    """Puentes tech×cmt por cercania en embedding concatenado (sin re-ejecutar modelos)."""
    cos_min = float(options.get("semantic_cosine_min", 0.76))
    profile_min = float(options.get("semantic_profile_min", 0.10))
    try:
        cap = int(options.get("semantic_cross_max_edges", 52))
    except (TypeError, ValueError):
        cap = 52
    if not unit_emb:
        return []

    tech_nodes = [n for n in nodes if str(n.get("dominant_origin") or "").lower() == "tech"]
    cmt_nodes = [n for n in nodes if str(n.get("dominant_origin") or "").lower() == "cmt"]
    edges: list[dict] = []

    for ta in tech_nodes:
        ka = str(ta.get("key") or "")
        ea = unit_emb.get(ka)
        if ea is None:
            continue
        arts_a = articles_for.get(ka, set())
        for tb in cmt_nodes:
            kb = str(tb.get("key") or "")
            eb = unit_emb.get(kb)
            if eb is None:
                continue
            if not (arts_a & articles_for.get(kb, set())):
                continue
            cos = float(np.dot(ea, eb))
            if cos < cos_min:
                continue
            profile_sentence_cos = _cosine_map_similarity(
                ta.get("sentence_profile") or {},
                tb.get("sentence_profile") or {},
            )
            profile_chunk_cos = _cosine_map_similarity(
                ta.get("chunk_profile") or {},
                tb.get("chunk_profile") or {},
            )
            profile_similarity = (0.72 * profile_sentence_cos) + (0.28 * profile_chunk_cos)
            if profile_similarity < profile_min:
                continue
            shared_articles = len(arts_a & articles_for.get(kb, set()))
            score = _semantic_cosine_to_edge_score(cos, cos_min)
            score += 0.12 * min(1.0, profile_similarity)
            score += 0.035 * min(1.0, shared_articles / 3.0)
            hub_penalty = _cross_hub_penalty(ta, tb, options)
            score *= hub_penalty
            edges.append({
                "key": f"{ka}__{kb}__emb",
                "source": ka,
                "target": kb,
                "source_entity": ta.get("entity", ka),
                "target_entity": tb.get("entity", kb),
                "score": round(min(0.985, score), 6),
                "sentence_cooccurrence": 0,
                "chunk_jaccard": 0.0,
                "profile_similarity": round(profile_similarity, 6),
                "sentence_npmi": 0.0,
                "weak_sentence_evidence": False,
                "semantic_embedding_bridge": True,
                "embedding_cosine": round(cos, 6),
            })

    edges.sort(
        key=lambda e: (-float(e.get("score") or 0.0), -float(e.get("embedding_cosine") or 0.0)),
    )
    if cap <= 0:
        return edges
    return edges[:cap]


def _merge_ambos_relation_layers(
    tech_edges: list[dict],
    cmt_edges: list[dict],
    cross_edges: list[dict],
    *,
    max_total: int,
    nodes: list[dict],
) -> list[dict]:
    """
    Vista ambos: unión TechBERT-only + PatVet-only + cruces tech×cmt (+ semánticas).
    - No deduplicar la misma pareja entre grafos mono de cada modelo: son evidencias separadas.
    - Si max_total > 0 y len(mono)+len(cruce) supera ese techo: se mantienen íntegras las mono
      y se trunca solo la capa cruzada por score.
    - max_total <= 0: sin truncar la capa cruzada (unión completa tras dedupe dentro de cada subcapa).
    """
    dedupe_tech = _dedupe_edges_by_pair_best_score(tech_edges)
    dedupe_cmt = _dedupe_edges_by_pair_best_score(cmt_edges)
    dedupe_cross = _dedupe_edges_by_pair_best_score(cross_edges)

    mono: list[dict] = []
    for edge in dedupe_tech:
        e = dict(edge)
        _ambos_stamp_mono_edge_key(e, "mono_tech")
        mono.append(e)
    for edge in dedupe_cmt:
        e = dict(edge)
        _ambos_stamp_mono_edge_key(e, "mono_cmt")
        mono.append(e)

    cross_sorted = sorted(
        dedupe_cross,
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -float(item.get("sentence_cooccurrence") or 0.0),
            str(item.get("source_entity") or "").lower(),
        ),
    )

    if max_total is None or int(max_total) <= 0:
        cross_trimmed = cross_sorted
    else:
        budget_cross = max(0, int(max_total) - len(mono))
        cross_trimmed = cross_sorted[:budget_cross] if budget_cross < len(cross_sorted) else cross_sorted

    merged = mono + cross_trimmed
    _annotate_workspace_edge_endpoint_mix(nodes, merged)

    def _sort_key(item: dict) -> tuple:
        mix = str(item.get("endpoint_model_mix") or "mono")
        cross_rank = 0 if mix == "tech_cmt" else (1 if mix == "joint_mix" else 2)
        weak_only = bool(item.get("weak_sentence_evidence"))
        weak_rank = 0 if (mix == "tech_cmt" and weak_only) else 1
        return (
            cross_rank,
            weak_rank,
            -float(item.get("score") or 0.0),
            -float(item.get("sentence_cooccurrence") or 0.0),
            str(item.get("source_entity") or "").lower(),
        )

    merged.sort(key=_sort_key)
    return merged


def _build_edges_cross_model_only(nodes: list[dict], totals: dict[str, int], options: dict) -> list[dict]:
    """Solo pares con dominant_origin tech × cmt (sin joint)."""
    edges: list[dict] = []
    n = len(nodes)
    for i in range(n):
        source = nodes[i]
        oa = str(source.get("dominant_origin") or "joint").lower()
        for j in range(i + 1, n):
            target = nodes[j]
            ob = str(target.get("dominant_origin") or "joint").lower()
            if {oa, ob} != {"tech", "cmt"}:
                continue
            edge = _build_edge(source, target, totals, options, combined=True)
            if edge:
                edges.append(edge)

    edges.sort(
        key=lambda item: (-item["score"], -item["sentence_cooccurrence"], item["source_entity"].lower()),
    )
    return _edges_respecting_max_cap(edges, options)


def _build_edges(nodes: list[dict], totals: dict[str, int], options: dict, combined: bool) -> list[dict]:
    edges = []
    for index, source in enumerate(nodes):
        for target in nodes[index + 1:]:
            edge = _build_edge(source, target, totals, options, combined=combined)
            if edge:
                edges.append(edge)

    edges.sort(key=lambda item: (-item["score"], -item["sentence_cooccurrence"], item["source_entity"].lower()))
    return _edges_respecting_max_cap(edges, options)


def _build_edge(source: dict, target: dict, totals: dict[str, int], options: dict, combined: bool) -> dict | None:
    cross_tech_cmt = False
    if combined:
        oa = str(source.get("dominant_origin") or "joint").lower()
        ob = str(target.get("dominant_origin") or "joint").lower()
        cross_tech_cmt = {oa, ob} == {"tech", "cmt"}

    min_sentence = int(options["min_sentence_cooccurrence"])
    sentence_intersection = _intersect_size(source["sentences"], target["sentences"])
    chunk_intersection = _intersect_size(source["chunks"], target["chunks"])
    shared_articles = _intersect_size(
        set(source.get("_article_ids") or []),
        set(target.get("_article_ids") or []),
    )

    if sentence_intersection < min_sentence:
        # Sin atajo solo-chunks para mismo modelo: chunk_key es compartido entre Tech/CMT y
        # relacionaba masivamente entidades del mismo párrafo. Solo pares tech×cmt pueden
        # usar solape de párrafos cuando las frases no son comparables entre modelos.
        if combined and cross_tech_cmt:
            min_shared_weak = int(options.get("cross_model_min_shared_articles_weak", 2))
            if shared_articles < min_shared_weak:
                return None
            min_chunk_weak = int(options.get("min_chunk_cross_model", 4))
            if chunk_intersection < min_chunk_weak:
                return None
        else:
            return None

    sentence_union = _union_size(source["sentences"], target["sentences"])
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

    profile_damp = float(options.get("profile_term_damp", 1.0))
    assoc_damp = float(options.get("association_term_damp", 1.0))
    if combined and sentence_intersection < min_sentence:
        profile_damp *= 0.72

    if combined and cross_tech_cmt:
        min_shared = int(options.get("cross_model_min_shared_articles", 1))
        if shared_articles < min_shared:
            return None

    score = (
        (0.25 * sentence_jaccard) +
        (0.15 * chunk_jaccard) +
        (0.15 * overlap_strength) +
        (0.20 * profile_similarity * profile_damp) +
        (0.25 * association_strength * assoc_damp)
    )
    threshold = float(options["score_threshold"])
    if combined and cross_tech_cmt:
        # Favorece pares cross-model respaldados en múltiples artículos del workspace.
        score += 0.03 * min(1.0, shared_articles / 3.0)
        score *= _cross_hub_penalty(source, target, options)
        threshold -= float(options.get("cross_model_score_relief", 0.0))
        threshold = max(0.18, threshold)
    if score < threshold:
        return None

    weak_sentence_evidence = bool(combined and sentence_intersection < min_sentence)

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
        "weak_sentence_evidence": weak_sentence_evidence,
    }


def _cross_hub_penalty(source: dict, target: dict, options: dict) -> float:
    """
    Penaliza pares tech↔cmt dominados por nodos "hub" (contexto demasiado general).
    Usa tamaño de perfiles de frase/chunk para reducir score en cruces muy genéricos.
    """
    gamma = float(options.get("cross_hub_gamma", 0.24))
    if gamma <= 0:
        return 1.0
    s_sent = len(source.get("sentence_profile") or {})
    t_sent = len(target.get("sentence_profile") or {})
    s_chunk = len(source.get("chunk_profile") or {})
    t_chunk = len(target.get("chunk_profile") or {})
    hub_size = max(s_sent + s_chunk, t_sent + t_chunk)
    if hub_size <= 8:
        return 1.0
    # Escala logarítmica suave: mantiene pares específicos y baja hubs globales.
    damp = 1.0 / (1.0 + gamma * math.log1p(hub_size - 8))
    return max(0.55, min(1.0, damp))


def _workspace_relations_path(workspace_id: str, model_key: str) -> Path:
    return WORKSPACES_DIR / workspace_id / f"relations_{model_key}.json"


def _article_relations_path(article_id: str, model_key: str) -> Path:
    return ARTICLES_DIR / article_id / f"relations_article_{model_key}.json"


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


def _build_signature(
    processed_articles: list[dict],
    model_key: str,
    projection_signature: str,
    combined_mode: bool = False,
    *,
    mono_tech_articles: list[dict] | None = None,
    mono_cmt_articles: list[dict] | None = None,
) -> str:
    digest = hashlib.sha256()
    digest.update(model_key.encode("utf-8"))
    digest.update(projection_signature.encode("utf-8"))
    digest.update(RELATIONS_ALGO_VERSION.encode("utf-8"))
    digest.update(b"|combined|" if combined_mode else b"|single|")
    for article in processed_articles:
        article_id = article["id"]
        if is_combined_model(model_key):
            tech_path = ARTICLES_DIR / article_id / "embeddings_tech.npz"
            cmt_path = ARTICLES_DIR / article_id / "embeddings_cmt.npz"
            tech_stamp = tech_path.stat().st_mtime_ns if tech_path.exists() else 0
            cmt_stamp = cmt_path.stat().st_mtime_ns if cmt_path.exists() else 0
            digest.update(f"{article_id}|{tech_stamp}|{cmt_stamp}|occ_rows".encode("utf-8"))
            continue
        tsne_path = ARTICLES_DIR / article_id / f"tsne_{model_key}.json"
        stamp = tsne_path.stat().st_mtime_ns if tsne_path.exists() else 0
        digest.update(f"{article_id}|{stamp}".encode("utf-8"))
    # Vista ambos: capas mono leen tsne_* de todos los artículos con tech/cmt procesado (alcance igual
    # que grafos workspace por modelo), no sólo ambos_processed; debe invalidar caché al cambiar esos artefactos.
    if combined_mode and is_combined_model(model_key):
        if mono_tech_articles:
            digest.update(b"|mono_ws_tech_tsne|")
            for aid in sorted({str(a.get("id") or "").strip() for a in mono_tech_articles} - {""}):
                tp = ARTICLES_DIR / aid / "tsne_tech.json"
                stamp = tp.stat().st_mtime_ns if tp.exists() else 0
                digest.update(f"{aid}|{stamp}".encode())
        if mono_cmt_articles:
            digest.update(b"|mono_ws_cmt_tsne|")
            for aid in sorted({str(a.get("id") or "").strip() for a in mono_cmt_articles} - {""}):
                cp = ARTICLES_DIR / aid / "tsne_cmt.json"
                stamp = cp.stat().st_mtime_ns if cp.exists() else 0
                digest.update(f"{aid}|{stamp}".encode())
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
