"""Helpers to resolve GitStorage instances per module based on settings."""

from __future__ import annotations
from core import settings_store


def _assigned_ids(module: str) -> list[str]:
    return settings_store.get_module_repos(module).get("repos", [])


def _primary_id(module: str) -> str:
    return settings_store.get_module_repos(module).get("primary", "")


def get_module_stores(module: str, storage) -> list:
    """Return GitStorage list for a module (all assigned repos, or all if none configured)."""
    if not storage:
        return []
    assigned = _assigned_ids(module)
    if not assigned:
        return list(storage._stores.values())
    return [storage._stores[rid] for rid in assigned if rid in storage._stores]


def get_primary_store(module: str, storage):
    """Return the primary GitStorage for writing (primary setting → first writable → first assigned)."""
    if not storage:
        return None
    assigned = _assigned_ids(module)
    candidates = assigned if assigned else list(storage._stores.keys())
    primary = _primary_id(module)

    # 1. Explicit primary if available
    if primary and primary in storage._stores and (not assigned or primary in assigned):
        return storage._stores[primary]

    # 2. First writable among candidates
    writable_ids = {r["id"] for r in storage._cfg.get("repos", [])
                    if r.get("permissions", {}).get("write")}
    for rid in candidates:
        if rid in writable_ids and rid in storage._stores:
            return storage._stores[rid]

    # 3. First available
    for rid in candidates:
        if rid in storage._stores:
            return storage._stores[rid]

    return None


def get_module_repo_list(module: str, storage) -> list[dict]:
    """Return [{id, name}] for repos assigned to a module."""
    if not storage:
        return []
    assigned = _assigned_ids(module)
    repo_map = {r["id"]: r.get("name", r["id"]) for r in storage._cfg.get("repos", [])}
    candidates = assigned if assigned else list(storage._stores.keys())
    return [{"id": rid, "name": repo_map.get(rid, rid)}
            for rid in candidates if rid in storage._stores]
