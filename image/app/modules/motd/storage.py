"""MOTD storage — one YAML file per message in motd/ subdirectory."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class MotdStorage:
    """Manages motd/{id}.yaml files inside the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / "motd"

    def _path(self, motd_id: str) -> Path:
        return self._dir / f"{motd_id}.yaml"

    def _parse(self, raw, label: str) -> dict | None:
        try:
            data = yaml.safe_load(raw)
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read motd %s: %s", label, e)
            return None

    def _write(self, entry: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(entry["id"]).write_text(yaml.dump(entry, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def list_entries(self) -> list[dict]:
        items = []
        for name in self._git.list_committed("motd"):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"motd/{name}")
            if raw is None:
                continue
            entry = self._parse(raw, name)
            if entry:
                items.append(entry)
        return sorted(items, key=lambda x: x.get("created", ""), reverse=True)

    def list_active(self) -> list[dict]:
        return [e for e in self.list_entries() if e.get("active", True)]

    def get_entry(self, motd_id: str) -> dict | None:
        raw = self._git.read_committed(f"motd/{motd_id}.yaml")
        return self._parse(raw, motd_id) if raw is not None else None

    def _existing_texts(self) -> set[str]:
        return {e["text"].strip().lower() for e in self.list_entries() if e.get("text")}

    def create_entry(self, data: dict) -> tuple[dict, bool]:
        """Create entry. Returns (entry, is_duplicate). Skips if text already exists."""
        text = data.get("text", "").strip()
        existing = self._existing_texts()
        if text.lower() in existing:
            dupe = next((e for e in self.list_entries() if e["text"].strip().lower() == text.lower()), {})
            return dupe, True
        today = date.today().isoformat()
        entry = {"id": _new_id(), "text": text, "active": True, "created": today}
        with self._git.write_lock():
            self._git._pull()
            self._write(entry)
            self._git._commit_and_push("motd: add entry")
        return entry, False

    def update_entry(self, motd_id: str, data: dict) -> dict | None:
        entry = self.get_entry(motd_id)
        if not entry:
            return None
        entry["text"] = data.get("text", entry["text"]).strip()
        entry["active"] = data.get("active", entry.get("active", True))
        with self._git.write_lock():
            self._git._pull()
            self._write(entry)
            self._git._commit_and_push("motd: update entry")
        return entry

    def delete_entry(self, motd_id: str) -> bool:
        with self._git.write_lock():
            self._git._pull()
            p = self._path(motd_id)
            if not p.exists():
                return False
            p.unlink()
            self._git._commit_and_push("motd: delete entry")
        return True

    def bulk_import(self, lines: list[str]) -> tuple[int, int]:
        """Create one entry per non-empty line, skip duplicates. Returns (created, skipped)."""
        texts = [t.strip() for t in lines if t.strip()]
        if not texts:
            return 0, 0
        with self._git.write_lock():
            self._git._pull()
            existing = self._existing_texts()
            today = date.today().isoformat()
            created = 0
            skipped = 0
            seen = set()
            for text in texts:
                key = text.lower()
                if key in existing or key in seen:
                    skipped += 1
                    continue
                seen.add(key)
                entry = {"id": _new_id(), "text": text, "active": True, "created": today}
                self._write(entry)
                created += 1
            if created:
                self._git._commit_and_push(f"motd: bulk import {created} entries")
        return created, skipped

    def get_daily(self, offset: int = 0) -> dict | None:
        """Return today's message deterministically, shifted by offset."""
        entries = self.list_active()
        if not entries:
            return None
        today_int = int(date.today().strftime("%Y%m%d"))
        idx = (today_int + offset) % len(entries)
        return entries[idx]
