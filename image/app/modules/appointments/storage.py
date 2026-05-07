"""Appointment storage — YAML files in appointments/ subdirectory of the data repo."""

import logging
import uuid
from datetime import date, timedelta
from pathlib import Path

import yaml
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

VALID_TYPES = {"training", "conference", "team_event", "business_trip", "other"}
VALID_RECURRING = {"none", "weekly", "monthly", "yearly"}


def _next_occurrence(entry: dict) -> dict | None:
    """Return a new entry dict shifted by one recurring interval, or None if not recurring."""
    recurring = entry.get("recurring", "none")
    if recurring not in VALID_RECURRING or recurring == "none":
        return None
    try:
        start = date.fromisoformat(entry["start_date"])
        end = date.fromisoformat(entry["end_date"])
    except (ValueError, KeyError):
        return None
    duration = end - start
    if recurring == "weekly":
        start += timedelta(weeks=1)
    elif recurring == "monthly":
        start += relativedelta(months=1)
    elif recurring == "yearly":
        start += relativedelta(years=1)
    end = start + duration
    return {
        **entry,
        "id": _new_id(),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "created": date.today().isoformat(),
    }


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class AppointmentStorage:
    """Manages whole-day appointment entries in the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._appt_dir = Path(git_storage.local_path) / "appointments"
        self._entries_dir = self._appt_dir / "entries"

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
        for name in self._git.list_committed("appointments/entries"):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"appointments/entries/{name}")
            if raw is None:
                continue
            try:
                e = yaml.safe_load(raw)
            except Exception as exc:
                logger.warning("Failed to parse appointments/entries/%s: %s", name, exc)
                continue
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
        raw = self._git.read_committed(f"appointments/entries/{entry_id}.yaml")
        if raw is None:
            return None
        try:
            e = yaml.safe_load(raw)
            return e if isinstance(e, dict) else None
        except Exception as exc:
            logger.warning("Failed to parse appointment %s: %s", entry_id, exc)
            return None

    def create_entry(self, data: dict) -> dict:
        appt_type = data.get("type", "other")
        if appt_type not in VALID_TYPES:
            appt_type = "other"
        recurring = data.get("recurring", "none")
        if recurring not in VALID_RECURRING:
            recurring = "none"
        entry = {
            "id": _new_id(),
            "title": data.get("title", "").strip(),
            "start_date": data.get("start_date", ""),
            "end_date": data.get("end_date", ""),
            "type": appt_type,
            "note": data.get("note", ""),
            "recurring": recurring,
            "created": date.today().isoformat(),
        }
        self._git._pull()
        self._ensure_dirs()
        self._write_yaml(self._entries_dir / f"{entry['id']}.yaml", entry)
        self._git._commit_and_push(
            f"appointments: add {entry['title'] or entry['type']} {entry['start_date']}"
        )
        return entry

    def update_entry(self, entry_id: str, data: dict) -> dict | None:
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        appt_type = data.get("type", entry.get("type", "other"))
        if appt_type not in VALID_TYPES:
            appt_type = entry.get("type", "other")
        recurring = data.get("recurring", entry.get("recurring", "none"))
        if recurring not in VALID_RECURRING:
            recurring = entry.get("recurring", "none")
        entry.update(
            {
                "title": data.get("title", entry.get("title", "")).strip(),
                "start_date": data.get("start_date", entry["start_date"]),
                "end_date": data.get("end_date", entry["end_date"]),
                "type": appt_type,
                "note": data.get("note", entry.get("note", "")),
                "recurring": recurring,
            }
        )
        self._git._pull()
        self._ensure_dirs()
        self._write_yaml(self._entries_dir / f"{entry_id}.yaml", entry)
        self._git._commit_and_push(
            f"appointments: update {entry['title'] or entry['type']} {entry['start_date']}"
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
        label = entry.get("title") or entry_id
        next_entry = _next_occurrence(entry)
        path.unlink()
        if next_entry:
            self._ensure_dirs()
            self._write_yaml(self._entries_dir / f"{next_entry['id']}.yaml", next_entry)
            self._git._commit_and_push(
                f"appointments: delete {label}, next {next_entry['start_date']}"
            )
        else:
            self._git._commit_and_push(f"appointments: delete {label}")
        return True
