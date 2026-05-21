"""Snippets storage — YAML files in snippets/ subdirectory."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class SnippetStorage:
    """Manages snippets/{id}.yaml files inside the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / "snippets"

    def _path(self, snippet_id: str) -> Path:
        return self._dir / f"{snippet_id}.yaml"

    def _read(self, path: Path) -> dict | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read snippet %s: %s", path, e)
            return None

    def _write(self, snippet: dict):
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(snippet["id"]).write_text(
            yaml.dump(snippet, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def _matches(self, snippet: dict, q: str) -> bool:
        if q in snippet.get("title", "").lower():
            return True
        if q in snippet.get("description", "").lower():
            return True
        for step in snippet.get("steps", []):
            if q in step.get("description", "").lower():
                return True
            if q in step.get("command", "").lower():
                return True
        return False

    def list_snippets(self, query: str = "") -> list[dict]:
        self._git._pull()
        if not self._dir.exists():
            return []
        q = query.strip().lower()
        items = []
        for f in self._dir.glob("*.yaml"):
            sn = self._read(f)
            if not sn:
                continue
            if q and not self._matches(sn, q):
                continue
            items.append(sn)
        return sorted(items, key=lambda x: x.get("title", "").lower())

    def get_snippet(self, snippet_id: str) -> dict | None:
        self._git._pull()
        p = self._path(snippet_id)
        return self._read(p) if p.exists() else None

    def create_snippet(self, data: dict) -> dict:
        today = date.today().isoformat()
        snippet = {
            "id": _new_id(),
            "title": data.get("title", "").strip(),
            "description": data.get("description", "").strip(),
            "steps": [
                {
                    "description": s.get("description", "").strip(),
                    "command": s.get("command", "").strip(),
                }
                for s in data.get("steps", [])
                if s.get("command", "").strip()
            ],
            "created": today,
            "updated": today,
        }
        self._git._pull()
        self._write(snippet)
        self._git._commit_and_push(f"snippets: add '{snippet['title']}'")
        return snippet

    def update_snippet(self, snippet_id: str, data: dict) -> dict | None:
        snippet = self.get_snippet(snippet_id)
        if not snippet:
            return None
        snippet.update(
            {
                "title": data.get("title", snippet["title"]).strip(),
                "description": data.get("description", snippet.get("description", "")).strip(),
                "steps": [
                    {
                        "description": s.get("description", "").strip(),
                        "command": s.get("command", "").strip(),
                    }
                    for s in data.get("steps", [])
                    if s.get("command", "").strip()
                ],
                "updated": date.today().isoformat(),
            }
        )
        self._write(snippet)
        self._git._commit_and_push(f"snippets: update '{snippet['title']}'")
        return snippet

    def delete_snippet(self, snippet_id: str) -> bool:
        self._git._pull()
        p = self._path(snippet_id)
        if not p.exists():
            return False
        sn = self._read(p)
        p.unlink()
        title = sn.get("title", snippet_id) if sn else snippet_id
        self._git._commit_and_push(f"snippets: delete '{title}'")
        return True

    def bulk_delete_snippets(self, snippet_ids: list[str]) -> int:
        if not snippet_ids:
            return 0
        self._git._pull()
        deleted = 0
        for sid in snippet_ids:
            p = self._path(sid)
            if p.exists():
                p.unlink()
                deleted += 1
        if deleted:
            self._git._commit_and_push(f"snippets: bulk delete {deleted} snippet(s)")
        return deleted
