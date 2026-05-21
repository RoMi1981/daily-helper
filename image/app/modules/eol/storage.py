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

    def _read(self, path: Path) -> dict | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read eol %s: %s", path, e)
            return None

    def _write(self, entry: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(entry["id"]).write_text(
            yaml.dump(entry, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def list_entries(self) -> list[dict]:
        self._git._pull()
        if not self._dir.exists():
            return []
        items = []
        for f in sorted(self._dir.glob("*.yaml")):
            entry = self._read(f)
            if entry:
                items.append(entry)
        return sorted(items, key=lambda x: (x.get("product", ""), x.get("cycle", "")))

    def get_entry(self, entry_id: str) -> dict | None:
        self._git._pull()
        p = self._path(entry_id)
        return self._read(p) if p.exists() else None

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
        self._git._pull()
        self._write(entry)
        self._git._commit_and_push(f"eol: track {product} {cycle}")
        return entry

    def update_notes(self, entry_id: str, notes: str) -> dict | None:
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        entry["notes"] = notes.strip()
        self._write(entry)
        self._git._commit_and_push(f"eol: update notes for {entry.get('label', entry_id)}")
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        self._git._pull()
        p = self._path(entry_id)
        if not p.exists():
            return False
        p.unlink()
        self._git._commit_and_push("eol: remove tracked entry")
        return True

    def is_tracked(self, product: str, cycle: str) -> bool:
        return any(
            e.get("product") == product and e.get("cycle") == cycle
            for e in self.list_entries()
        )
