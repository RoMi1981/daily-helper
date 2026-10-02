"""EOL tracker storage — one YAML file per tracked product/cycle."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class EolStorage:
    """Manages eol/{id}.yaml files inside the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / "eol"

    def _path(self, entry_id: str) -> Path:
        return self._dir / f"{entry_id}.yaml"

    def _parse(self, raw, label: str) -> dict | None:
        try:
            data = yaml.safe_load(raw)
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read eol %s: %s", label, e)
            return None

    def _write(self, entry: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(entry["id"]).write_text(yaml.dump(entry, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def list_entries(self) -> list[dict]:
        items = []
        for name in self._git.list_committed("eol"):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"eol/{name}")
            if raw is None:
                continue
            entry = self._parse(raw, name)
            if entry:
                items.append(entry)
        return sorted(items, key=lambda x: (x.get("product", ""), x.get("cycle", "")))

    def get_entry(self, entry_id: str) -> dict | None:
        raw = self._git.read_committed(f"eol/{entry_id}.yaml")
        return self._parse(raw, entry_id) if raw is not None else None

    def create_entry(self, product: str, cycle: str, label: str, notes: str = "") -> dict:
        today = date.today().isoformat()
        entry = {
            "id": _new_id(),
            "product": product,
            "cycle": cycle,
            "label": label,
            "notes": notes,
            "created": today,
        }
        with self._git.write_lock():
            self._git._pull()
            self._write(entry)
            self._git._commit_and_push(f"eol: track {product} {cycle}")
        return entry

    def update_notes(self, entry_id: str, notes: str) -> dict | None:
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        entry["notes"] = notes.strip()
        with self._git.write_lock():
            self._git._pull()
            self._write(entry)
            self._git._commit_and_push(f"eol: update notes for {entry.get('label', entry_id)}")
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        if self.get_entry(entry_id) is None:
            return False
        with self._git.write_lock():
            self._git._pull()
            p = self._path(entry_id)
            if not p.exists():
                return False
            p.unlink()
            self._git._commit_and_push("eol: remove tracked entry")
        return True

    def is_tracked(self, product: str, cycle: str) -> bool:
        return any(e.get("product") == product and e.get("cycle") == cycle for e in self.list_entries())
