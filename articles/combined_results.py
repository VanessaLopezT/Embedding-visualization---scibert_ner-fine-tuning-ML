from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from django.conf import settings
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE


DATA_DIR = Path(settings.DATA_DIR)
ARTICLES_DIR = DATA_DIR / "articles"

BASE_MODEL_KEYS = ("tech", "cmt")
COMBINED_MODEL_KEYS = {"ambos", "both", "combined"}
CANONICAL_COMBINED_KEY = "ambos"


class CombinedInputsMissingError(RuntimeError):
    def __init__(self, article_id: str, missing_models: list[str], artifact_type: str):
        self.article_id = article_id
        self.missing_models = missing_models
        self.artifact_type = artifact_type
        missing_text = ", ".join(missing_models)
        super().__init__(
            f"El artículo '{article_id}' no tiene resultados {artifact_type} para: {missing_text}. "
            "Procesa primero esos modelos base (tech/cmt)."
        )


def canonical_model_key(model_key: str | None) -> str:
    key = str(model_key or "").strip().lower()
    if key in COMBINED_MODEL_KEYS:
        return CANONICAL_COMBINED_KEY
    return key or "tech"


def is_combined_model(model_key: str | None) -> bool:
    return canonical_model_key(model_key) == CANONICAL_COMBINED_KEY


def get_supported_model_keys(base_keys: list[str] | tuple[str, ...]) -> list[str]:
    keys = [str(key) for key in base_keys]
    if CANONICAL_COMBINED_KEY not in keys:
        keys.append(CANONICAL_COMBINED_KEY)
    return keys


def get_missing_base_models_for_article(article_id: str, artifact_type: str = "tsne") -> list[str]:
    missing = []
    for model_key in BASE_MODEL_KEYS:
        path = _artifact_path(article_id, model_key, artifact_type)
        if not path.exists():
            missing.append(model_key)
    return missing


def _mono_tsne_points_list(article_id: str, model_key: str) -> list[dict]:
    raw = _read_json_array(_artifact_path(article_id, model_key, "tsne"))
    if not raw:
        return []
    return [p for p in raw if isinstance(p, dict) and p.get("x") is not None and p.get("y") is not None]


def _horizontal_shift_second_tsne_cloud(left: list[dict], right: list[dict], margin: float = 8.0) -> None:
    xs_l = [float(p["x"]) for p in left]
    xs_r = [float(p["x"]) for p in right]
    if not xs_l or not xs_r:
        return
    shift = max(xs_l) - min(xs_r) + margin
    for p in right:
        p["x"] = float(p["x"]) + shift


def _mono_tsne_fallback_for_ambos_article(article_id: str) -> list[dict]:
    """
    Cuando el emparejamiento concat (workspace_combined_occurrence_rows) no produce filas pero
    al menos un modelo base sí tiene proyección t-SNE guardada (p. ej. el otro modelo no detectó
    entidades), reutiliza esos puntos para la vista «ambos» del artículo individual.
    """
    tech = _mono_tsne_points_list(article_id, "tech")
    cmt = _mono_tsne_points_list(article_id, "cmt")
    if not tech and not cmt:
        return []

    def stamp(points: list[dict], origin: str, start_id: int) -> tuple[list[dict], int]:
        out: list[dict] = []
        i = start_id
        for p in points:
            q = dict(p)
            q["origin"] = origin
            q["id"] = i
            i += 1
            st = q.get("sentence_text")
            q["sentence_text"] = "" if st is None else str(st)
            out.append(q)
        return out, i

    if tech and not cmt:
        pts, _ = stamp(tech, "tech", 0)
        return pts
    if cmt and not tech:
        pts, _ = stamp(cmt, "cmt", 0)
        return pts

    tech_pts, next_id = stamp(tech, "tech", 0)
    cmt_pts, _ = stamp(cmt, "cmt", next_id)
    _horizontal_shift_second_tsne_cloud(tech_pts, cmt_pts)
    return tech_pts + cmt_pts


def build_combined_article_tsne(article_id: str) -> list[dict]:
    missing = get_missing_base_models_for_article(article_id, "embeddings")
    if missing:
        raise CombinedInputsMissingError(article_id, missing, "embeddings")

    signature = _build_combined_signature(article_id)
    cache_meta_path = _combined_meta_path(article_id, "tsne")
    cache_tsne_path = _artifact_path(article_id, CANONICAL_COMBINED_KEY, "tsne")
    cached_meta = _read_json(cache_meta_path)

    if cache_tsne_path.exists() and cached_meta.get("signature") == signature:
        cached = _read_json_array(cache_tsne_path)
        if cached is not None:
            # Robustez: no persistir un cache vacío "pegado" cuando ya existen
            # entradas base para reconstruir la vista combinada.
            if cached:
                return cached

    rows = workspace_combined_occurrence_rows(article_id)
    if not rows:
        fallback = _mono_tsne_fallback_for_ambos_article(article_id)
        if fallback:
            coords_xy = np.array([[float(p["x"]), float(p["y"])] for p in fallback], dtype=np.float64)
            coords_xy = _combined_center_xy(coords_xy)
            coords_xy = _combined_scale_xy_visual(coords_xy, target_rms=52.0)
            for i, p in enumerate(fallback):
                p["x"] = float(coords_xy[i][0])
                p["y"] = float(coords_xy[i][1])
            cache_tsne_path.parent.mkdir(parents=True, exist_ok=True)
            cache_tsne_path.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")
            _write_json(cache_meta_path, {"signature": signature, "count": len(fallback)})
            return fallback
        cache_tsne_path.parent.mkdir(parents=True, exist_ok=True)
        cache_tsne_path.write_text("[]", encoding="utf-8")
        _write_json(cache_meta_path, {"signature": signature, "count": 0})
        return []

    matrix = np.vstack([r["vector"] for r in rows]).astype(np.float32)
    coords_xy = np.asarray(_reduce_to_2d(matrix), dtype=np.float64)
    coords_xy = _combined_center_xy(coords_xy)
    coords_xy = _combined_scale_xy_visual(coords_xy, target_rms=52.0)

    final_points = []
    for index, row in enumerate(rows):
        final_points.append({
            "id": index,
            "x": float(coords_xy[index][0]),
            "y": float(coords_xy[index][1]),
            "label": row["label"],
            "entity": row["entity_display"],
            "text_index": row["text_index"],
            "sentence_id": row["sentence_id"],
            "start": row.get("start"),
            "end": row.get("end"),
            "sentence_text": row.get("sentence_text") or "",
            "origin": row.get("origin") or "joint",
        })

    cache_tsne_path.parent.mkdir(parents=True, exist_ok=True)
    cache_tsne_path.write_text(json.dumps(final_points, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_json(cache_meta_path, {"signature": signature, "count": len(final_points)})
    return final_points


def build_combined_article_ner(article_id: str) -> list[dict]:
    missing = get_missing_base_models_for_article(article_id, "ner")
    if missing:
        raise CombinedInputsMissingError(article_id, missing, "NER")

    signature = _build_combined_signature(article_id)
    cache_meta_path = _combined_meta_path(article_id, "ner")
    cache_ner_path = _artifact_path(article_id, CANONICAL_COMBINED_KEY, "ner")
    cached_meta = _read_json(cache_meta_path)
    if cache_ner_path.exists() and cached_meta.get("signature") == signature:
        cached = _read_json_array(cache_ner_path)
        if cached is not None:
            if cached:
                return cached

    tech_rows = _read_json_array(_artifact_path(article_id, "tech", "ner")) or []
    cmt_rows = _read_json_array(_artifact_path(article_id, "cmt", "ner")) or []

    grouped = {}
    ordered_keys = []
    for source_rows in (tech_rows, cmt_rows):
        for row in source_rows:
            text = str(row.get("text") or "")
            key = text
            if key not in grouped:
                grouped[key] = {"text": text, "entities": []}
                ordered_keys.append(key)
            grouped[key]["entities"].extend(list(row.get("entities") or []))

    merged_rows = []
    for key in ordered_keys:
        row = grouped[key]
        seen = set()
        dedup = []
        for ent in row["entities"]:
            sig = (
                str(ent.get("entity_group") or ""),
                str(ent.get("word") or ""),
                int(ent.get("start", -1)),
                int(ent.get("end", -1)),
            )
            if sig in seen:
                continue
            seen.add(sig)
            dedup.append(ent)
        merged_rows.append({
            "text": row["text"],
            "entities": dedup,
        })

    cache_ner_path.parent.mkdir(parents=True, exist_ok=True)
    cache_ner_path.write_text(json.dumps(merged_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_json(cache_meta_path, {"signature": signature, "count": len(merged_rows)})
    return merged_rows


def _build_combined_occurrences(model_payloads: dict[str, dict]) -> list[dict]:
    tech_emb = model_payloads["tech"]["embeddings"]
    cmt_emb = model_payloads["cmt"]["embeddings"]
    if tech_emb.size == 0 and cmt_emb.size == 0:
        return []

    buckets = defaultdict(lambda: {"tech": [], "cmt": []})
    for model_key in BASE_MODEL_KEYS:
        payload = model_payloads[model_key]
        embeddings = payload["embeddings"]
        labels = payload["labels"]
        texts = payload["texts"]
        text_index = payload["text_index"]
        sentence_ids = payload["sentence_ids"]
        offsets = payload["offsets"]
        sentence_texts = payload["sentence_texts"]

        for idx in range(len(embeddings)):
            entity = str(texts[idx] or "").strip()
            if not entity:
                continue
            sid = int(sentence_ids[idx]) if idx < len(sentence_ids) else -1
            start = int(offsets[idx][0]) if idx < len(offsets) else -1
            end = int(offsets[idx][1]) if idx < len(offsets) else -1
            tidx = int(text_index[idx]) if idx < len(text_index) else -1
            norm_entity = _normalize_entity(entity)
            key = (tidx, sid, start, end, norm_entity)
            sentence_text = str(sentence_texts[sid]) if 0 <= sid < len(sentence_texts) else ""
            buckets[key][model_key].append({
                "embedding": embeddings[idx].astype(np.float32),
                "label": str(labels[idx] or "UNKNOWN"),
                "entity": entity,
                "text_index": tidx,
                "sentence_id": sid,
                "start": start if start >= 0 else None,
                "end": end if end >= 0 else None,
                "sentence_text": sentence_text,
            })

    points = []

    for key in sorted(buckets.keys()):
        tech_items = buckets[key]["tech"]
        cmt_items = buckets[key]["cmt"]
        for tech_item, cmt_item in _pair_items_by_similarity(tech_items, cmt_items):
            if not tech_item and not cmt_item:
                continue
            primary = tech_item or cmt_item
            label = _combine_labels(
                tech_item["label"] if tech_item else None,
                cmt_item["label"] if cmt_item else None,
            )
            if tech_item and cmt_item:
                origin = "joint"
            elif tech_item:
                origin = "tech"
            else:
                origin = "cmt"
            points.append({
                "label": label,
                "entity": primary["entity"],
                "text_index": primary["text_index"],
                "sentence_id": primary["sentence_id"],
                "start": primary["start"],
                "end": primary["end"],
                "sentence_text": primary["sentence_text"],
                "origin": origin,
            })

    return points


def _occurrence_key_from_row(text_index: int, sentence_id: int, start, end, entity: str) -> tuple:
    """
    Debe coincidir con la clave de bucket en _build_combined_occurrences:
    allí se usa (tidx, sid, start, end, norm_entity) con start/end enteros del offset
    (pueden ser -1). En los puntos combinados, start/end negativos se guardan como None;
    aquí los volvemos a -1 para empatar con tsne/embeddings.
    """
    if start is None:
        st = -1
    else:
        try:
            st = int(start)
        except (TypeError, ValueError):
            st = -1
    if end is None:
        en = -1
    else:
        try:
            en = int(end)
        except (TypeError, ValueError):
            en = -1
    return (int(text_index), int(sentence_id), st, en, _normalize_entity(entity))


def _occurrence_key_from_tsne_point(pt: dict) -> tuple:
    return _occurrence_key_from_row(
        int(pt.get("text_index", -1)),
        int(pt.get("sentence_id", -1)),
        pt.get("start"),
        pt.get("end"),
        str(pt.get("entity") or ""),
    )


def _norm_xy_cloud(tsne_list: list[dict]) -> dict[tuple, tuple[float, float]]:
    """Min-max por eje sobre la nube del modelo (preserva forma relativa del tsne del modelo)."""
    if not tsne_list:
        return {}
    xs = [float(p["x"]) for p in tsne_list]
    ys = [float(p["y"]) for p in tsne_list]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    rx = max(max_x - min_x, 1e-12)
    ry = max(max_y - min_y, 1e-12)
    out: dict[tuple, tuple[float, float]] = {}
    for p in tsne_list:
        k = _occurrence_key_from_tsne_point(p)
        nx = (float(p["x"]) - min_x) / rx
        ny = (float(p["y"]) - min_y) / ry
        out[k] = (nx, ny)
    return out


def _fuse_norm_xy(origin: str, tech_m: dict, cmt_m: dict, key: tuple) -> tuple[float, float]:
    t = tech_m.get(key)
    c = cmt_m.get(key)
    if origin == "joint":
        if t and c:
            return (t[0] + c[0]) / 2.0, (t[1] + c[1]) / 2.0
        if t:
            return t
        if c:
            return c
        return (0.5, 0.5)
    if origin == "tech":
        return t if t else (0.5, 0.5)
    return c if c else (0.5, 0.5)


def _build_combined_embedding_buckets(model_payloads: dict[str, dict]) -> defaultdict:
    buckets = defaultdict(lambda: {"tech": [], "cmt": []})
    for model_key in BASE_MODEL_KEYS:
        payload = model_payloads[model_key]
        embeddings = payload["embeddings"]
        labels = payload["labels"]
        texts = payload["texts"]
        text_index = payload["text_index"]
        sentence_ids = payload["sentence_ids"]
        offsets = payload["offsets"]
        sentence_texts = payload["sentence_texts"]
        for idx in range(len(embeddings)):
            entity = str(texts[idx] or "").strip()
            if not entity:
                continue
            sid = int(sentence_ids[idx]) if idx < len(sentence_ids) else -1
            start = int(offsets[idx][0]) if idx < len(offsets) else -1
            end = int(offsets[idx][1]) if idx < len(offsets) else -1
            tidx = int(text_index[idx]) if idx < len(text_index) else -1
            norm_entity = _normalize_entity(entity)
            key = (tidx, sid, start, end, norm_entity)
            sentence_text = str(sentence_texts[sid]) if 0 <= sid < len(sentence_texts) else ""
            buckets[key][model_key].append({
                "embedding": embeddings[idx].astype(np.float32),
                "label": str(labels[idx] or "UNKNOWN"),
                "entity": entity,
                "text_index": tidx,
                "sentence_id": sid,
                "start": start if start >= 0 else None,
                "end": end if end >= 0 else None,
                "sentence_text": sentence_text,
            })
    return buckets


def _pair_items_by_similarity(tech_items: list[dict], cmt_items: list[dict]) -> list[tuple[dict | None, dict | None]]:
    """
    Empareja ocurrencias tech/cmt dentro del mismo bucket por similitud coseno.
    Mejora la alineación de la vista combinada cuando hay cantidades distintas
    o el orden interno de detección no coincide entre modelos.
    """
    if not tech_items and not cmt_items:
        return []
    if not tech_items:
        return [(None, item) for item in cmt_items]
    if not cmt_items:
        return [(item, None) for item in tech_items]

    sim_pairs: list[tuple[float, int, int]] = []
    for i, t in enumerate(tech_items):
        te = np.asarray(t.get("embedding"), dtype=np.float32).reshape(-1)
        tnorm = float(np.linalg.norm(te))
        if tnorm < 1e-12:
            continue
        for j, c in enumerate(cmt_items):
            ce = np.asarray(c.get("embedding"), dtype=np.float32).reshape(-1)
            cnorm = float(np.linalg.norm(ce))
            if cnorm < 1e-12:
                continue
            sim = float(np.dot(te, ce) / (tnorm * cnorm))
            sim_pairs.append((sim, i, j))

    sim_pairs.sort(key=lambda x: x[0], reverse=True)
    used_t: set[int] = set()
    used_c: set[int] = set()
    out: list[tuple[dict | None, dict | None]] = []

    for _, i, j in sim_pairs:
        if i in used_t or j in used_c:
            continue
        used_t.add(i)
        used_c.add(j)
        out.append((tech_items[i], cmt_items[j]))

    for i, item in enumerate(tech_items):
        if i not in used_t:
            out.append((item, None))
    for j, item in enumerate(cmt_items):
        if j not in used_c:
            out.append((None, item))
    return out


def _normalize_embeddings_for_combined(emb: np.ndarray) -> np.ndarray:
    """
    Normaliza cada espacio de embeddings (tech/cmt) antes de concatenar:
    - centrado+escalado por dimensión (si hay >=2 filas),
    - normalización L2 por fila.
    Esto reduce desbalance de escala entre modelos en la fusión ambos.
    """
    arr = np.asarray(emb, dtype=np.float32)
    if arr.ndim != 2 or arr.size == 0:
        return arr
    out = arr.copy()
    if out.shape[0] >= 2:
        mean = out.mean(axis=0, keepdims=True)
        std = out.std(axis=0, keepdims=True)
        std = np.where(std < 1e-6, 1.0, std)
        out = (out - mean) / std
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    out = out / norms
    return out.astype(np.float32, copy=False)


def _embedding_feature_dim(emb: np.ndarray) -> int:
    """
    Columnas de la matriz aunque no haya filas (p. ej. shape (0, 768)).
    No usar `emb.size`: con 0 filas el size es 0 y se perdia la dimension,
    generando concat tech+cmt de longitud incorrecta y fallos al agregar en workspace.
    """
    arr = np.asarray(emb)
    if arr.ndim != 2:
        return 0
    d = int(arr.shape[1])
    return d if d > 0 else 0


def _paired_concat_embedding_dims(
    tech_emb: np.ndarray, cmt_emb: np.ndarray
) -> tuple[int, int]:
    """
    dims por modelo para padding al concatenar. Si uno de los NPZ llega corrupto como
    matriz vacia (0, 0), no sabemos cuantas columnas tendria: se asume la misma anchura
    que el modelo hermano (tipico BERT mismo hidden), evitando vectors (768,) en vez de (1536,).
    """
    te = np.asarray(tech_emb)
    cm = np.asarray(cmt_emb)
    dim_tech = _embedding_feature_dim(te)
    dim_cmt = _embedding_feature_dim(cm)
    degenerate_te = (
        dim_tech == 0
        and te.ndim == 2
        and te.shape == (0, 0)
    )
    degenerate_cm = (
        dim_cmt == 0
        and cm.ndim == 2
        and cm.shape == (0, 0)
    )
    if degenerate_te and dim_cmt > 0:
        dim_tech = dim_cmt
    if degenerate_cm and dim_tech > 0:
        dim_cmt = dim_tech
    return dim_tech, dim_cmt


def pad_workspace_concat_embedding(vec: np.ndarray, target_len: int) -> np.ndarray:
    """
    Al agrupar varios articulos en workspace (ambos), el concat puede medir lo mismo o no
    si cambia el modelo o hubo corrupcion en NPZ. Se rellena con ceros al final hasta target_len.
    """
    if target_len <= 0:
        return np.asarray(vec, dtype=np.float64).reshape(-1)
    v = np.asarray(vec, dtype=np.float64).reshape(-1)
    if v.size >= target_len:
        return v[:target_len].copy()
    out = np.zeros(target_len)
    out[: v.size] = v
    return out


def workspace_combined_occurrence_rows(article_id: str) -> list[dict]:
    """
    Ocurrencias alineadas tech/cmt para agregar el workspace en modo ambos: cada fila trae un vector
    concat(embeddings_tech, embeddings_cmt) en alta dimensión (ceros donde falta una mitad del par).
    """
    missing = get_missing_base_models_for_article(article_id, "embeddings")
    if missing:
        return []
    model_payloads = {
        model_key: _load_embeddings_payload(article_id, model_key)
        for model_key in BASE_MODEL_KEYS
    }
    for model_key in BASE_MODEL_KEYS:
        model_payloads[model_key]["embeddings"] = _normalize_embeddings_for_combined(
            model_payloads[model_key]["embeddings"],
        )
    tech_emb = model_payloads["tech"]["embeddings"]
    cmt_emb = model_payloads["cmt"]["embeddings"]
    if tech_emb.size == 0 and cmt_emb.size == 0:
        return []

    dim_tech, dim_cmt = _paired_concat_embedding_dims(tech_emb, cmt_emb)
    if dim_tech <= 0 or dim_cmt <= 0:
        return []
    zero_tech = np.zeros((dim_tech,), dtype=np.float32)
    zero_cmt = np.zeros((dim_cmt,), dtype=np.float32)

    buckets = _build_combined_embedding_buckets(model_payloads)
    rows: list[dict] = []
    for key in sorted(buckets.keys()):
        tech_items = buckets[key]["tech"]
        cmt_items = buckets[key]["cmt"]
        for tech_item, cmt_item in _pair_items_by_similarity(tech_items, cmt_items):
            if not tech_item and not cmt_item:
                continue
            tech_e = tech_item["embedding"] if tech_item else zero_tech
            cmt_e = cmt_item["embedding"] if cmt_item else zero_cmt
            vec = np.concatenate([tech_e, cmt_e], axis=0)
            primary = tech_item or cmt_item
            norm_entity = key[4]
            rows.append({
                "norm_entity": norm_entity,
                "entity_display": primary["entity"],
                "vector": vec.astype(np.float32, copy=False),
                "label": str(primary["label"] or "UNKNOWN"),
                "origin": "joint" if tech_item and cmt_item else ("tech" if tech_item else "cmt"),
                "sentence_id": primary["sentence_id"],
                "text_index": primary["text_index"],
                "sentence_text": str(primary.get("sentence_text") or ""),
                "start": primary.get("start"),
                "end": primary.get("end"),
            })
    return rows


def workspace_combined_points_for_relations(article_id: str) -> list[dict]:
    """
    Ocurrencias alineadas tech/cmt sin vectores: mismo conjunto que workspace_combined_occurrence_rows,
    en forma compatible con el bucle de coocurrencia de workspace_relaciones (antes build_combined_article_tsne).

    Si el emparejamiento concat no produce filas pero sí hay puntos en tsne_tech/tsne_cmt (un modelo sin
    entidades), se reutilizan esos puntos como fuente de coocurrencias para la vista ambos.
    """
    rows = workspace_combined_occurrence_rows(article_id)
    if rows:
        return [
            {
                "entity": str(r["entity_display"] or "").strip(),
                "label": str(r.get("label") or "UNKNOWN"),
                "origin": str(r.get("origin") or "joint"),
                "sentence_id": r.get("sentence_id"),
                "text_index": r.get("text_index"),
            }
            for r in rows
        ]

    out: list[dict] = []
    for mk in BASE_MODEL_KEYS:
        lst = _read_json_array(_artifact_path(article_id, mk, "tsne")) or []
        if not isinstance(lst, list):
            continue
        for p in lst:
            if not isinstance(p, dict):
                continue
            ent = str(p.get("entity") or "").strip()
            if not ent:
                continue
            out.append({
                "entity": ent,
                "label": str(p.get("label") or "UNKNOWN"),
                "origin": str(mk),
                "sentence_id": p.get("sentence_id"),
                "text_index": p.get("text_index"),
            })
    return out


def _planar_coords_from_concat_fallback(model_payloads: dict[str, dict], points: list[dict]) -> list[tuple[float, float]]:
    """Reserva: concatenación + PCA/t-SNE (rompe semántica con ceros; solo si falla la fusión)."""
    dim_tech, dim_cmt = _paired_concat_embedding_dims(
        model_payloads["tech"]["embeddings"],
        model_payloads["cmt"]["embeddings"],
    )
    if dim_tech <= 0 or dim_cmt <= 0:
        return [(0.5, 0.5)] * len(points)
    zero_tech = np.zeros((dim_tech,), dtype=np.float32)
    zero_cmt = np.zeros((dim_cmt,), dtype=np.float32)
    buckets = _build_combined_embedding_buckets(model_payloads)
    vectors = []
    for key in sorted(buckets.keys()):
        tech_items = buckets[key]["tech"]
        cmt_items = buckets[key]["cmt"]
        for tech_item, cmt_item in _pair_items_by_similarity(tech_items, cmt_items):
            if not tech_item and not cmt_item:
                continue
            tech_emb = tech_item["embedding"] if tech_item else zero_tech
            cmt_emb = cmt_item["embedding"] if cmt_item else zero_cmt
            vectors.append(np.concatenate([tech_emb, cmt_emb], axis=0))
    if len(vectors) != len(points):
        return [(0.5, 0.5)] * len(points)
    matrix = np.vstack(vectors).astype(np.float32)
    coords = _reduce_to_2d(matrix)
    return [(float(coords[i][0]), float(coords[i][1])) for i in range(len(points))]


def _planar_coords_for_combined(
    article_id: str,
    points: list[dict],
    model_payloads: dict[str, dict],
) -> list[tuple[float, float]]:
    """
    Usa las coordenadas ya proyectadas en tsne_tech / tsne_cmt (misma ocurrencia que el modelo solo).
    Así la vista combinada respeta la geometría local de cada modelo y evita un t-SNE sobre
    vectores concatenados con ceros cuando solo uno detectó la entidad.

    Si faltan JSON base o una ocurrencia no tiene par en el mapa del modelo que corresponde,
    se usa la concatenación + PCA/t-SNE como respaldo (comportamiento anterior).
    """
    tech_path = _artifact_path(article_id, "tech", "tsne")
    cmt_path = _artifact_path(article_id, "cmt", "tsne")
    tech_list = _read_json_array(tech_path) or []
    cmt_list = _read_json_array(cmt_path) or []
    if not isinstance(tech_list, list):
        tech_list = []
    if not isinstance(cmt_list, list):
        cmt_list = []

    tech_m = _norm_xy_cloud(tech_list)
    cmt_m = _norm_xy_cloud(cmt_list)

    need_fallback = False
    if not tech_list and not cmt_list:
        need_fallback = True
    else:
        for p in points:
            key = _occurrence_key_from_row(
                int(p["text_index"]),
                int(p["sentence_id"]),
                p.get("start"),
                p.get("end"),
                str(p.get("entity") or ""),
            )
            origin = str(p.get("origin") or "joint")
            if origin == "tech" and key not in tech_m:
                need_fallback = True
                break
            if origin == "cmt" and key not in cmt_m:
                need_fallback = True
                break
            if origin == "joint" and (key not in tech_m or key not in cmt_m):
                need_fallback = True
                break

    if need_fallback:
        return _planar_coords_from_concat_fallback(model_payloads, points)

    out: list[tuple[float, float]] = []
    for p in points:
        key = _occurrence_key_from_row(
            int(p["text_index"]),
            int(p["sentence_id"]),
            p.get("start"),
            p.get("end"),
            str(p.get("entity") or ""),
        )
        origin = str(p.get("origin") or "joint")
        xy = _fuse_norm_xy(origin, tech_m, cmt_m, key)
        out.append(xy)
    # Misma escala global [-1, 1] que el fallback para el lienzo
    if len(out) >= 2:
        xs = [v[0] for v in out]
        ys = [v[1] for v in out]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        rx = max(max_x - min_x, 1e-12)
        ry = max(max_y - min_y, 1e-12)
        out = [((x - min_x) / rx * 2.0 - 1.0, (y - min_y) / ry * 2.0 - 1.0) for x, y in out]
    return out


def _combined_center_xy(coords: np.ndarray) -> np.ndarray:
    arr = np.asarray(coords, dtype=np.float64)
    if arr.size == 0:
        return arr
    return arr - arr.mean(axis=0)


def _combined_scale_xy_visual(coords: np.ndarray, target_rms: float = 52.0) -> np.ndarray:
    arr = np.asarray(coords, dtype=np.float64)
    if arr.size == 0:
        return arr
    rms = float(np.sqrt(np.mean(arr ** 2)))
    if rms < 1e-15:
        return arr
    return arr * (target_rms / rms)


def _reduce_to_2d(matrix: np.ndarray) -> np.ndarray:
    n_samples = matrix.shape[0]
    if n_samples == 1:
        return np.array([[0.0, 0.0]], dtype=np.float32)
    if n_samples == 2:
        return np.array([[-1.0, 0.0], [1.0, 0.0]], dtype=np.float32)

    n_components = min(30, matrix.shape[1], n_samples - 1)
    reduced = PCA(n_components=n_components, random_state=42).fit_transform(matrix)
    if n_samples < 8:
        return PCA(n_components=2, random_state=42).fit_transform(reduced).astype(np.float32)

    perplexity = min(25, max(5, n_samples // 3))
    perplexity = min(perplexity, n_samples - 1)
    return TSNE(
        n_components=2,
        random_state=42,
        perplexity=perplexity,
        learning_rate="auto",
        init="pca",
        max_iter=600,
    ).fit_transform(reduced).astype(np.float32)


def _build_combined_signature(article_id: str) -> str:
    digest = hashlib.sha256()
    digest.update(CANONICAL_COMBINED_KEY.encode("utf-8"))
    digest.update(b"|tsne_article_concat_emb_norm_pairing_v4|")
    for model_key in BASE_MODEL_KEYS:
        for artifact_type in ("embeddings", "ner", "tsne"):
            path = _artifact_path(article_id, model_key, artifact_type)
            stamp = path.stat().st_mtime_ns if path.exists() else 0
            digest.update(f"{model_key}|{artifact_type}|{stamp}".encode("utf-8"))
    return digest.hexdigest()


def _load_embeddings_payload(article_id: str, model_key: str) -> dict:
    path = _artifact_path(article_id, model_key, "embeddings")
    data = np.load(path, allow_pickle=True)
    payload = {
        "embeddings": data["embeddings"] if "embeddings" in data.files else np.empty((0, 0), dtype=np.float32),
        "labels": data["labels"] if "labels" in data.files else np.array([]),
        "texts": data["texts"] if "texts" in data.files else np.array([]),
        "text_index": data["text_index"] if "text_index" in data.files else np.array([], dtype=np.int32),
        "sentence_ids": data["sentence_ids"] if "sentence_ids" in data.files else np.array([], dtype=np.int32),
        "offsets": data["offsets"] if "offsets" in data.files else np.empty((0, 2), dtype=np.int32),
        "sentence_texts": data["sentence_texts"] if "sentence_texts" in data.files else np.array([]),
    }
    data.close()
    return payload


def _artifact_path(article_id: str, model_key: str, artifact_type: str) -> Path:
    if artifact_type == "tsne":
        return ARTICLES_DIR / article_id / f"tsne_{model_key}.json"
    if artifact_type == "ner":
        return ARTICLES_DIR / article_id / f"ner_{model_key}.json"
    if artifact_type == "embeddings":
        return ARTICLES_DIR / article_id / f"embeddings_{model_key}.npz"
    raise ValueError(f"artifact_type no soportado: {artifact_type}")


def _combined_meta_path(article_id: str, artifact_type: str) -> Path:
    return ARTICLES_DIR / article_id / f"{artifact_type}_{CANONICAL_COMBINED_KEY}.meta.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_json_array(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else None
    except Exception:
        return None


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_entity(value: str) -> str:
    return " ".join(str(value or "").lower().split()).strip()


def _combine_labels(tech_label: str | None, cmt_label: str | None) -> str:
    t = str(tech_label or "").strip()
    c = str(cmt_label or "").strip()
    if t and c:
        if t == c:
            return t
        return f"{t} / {c}"
    return t or c or "UNKNOWN"
