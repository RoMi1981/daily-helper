"""Snippets storage — YAML files in snippets/ subdirectory."""

import uuid
from datetime import date

from core.yaml_dir_storage import YamlDirStorage


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class SnippetStorage(YamlDirStorage):
    """Manages snippets/{id}.yaml files inside the data git repo."""

    subdir = "snippets"

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
        q = query.strip().lower()
        items = self._list_raw()
        if q:
            items = [sn for sn in items if self._matches(sn, q)]
        return sorted(items, key=lambda x: x.get("title", "").lower())

    def get_snippet(self, snippet_id: str) -> dict | None:
        return self.get_entry(snippet_id)

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
        with self._git.write_lock():
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
        with self._git.write_lock():
            self._git._pull()
            self._write(snippet)
            self._git._commit_and_push(f"snippets: update '{snippet['title']}'")
        return snippet

    def delete_snippet(self, snippet_id: str) -> bool:
        with self._git.write_lock():
            sn = self._delete(snippet_id)
            if sn is None:
                return False
            title = sn.get("title", snippet_id)
            self._git._commit_and_push(f"snippets: delete '{title}'")
        return True

    def bulk_delete_snippets(self, snippet_ids: list[str]) -> int:
        with self._git.write_lock():
            deleted = self._bulk_delete(snippet_ids)
            if deleted:
                self._git._commit_and_push(f"snippets: bulk delete {deleted} snippet(s)")
        return deleted
