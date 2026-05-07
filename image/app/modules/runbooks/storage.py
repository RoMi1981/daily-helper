"""Runbooks storage — YAML files in runbooks/ subdirectory."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class RunbookStorage:
    """Manages runbooks/{id}.yaml files inside the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / "runbooks"

    def _path(self, runbook_id: str) -> Path:
        return self._dir / f"{runbook_id}.yaml"

    def _read(self, path: Path) -> dict | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read runbook %s: %s", path, e)
            return None

    def _write(self, runbook: dict):
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(runbook["id"]).write_text(
            yaml.dump(runbook, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def list_runbooks(self, query: str = "") -> list[dict]:
        self._git._pull()
        if not self._dir.exists():
            return []
        items = []
        q = query.strip().lower()
        for f in self._dir.glob("*.yaml"):
            rb = self._read(f)
            if not rb:
                continue
            if (
                q
                and q not in rb.get("title", "").lower()
                and q not in rb.get("description", "").lower()
            ):
                continue
            items.append(rb)
        return sorted(items, key=lambda x: x.get("title", "").lower())

    def get_runbook(self, runbook_id: str) -> dict | None:
        self._git._pull()
        p = self._path(runbook_id)
        return self._read(p) if p.exists() else None

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
        self._write(runbook)
        self._git._commit_and_push(f"runbooks: update '{runbook['title']}'")
        return runbook

    def delete_runbook(self, runbook_id: str) -> bool:
        self._git._pull()
        p = self._path(runbook_id)
        if not p.exists():
            return False
        rb = self._read(p)
        p.unlink()
        title = rb.get("title", runbook_id) if rb else runbook_id
        self._git._commit_and_push(f"runbooks: delete '{title}'")
        return True

    def bulk_delete_runbooks(self, runbook_ids: list[str]) -> int:
        if not runbook_ids:
            return 0
        self._git._pull()
        deleted = 0
        for rid in runbook_ids:
            p = self._path(rid)
            if p.exists():
                p.unlink()
                deleted += 1
        if deleted:
            self._git._commit_and_push(f"runbooks: bulk delete {deleted} runbook(s)")
        return deleted
