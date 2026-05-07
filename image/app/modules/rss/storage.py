"""RSS feed storage — one YAML file per feed in rss/ subdirectory."""

import logging
import uuid
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class RssStorage:
    """Manages rss/{id}.yaml files in the git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / "rss"

    def _path(self, feed_id: str) -> Path:
        return self._dir / f"{feed_id}.yaml"

    def _write(self, feed: dict):
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(feed["id"]).write_text(
            yaml.dump(feed, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def list_feeds(self) -> list[dict]:
        feeds = []
        for name in self._git.list_committed("rss"):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"rss/{name}")
            if raw and isinstance(raw, (str, bytes)):
                try:
                    feed = yaml.safe_load(raw)
                    if isinstance(feed, dict):
                        feeds.append(feed)
                except Exception:
                    pass
        return sorted(feeds, key=lambda f: f.get("name", "").lower())

    def upsert_feed(self, feed: dict) -> dict:
        is_new = not feed.get("id")
        if is_new:
            feed["id"] = _new_id()
        self._git._pull()
        self._write(feed)
        action = "add" if is_new else "update"
        self._git._commit_and_push(f"rss: {action} feed '{feed['name']}'")
        return feed

    def set_default(self, feed_id: str) -> bool:
        """Mark feed_id as default, clear default flag from all others."""
        self._git._pull()
        if not self._dir.exists():
            return False
        feeds = []
        for p in self._dir.glob("*.yaml"):
            try:
                feed = yaml.safe_load(p.read_text(encoding="utf-8"))
                if isinstance(feed, dict):
                    feeds.append((p, feed))
            except Exception:
                pass
        target = next((f for _, f in feeds if f.get("id") == feed_id), None)
        if not target:
            return False
        for path, feed in feeds:
            desired = feed["id"] == feed_id
            if feed.get("default", False) != desired:
                feed["default"] = desired
                path.write_text(
                    yaml.dump(feed, allow_unicode=True, sort_keys=False), encoding="utf-8"
                )
        self._git._commit_and_push(f"rss: set default feed '{target.get('name', feed_id)}'")
        return True

    def delete_feed(self, feed_id: str) -> bool:
        path = self._path(feed_id)
        raw = self._git.read_committed(f"rss/{feed_id}.yaml")
        if not raw:
            return False
        name = feed_id
        try:
            data = yaml.safe_load(raw)
            if isinstance(data, dict):
                name = data.get("name", feed_id)
        except Exception:
            pass
        self._git._pull()
        if path.exists():
            path.unlink()
        self._git._commit_and_push(f"rss: delete feed '{name}'")
        return True
