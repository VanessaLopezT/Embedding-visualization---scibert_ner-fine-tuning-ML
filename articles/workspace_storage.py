"""
Persistencia de workspaces basada en archivos JSON.

Un workspace es una coleccion nombrada de articulos.
Los articulos siguen viviendo en data/articles/<article_id>;
el workspace solo guarda referencias a article_ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from django.conf import settings


@dataclass(frozen=True)
class WorkspaceRecord:
    id: str
    name: str
    description: str
    article_ids: list[str]
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workspaces_root() -> Path:
    root = Path(settings.DATA_DIR) / "workspaces"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _workspace_dir(workspace_id: str) -> Path:
    return _workspaces_root() / workspace_id


def _workspace_meta_path(workspace_id: str) -> Path:
    return _workspace_dir(workspace_id) / "meta.json"


def list_workspaces() -> list[dict]:
    items = []
    for meta_file in sorted(_workspaces_root().glob("*/meta.json")):
        try:
            items.append(read_workspace(meta_file.parent.name))
        except Exception:
            continue
    items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return items


def create_workspace(name: str, description: str = "", article_ids: Iterable[str] | None = None) -> dict:
    workspace_id = uuid4().hex[:10]
    meta = {
        "id": workspace_id,
        "name": str(name or "").strip(),
        "description": str(description or "").strip(),
        "article_ids": _dedupe_article_ids(article_ids or []),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    write_workspace(meta)
    return meta


def read_workspace(workspace_id: str) -> dict:
    path = _workspace_meta_path(workspace_id)
    with open(path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def write_workspace(meta: dict):
    workspace_id = str(meta["id"])
    path = _workspace_meta_path(workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        **meta,
        "article_ids": _dedupe_article_ids(meta.get("article_ids", [])),
        "updated_at": _now_iso(),
    }
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(meta, file_obj, ensure_ascii=False, indent=2)


def delete_workspace(workspace_id: str) -> bool:
    path = _workspace_meta_path(workspace_id)
    if not path.exists():
        return False
    path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass
    return True


def add_articles(workspace_id: str, article_ids: Iterable[str]) -> dict:
    meta = read_workspace(workspace_id)
    merged = list(meta.get("article_ids", [])) + list(article_ids or [])
    meta["article_ids"] = _dedupe_article_ids(merged)
    write_workspace(meta)
    return read_workspace(workspace_id)


def remove_articles(workspace_id: str, article_ids: Iterable[str]) -> dict:
    meta = read_workspace(workspace_id)
    to_remove = {str(article_id).strip() for article_id in article_ids or [] if str(article_id).strip()}
    meta["article_ids"] = [
        article_id
        for article_id in meta.get("article_ids", [])
        if article_id not in to_remove
    ]
    write_workspace(meta)
    return read_workspace(workspace_id)


def update_workspace(workspace_id: str, *, name: str | None = None, description: str | None = None) -> dict:
    meta = read_workspace(workspace_id)
    if name is not None:
        meta["name"] = str(name).strip()
    if description is not None:
        meta["description"] = str(description).strip()
    write_workspace(meta)
    return read_workspace(workspace_id)


def _dedupe_article_ids(article_ids: Iterable[str]) -> list[str]:
    seen = set()
    ordered = []
    for raw in article_ids:
        article_id = str(raw).strip()
        if not article_id or article_id in seen:
            continue
        seen.add(article_id)
        ordered.append(article_id)
    return ordered
