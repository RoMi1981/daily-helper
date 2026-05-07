"""Tests for VacationStorage and holidays_helper."""

import os
import sys
from unittest.mock import patch

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = (
    _candidate
    if os.path.isdir(_candidate)
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def read_committed(self, path: str):
        import os

        full = os.path.join(self.local_path, path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def list_committed(self, directory: str) -> list:
        import os

        full = os.path.join(self.local_path, directory)
        if not os.path.isdir(full):
            return []
        return os.listdir(full)


@pytest.fixture()
def storage(tmp_path):
    from modules.vacations.storage import VacationStorage

    return VacationStorage(FakeGit(tmp_path))


# ── VacationStorage CRUD ───────────────────────────────────────────────────


def test_list_empty(storage):
    assert storage.list_entries() == []


def test_create_and_list(storage):
    e = storage.create_entry(
        {
            "start_date": "2026-07-01",
            "end_date": "2026-07-10",
            "status": "planned",
            "note": "Summer",
        }
    )
    assert e["start_date"] == "2026-07-01"
    assert e["end_date"] == "2026-07-10"
    assert e["status"] == "planned"
    assert "id" in e
    entries = storage.list_entries()
    assert len(entries) == 1


def test_get_entry(storage):
    e = storage.create_entry({"start_date": "2026-08-01", "end_date": "2026-08-05"})
    fetched = storage.get_entry(e["id"])
    assert fetched is not None
    assert fetched["start_date"] == "2026-08-01"


def test_get_entry_missing(storage):
    assert storage.get_entry("doesnotexist") is None


def test_update_entry(storage):
    e = storage.create_entry({"start_date": "2026-06-01", "end_date": "2026-06-05", "note": "old"})
    updated = storage.update_entry(
        e["id"], {"start_date": "2026-06-02", "end_date": "2026-06-06", "note": "new"}
    )
    assert updated["start_date"] == "2026-06-02"
    assert updated["note"] == "new"


def test_update_entry_missing(storage):
    assert (
        storage.update_entry("ghost", {"start_date": "2026-01-01", "end_date": "2026-01-02"})
        is None
    )


def test_update_status(storage):
    e = storage.create_entry(
        {"start_date": "2026-05-01", "end_date": "2026-05-03", "status": "planned"}
    )
    updated = storage.update_status(e["id"], "approved")
    assert updated["status"] == "approved"


def test_update_status_missing(storage):
    assert storage.update_status("ghost", "approved") is None


def test_delete_entry(storage):
    e = storage.create_entry({"start_date": "2026-09-01", "end_date": "2026-09-05"})
    assert storage.delete_entry(e["id"]) is True
    assert storage.get_entry(e["id"]) is None


def test_delete_entry_missing(storage):
    assert storage.delete_entry("ghost") is False


# ── Year filter ────────────────────────────────────────────────────────────


def test_list_filter_by_year(storage):
    storage.create_entry({"start_date": "2025-12-20", "end_date": "2025-12-31"})
    storage.create_entry({"start_date": "2026-01-05", "end_date": "2026-01-10"})
    entries_2026 = storage.list_entries(year=2026)
    assert len(entries_2026) == 1
    assert entries_2026[0]["start_date"] == "2026-01-05"


def test_list_sorted_by_start_date(storage):
    storage.create_entry({"start_date": "2026-09-01", "end_date": "2026-09-05"})
    storage.create_entry({"start_date": "2026-04-01", "end_date": "2026-04-05"})
    storage.create_entry({"start_date": "2026-06-15", "end_date": "2026-06-20"})
    entries = storage.list_entries()
    dates = [e["start_date"] for e in entries]
    assert dates == sorted(dates)


# ── Account calculation ────────────────────────────────────────────────────


def test_account_empty(storage):
    acc = storage.get_account(2026, 30, "BY")
    assert acc["total_days"] == 30
    assert acc["used_days"] == 0
    assert acc["planned_days"] == 0
    assert acc["remaining_days"] == 30


def test_account_with_approved_entry(storage):
    # Mon 2026-04-20 to Fri 2026-04-24 = 5 work days
    e = storage.create_entry(
        {"start_date": "2026-04-20", "end_date": "2026-04-24", "status": "planned"}
    )
    storage.update_status(e["id"], "approved")
    acc = storage.get_account(2026, 30, "BY")
    assert acc["used_days"] == 5
    assert acc["remaining_days"] == 25


def test_account_with_planned_entry(storage):
    storage.create_entry(
        {"start_date": "2026-04-20", "end_date": "2026-04-24", "status": "planned"}
    )
    acc = storage.get_account(2026, 30, "BY")
    assert acc["used_days"] == 0
    assert acc["planned_days"] == 5
    assert acc["remaining_after_planned"] == 25


def test_account_requested_counts_as_planned(storage):
    # 'requested' entries must appear in planned_days, not used_days
    storage.create_entry(
        {"start_date": "2026-04-20", "end_date": "2026-04-24", "status": "requested"}
    )
    acc = storage.get_account(2026, 30, "BY")
    assert acc["used_days"] == 0
    assert acc["planned_days"] == 5
    assert acc["remaining_after_planned"] == 25


def test_account_planned_and_requested_combined(storage):
    storage.create_entry(
        {"start_date": "2026-04-20", "end_date": "2026-04-24", "status": "planned"}
    )
    storage.create_entry(
        {"start_date": "2026-05-04", "end_date": "2026-05-08", "status": "requested"}
    )
    acc = storage.get_account(2026, 30, "BY")
    assert acc["planned_days"] == 10
    assert acc["remaining_after_planned"] == 20


# ── Commit messages ────────────────────────────────────────────────────────


def test_commit_on_create(storage):
    storage.create_entry({"start_date": "2026-07-01", "end_date": "2026-07-05"})
    assert any("vacations: add" in m for m in storage._git._committed)


def test_commit_on_update(storage):
    e = storage.create_entry({"start_date": "2026-07-01", "end_date": "2026-07-05"})
    storage._git._committed.clear()
    storage.update_entry(e["id"], {"start_date": "2026-07-01", "end_date": "2026-07-06"})
    assert any("vacations: update" in m for m in storage._git._committed)


def test_commit_on_status_change(storage):
    e = storage.create_entry({"start_date": "2026-07-01", "end_date": "2026-07-05"})
    storage._git._committed.clear()
    storage.update_status(e["id"], "approved")
    assert any("approved" in m for m in storage._git._committed)


def test_commit_on_delete(storage):
    e = storage.create_entry({"start_date": "2026-07-01", "end_date": "2026-07-05"})
    storage._git._committed.clear()
    storage.delete_entry(e["id"])
    assert any("vacations: delete" in m for m in storage._git._committed)


# ── holidays_helper ────────────────────────────────────────────────────────


def test_get_holidays_returns_dates():
    from modules.vacations.holidays_helper import get_holidays
    from datetime import date

    hols = get_holidays(2026, "BY")
    assert isinstance(hols, set)
    assert date(2026, 1, 1) in hols  # New Year
    assert date(2026, 12, 25) in hols  # Christmas


def test_get_holidays_english():
    from modules.vacations.holidays_helper import get_holidays, _holiday_name

    name = _holiday_name(__import__("datetime").date(2026, 1, 1), "BY", "en_US")
    assert "New Year" in name


def test_get_holidays_german():
    from modules.vacations.holidays_helper import _holiday_name

    name = _holiday_name(__import__("datetime").date(2026, 1, 1), "BY", "de")
    assert "Neujahr" in name


def test_count_work_days_simple():
    from modules.vacations.holidays_helper import count_work_days

    # Mon–Fri = 5 work days (no holidays in that week)
    result = count_work_days("2026-04-20", "2026-04-24", "BY")
    assert result == 5


def test_count_work_days_skips_weekend():
    from modules.vacations.holidays_helper import count_work_days

    # Mon–Sun = 5 work days
    result = count_work_days("2026-04-20", "2026-04-26", "BY")
    assert result == 5


def test_count_work_days_skips_holidays():
    from modules.vacations.holidays_helper import count_work_days

    # Easter Monday 2026-04-06 is a holiday in BY
    result = count_work_days("2026-04-06", "2026-04-06", "BY")
    assert result == 0


def test_count_work_days_invalid():
    from modules.vacations.holidays_helper import count_work_days

    assert count_work_days("bad", "date", "BY") == 0
    assert count_work_days("2026-04-10", "2026-04-01", "BY") == 0


def test_get_calendar_data_structure():
    from modules.vacations.holidays_helper import get_calendar_data

    cal = get_calendar_data(2026, 4, "BY", [])
    assert cal["year"] == 2026
    assert cal["month"] == 4
    assert cal["month_name"] == "April"
    assert len(cal["weeks"]) > 0
    assert "prev_year" in cal
    assert "next_year" in cal


def test_get_calendar_data_holiday_marked():
    from modules.vacations.holidays_helper import get_calendar_data
    from datetime import date

    # Easter Monday 2026-04-06 is a holiday
    cal = get_calendar_data(2026, 4, "BY", [])
    easter_monday = None
    for week in cal["weeks"]:
        for day in week:
            if day and day["date"] == date(2026, 4, 6):
                easter_monday = day
    assert easter_monday is not None
    assert easter_monday["is_holiday"] is True
    assert easter_monday["holiday_name"] != ""


def test_get_calendar_data_vacation_marked():
    from modules.vacations.holidays_helper import get_calendar_data
    from datetime import date

    entries = [{"start_date": "2026-04-20", "end_date": "2026-04-24", "status": "approved"}]
    cal = get_calendar_data(2026, 4, "BY", entries)
    for week in cal["weeks"]:
        for day in week:
            if day and day["date"] == date(2026, 4, 20):
                assert day["is_vacation"] is True


def test_get_calendar_data_pending_marked():
    from modules.vacations.holidays_helper import get_calendar_data
    from datetime import date

    entries = [{"start_date": "2026-04-20", "end_date": "2026-04-22", "status": "planned"}]
    cal = get_calendar_data(2026, 4, "BY", entries)
    for week in cal["weeks"]:
        for day in week:
            if day and day["date"] == date(2026, 4, 20):
                assert day["is_vacation_pending"] is True
                assert day["is_vacation"] is False


def test_get_calendar_prev_next_month():
    from modules.vacations.holidays_helper import get_calendar_data

    cal = get_calendar_data(2026, 1, "BY", [])
    assert cal["prev_month"] == 12
    assert cal["prev_year"] == 2025
    assert cal["next_month"] == 2
    assert cal["next_year"] == 2026


def test_get_calendar_dec_next():
    from modules.vacations.holidays_helper import get_calendar_data

    cal = get_calendar_data(2026, 12, "BY", [])
    assert cal["next_month"] == 1
    assert cal["next_year"] == 2027
