"""Cross-module favorites — stored in favorites.yaml in the primary writable repo."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FILENAME = "favorites.yaml"


def _get_primary_git():
    """Return the first writable GitStorage, or None."""
    from core.state import get_storage

    storage = get_storage()
    if not storage:
        return None
    for store in storage._stores.values():
        return store  # first available store; prefer writable
    return None


def _load(git) -> list[dict]:
    raw = git.read_committed(_FILENAME)
    if not raw:
        return []
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(git, entries: list[dict]) -> None:
    path = Path(git.local_path) / _FILENAME
    path.write_text(yaml.dump(entries, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    git._commit_and_push("favorites: update")


def list_favorites() -> list[dict]:
    git = _get_primary_git()
    if not git:
        return []
    return _load(git)


def toggle_favorite(module: str, entry_id: str, title: str, url: str) -> bool:
    """Add or remove a favorite. Returns True if now a favorite, False if removed."""
    git = _get_primary_git()
    if not git:
        return False
    git._pull()
    entries = _load(git)
    for i, e in enumerate(entries):
        if e.get("module") == module and e.get("id") == entry_id:
            entries.pop(i)
            _save(git, entries)
            return False
    from datetime import date

    entries.append({
        "module": module,
        "id": entry_id,
        "title": title,
        "url": url,
        "pinned_at": date.today().isoformat(),
    })
    _save(git, entries)
    return True


def is_favorite(module: str, entry_id: str) -> bool:
    git = _get_primary_git()
    if not git:
        return False
    entries = _load(git)
    return any(e.get("module") == module and e.get("id") == entry_id for e in entries)
