"""Shared read/write plumbing for module storage that keeps one YAML file per
item in a top-level git directory (runbooks/, snippets/, mail_templates/,
ticket_templates/, ...).

Reads go through GitStorage.list_committed()/read_committed() (git objects,
never the working tree) so they agree with each other on the same git ref and
never see phantom "missing" entries during a pending-push window. Mutations
still pull + touch the working tree, since a commit needs one. Subclasses own
their domain fields, create/update serialization, search matching, and commit
messages — this only provides the common I/O.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class YamlDirStorage:
    subdir: str = ""  # subclass must set, e.g. "runbooks"

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / self.subdir

    def _path(self, item_id: str) -> Path:
        return self._dir / f"{item_id}.yaml"

    def _parse(self, raw, label: str) -> dict | None:
        try:
            data = yaml.safe_load(raw)
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read %s %s: %s", self.subdir, label, e)
            return None

    def _write(self, item: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(item["id"]).write_text(yaml.dump(item, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def _list_raw(self) -> list[dict]:
        items = []
        for name in self._git.list_committed(self.subdir):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"{self.subdir}/{name}")
            if raw is None:
                continue
            entry = self._parse(raw, name)
            if entry:
                items.append(entry)
        return items

    def get_entry(self, item_id: str) -> dict | None:
        raw = self._git.read_committed(f"{self.subdir}/{item_id}.yaml")
        return self._parse(raw, item_id) if raw is not None else None

    def _delete(self, item_id: str) -> dict | None:
        """Pull, then delete item_id's file if present.

        Returns its parsed content (so callers can build a commit message
        from e.g. a title/name field) or None if it didn't exist.
        """
        self._git._pull()
        p = self._path(item_id)
        if not p.exists():
            return None
        try:
            entry = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            entry = None
        p.unlink()
        return entry if isinstance(entry, dict) else {}

    def _bulk_delete(self, item_ids: list[str]) -> int:
        if not item_ids:
            return 0
        self._git._pull()
        deleted = 0
        for iid in item_ids:
            p = self._path(iid)
            if p.exists():
                p.unlink()
                deleted += 1
        return deleted
