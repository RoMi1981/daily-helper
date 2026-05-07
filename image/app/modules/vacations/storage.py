"""Vacation storage — YAML files in vacations/ subdirectory of the data repo."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class VacationStorage:
    """Manages vacation entries and account in the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._vac_dir = Path(git_storage.local_path) / "vacations"
        self._entries_dir = self._vac_dir / "entries"

    def _ensure_dirs(self):
        self._entries_dir.mkdir(parents=True, exist_ok=True)

    def _read_yaml(self, path: Path) -> dict | None:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read %s: %s", path, e)
            return None

    def _write_yaml(self, path: Path, data: dict):
        path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def list_entries(self, year: int | None = None) -> list[dict]:
        entries = []
        for name in self._git.list_committed("vacations/entries"):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"vacations/entries/{name}")
            if raw is None:
                continue
            e = yaml.safe_load(raw.decode("utf-8"))
            if not isinstance(e, dict):
                continue
            if year:
                try:
                    if int(e.get("start_date", "")[:4]) != year:
                        continue
                except (ValueError, TypeError):
                    pass
            entries.append(e)
        return sorted(entries, key=lambda e: e.get("start_date", ""))

    def get_entry(self, entry_id: str) -> dict | None:
        raw = self._git.read_committed(f"vacations/entries/{entry_id}.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None

    def create_entry(self, data: dict) -> dict:
        entry = {
            "id": _new_id(),
            "start_date": data.get("start_date", ""),
            "end_date": data.get("end_date", ""),
            "status": data.get("status", "planned"),
            "note": data.get("note", ""),
            "created": date.today().isoformat(),
        }
        self._git._pull()
        self._ensure_dirs()
        self._write_yaml(self._entries_dir / f"{entry['id']}.yaml", entry)
        self._git._commit_and_push(f"vacations: add {entry['start_date']} – {entry['end_date']}")
        return entry

    def update_entry(self, entry_id: str, data: dict) -> dict | None:
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        entry.update(
            {
                "start_date": data.get("start_date", entry["start_date"]),
                "end_date": data.get("end_date", entry["end_date"]),
                "note": data.get("note", entry.get("note", "")),
            }
        )
        self._git._pull()
        self._ensure_dirs()
        self._write_yaml(self._entries_dir / f"{entry_id}.yaml", entry)
        self._git._commit_and_push(f"vacations: update {entry['start_date']} – {entry['end_date']}")
        return entry

    def update_status(self, entry_id: str, status: str) -> dict | None:
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        entry["status"] = status
        self._git._pull()
        self._ensure_dirs()
        self._write_yaml(self._entries_dir / f"{entry_id}.yaml", entry)
        self._git._commit_and_push(
            f"vacations: {status} {entry['start_date']} – {entry['end_date']}"
        )
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        entry = self.get_entry(entry_id)
        if entry is None:
            return False
        self._git._pull()
        path = self._entries_dir / f"{entry_id}.yaml"
        if not path.exists():
            return False
        label = f"{entry['start_date']} – {entry['end_date']}" if entry else entry_id
        path.unlink()
        self._git._commit_and_push(f"vacations: delete {label}")
        return True

    def get_account(
        self, year: int, total_days: float, state: str, entries: list[dict] | None = None
    ) -> dict:
        """Calculate vacation account for a given year. Pass entries to use pre-merged multi-repo data."""
        from modules.vacations.holidays_helper import count_work_days

        if entries is None:
            entries = self.list_entries(year)
        for e in entries:
            try:
                e["work_days"] = count_work_days(e["start_date"], e["end_date"], state)
            except Exception:
                e["work_days"] = None
        approved = [e for e in entries if e.get("status") in ("approved", "documented")]
        planned = [e for e in entries if e.get("status") in ("planned", "requested")]
        used = sum(e["work_days"] or 0 for e in approved)
        planned_days = sum(e["work_days"] or 0 for e in planned)
        remaining = total_days - used
        return {
            "year": year,
            "total_days": total_days,
            "used_days": used,
            "planned_days": planned_days,
            "remaining_days": remaining,
            "remaining_after_planned": remaining - planned_days,
            "entries": entries,
        }
