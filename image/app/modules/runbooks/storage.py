"""Runbooks storage — YAML files in runbooks/ subdirectory."""

import uuid
from datetime import date

from core.yaml_dir_storage import YamlDirStorage


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class RunbookStorage(YamlDirStorage):
    """Manages runbooks/{id}.yaml files inside the data git repo."""

    subdir = "runbooks"

    def _matches(self, rb: dict, q: str) -> bool:
        if q in rb.get("title", "").lower():
            return True
        if q in rb.get("description", "").lower():
            return True
        for step in rb.get("steps", []):
            if q in step.get("title", "").lower():
                return True
            if q in step.get("body", "").lower():
                return True
        return False

    def list_runbooks(self, query: str = "") -> list[dict]:
        q = query.strip().lower()
        items = self._list_raw()
        if q:
            items = [rb for rb in items if self._matches(rb, q)]
        return sorted(items, key=lambda x: x.get("title", "").lower())

    def get_runbook(self, runbook_id: str) -> dict | None:
        return self.get_entry(runbook_id)

    def create_runbook(self, data: dict) -> dict:
        today = date.today().isoformat()
        runbook = {
            "id": _new_id(),
            "title": data.get("title", "").strip(),
            "description": data.get("description", "").strip(),
            "steps": [
                {"title": s.get("title", "").strip(), "body": s.get("body", "").strip()}
                for s in data.get("steps", [])
                if s.get("title", "").strip()
            ],
            "created": today,
            "updated": today,
        }
        with self._git.write_lock():
            self._git._pull()
            self._write(runbook)
            self._git._commit_and_push(f"runbooks: add '{runbook['title']}'")
        return runbook

    def update_runbook(self, runbook_id: str, data: dict) -> dict | None:
        runbook = self.get_runbook(runbook_id)
        if not runbook:
            return None
        runbook.update(
            {
                "title": data.get("title", runbook["title"]).strip(),
                "description": data.get("description", runbook.get("description", "")).strip(),
                "steps": [
                    {"title": s.get("title", "").strip(), "body": s.get("body", "").strip()}
                    for s in data.get("steps", [])
                    if s.get("title", "").strip()
                ],
                "updated": date.today().isoformat(),
            }
        )
        with self._git.write_lock():
            self._git._pull()
            self._write(runbook)
            self._git._commit_and_push(f"runbooks: update '{runbook['title']}'")
        return runbook

    def delete_runbook(self, runbook_id: str) -> bool:
        with self._git.write_lock():
            rb = self._delete(runbook_id)
            if rb is None:
                return False
            title = rb.get("title", runbook_id)
            self._git._commit_and_push(f"runbooks: delete '{title}'")
        return True

    def bulk_delete_runbooks(self, runbook_ids: list[str]) -> int:
        with self._git.write_lock():
            deleted = self._bulk_delete(runbook_ids)
            if deleted:
                self._git._commit_and_push(f"runbooks: bulk delete {deleted} runbook(s)")
        return deleted
