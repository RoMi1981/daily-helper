"""Cross-module favorites — stored in favorites.yaml in the primary writable repo."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FILENAME = "favorites.yaml"


class FavoritesUnreadable(Exception):
    """favorites.yaml exists but is not a readable list (e.g. a merge conflict)."""


def _get_primary_git():
    """Return the writable GitStorage favorites should be stored in, or None.

    Reuses the same primary-repo resolution every other module uses
    (module_repos.get_primary_store): explicit primary → first writable →
    first available. The previous version of this function just returned
    the first store in dict order regardless of write access, contradicting
    its own docstring.
    """
    from core.module_repos import get_primary_store
    from core.state import get_storage

    return get_primary_store("favorites", get_storage())


def _load(git) -> list[dict]:
    """Return the stored favourites; raise FavoritesUnreadable if the file is broken.

    An unreadable file must never read as "no favourites": toggle_favorite()
    writes back what it loaded, and would replace every stored favourite with
    the single new one.
    """
    raw = git.read_committed(_FILENAME)
    if not raw:
        return []
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except Exception as exc:
        raise FavoritesUnreadable(f"{_FILENAME} is not valid YAML: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, list):
        raise FavoritesUnreadable(f"{_FILENAME} does not contain a list")
    return data


def _load_for_display(git) -> list[dict]:
    """Like _load(), but an unreadable file shows as empty — with a warning."""
    try:
        return _load(git)
    except FavoritesUnreadable as exc:
        logger.warning("Favorites hidden: %s", exc)
        return []


def _save(git, entries: list[dict]) -> None:
    """Caller must hold git.write_lock() — see toggle_favorite()."""
    path = Path(git.local_path) / _FILENAME
    path.write_text(yaml.dump(entries, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    git._commit_and_push("favorites: update")


def list_favorites() -> list[dict]:
    git = _get_primary_git()
    if not git:
        return []
    return _load_for_display(git)


def toggle_favorite(module: str, entry_id: str, title: str, url: str) -> bool:
    """Add or remove a favorite. Returns True if now a favorite, False if removed."""
    git = _get_primary_git()
    if not git:
        return False
    # Read-modify-write on a single list file: without the lock two toggles
    # read the same list and the second _save drops the first one's change.
    with git.write_lock():
        git._pull()
        entries = _load(git)
        for i, e in enumerate(entries):
            if e.get("module") == module and e.get("id") == entry_id:
                entries.pop(i)
                _save(git, entries)
                return False
        from datetime import date

        entries.append(
            {
                "module": module,
                "id": entry_id,
                "title": title,
                "url": url,
                "pinned_at": date.today().isoformat(),
            }
        )
        _save(git, entries)
    return True


def is_favorite(module: str, entry_id: str) -> bool:
    git = _get_primary_git()
    if not git:
        return False
    entries = _load_for_display(git)
    return any(e.get("module") == module and e.get("id") == entry_id for e in entries)
