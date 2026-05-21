"""Tests for the Appointments module — storage and router."""

import os
import sys

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

import main as _main_module


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


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)
    from core import settings_store as ss

    _main_module.settings_store = ss
    yield
    from core.state import reset_storage

    reset_storage()


@pytest.fixture()
def client(isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


# ── AppointmentStorage ─────────────────────────────────────────────────────


def test_create_and_list(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Python Training",
            "start_date": "2026-05-15",
            "end_date": "2026-05-16",
            "type": "training",
            "note": "Provider XYZ",
        }
    )
    assert entry["id"]
    assert entry["title"] == "Python Training"
    assert entry["type"] == "training"

    entries = s.list_entries()
    assert len(entries) == 1
    assert entries[0]["title"] == "Python Training"


def test_list_empty(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    assert s.list_entries() == []


def test_list_filter_by_year(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    s.create_entry(
        {"title": "A", "start_date": "2026-03-01", "end_date": "2026-03-01", "type": "other"}
    )
    s.create_entry(
        {"title": "B", "start_date": "2027-06-01", "end_date": "2027-06-01", "type": "other"}
    )

    r2026 = s.list_entries(year=2026)
    assert len(r2026) == 1
    assert r2026[0]["title"] == "A"


def test_get_entry(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Conf",
            "start_date": "2026-09-10",
            "end_date": "2026-09-12",
            "type": "conference",
        }
    )
    fetched = s.get_entry(entry["id"])
    assert fetched["title"] == "Conf"


def test_get_entry_missing(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    assert s.get_entry("nonexistent") is None


def test_update_entry(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Old Title",
            "start_date": "2026-01-10",
            "end_date": "2026-01-10",
            "type": "other",
        }
    )
    updated = s.update_entry(
        entry["id"],
        {
            "title": "New Title",
            "start_date": "2026-01-10",
            "end_date": "2026-01-11",
            "type": "training",
            "note": "updated note",
        },
    )
    assert updated["title"] == "New Title"
    assert updated["type"] == "training"
    assert updated["end_date"] == "2026-01-11"


def test_update_entry_missing(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    assert s.update_entry("missing", {"title": "x"}) is None


def test_update_invalid_type_falls_back(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {"title": "X", "start_date": "2026-01-01", "end_date": "2026-01-01", "type": "training"}
    )
    updated = s.update_entry(entry["id"], {"type": "INVALID_TYPE"})
    assert updated["type"] == "training"  # keeps original


def test_delete_entry(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Delete Me",
            "start_date": "2026-02-01",
            "end_date": "2026-02-01",
            "type": "other",
        }
    )
    assert s.delete_entry(entry["id"]) is True
    assert s.list_entries() == []


def test_delete_entry_missing(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    assert s.delete_entry("does-not-exist") is False


def test_create_invalid_type_defaults_to_other(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {"title": "X", "start_date": "2026-01-01", "end_date": "2026-01-01", "type": "spaceship"}
    )
    assert entry["type"] == "other"


def test_sorted_by_date(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    s.create_entry(
        {"title": "B", "start_date": "2026-06-01", "end_date": "2026-06-01", "type": "other"}
    )
    s.create_entry(
        {"title": "A", "start_date": "2026-03-01", "end_date": "2026-03-01", "type": "other"}
    )
    entries = s.list_entries()
    assert entries[0]["title"] == "A"
    assert entries[1]["title"] == "B"


# ── holidays_helper: appointment overlay ──────────────────────────────────


def test_get_calendar_data_with_appointments():
    from modules.vacations.holidays_helper import get_calendar_data
    from datetime import date

    appt_entries = [
        {
            "title": "Training",
            "start_date": "2026-04-15",
            "end_date": "2026-04-17",
            "type": "training",
        }
    ]

    cal = get_calendar_data(2026, 4, "BY", [], appointment_entries=appt_entries)

    # Find April 15-17
    appointment_days = []
    for week in cal["weeks"]:
        for day in week:
            if day and day.get("is_appointment"):
                appointment_days.append(day["day"])

    assert 15 in appointment_days
    assert 16 in appointment_days
    assert 17 in appointment_days


def test_get_calendar_data_no_appointments():
    from modules.vacations.holidays_helper import get_calendar_data

    cal = get_calendar_data(2026, 4, "BY", [])
    # All days should have is_appointment=False by default
    for week in cal["weeks"]:
        for day in week:
            if day:
                assert day.get("is_appointment") is False


def test_get_calendar_data_appointment_outside_month():
    from modules.vacations.holidays_helper import get_calendar_data

    appt_entries = [
        {"title": "Future", "start_date": "2026-05-10", "end_date": "2026-05-10", "type": "other"}
    ]
    cal = get_calendar_data(2026, 4, "BY", [], appointment_entries=appt_entries)
    for week in cal["weeks"]:
        for day in week:
            if day:
                assert not day.get("is_appointment")


# ── Router endpoints ────────────────────────────────────────────────────────


def test_list_not_configured(client):
    resp = client.get("/appointments")
    assert resp.status_code == 200
    assert "No repository" in resp.text


def test_calendar_not_configured(client):
    resp = client.get("/appointments/calendar")
    assert resp.status_code == 200


def test_create_no_storage(client):
    resp = client.post(
        "/appointments",
        data={
            "title": "Test",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "type": "training",
        },
        follow_redirects=False,
    )
    # 503 when no storage configured
    assert resp.status_code == 503


def _setup_repo(client, tmp_path):
    """Helper: configure a repo in settings so storage is available."""
    from core import settings_store
    from core.state import reset_storage
    import shutil

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    cfg = settings_store.load()
    repo_id = "test-repo-1"
    cfg["repos"] = [
        {
            "id": repo_id,
            "name": "Test",
            "url": "file://" + str(repo_dir),
            "platform": "gitea",
            "auth_mode": "none",
            "enabled": True,
            "permissions": {"read": True, "write": True},
        }
    ]
    cfg["module_repos"]["appointments"] = {"repos": [repo_id], "primary": repo_id}
    settings_store.save(cfg)
    reset_storage()
    return repo_id, repo_dir


def test_create_and_list_with_storage(client, tmp_path, monkeypatch):
    from unittest.mock import patch, MagicMock
    from modules.appointments.storage import AppointmentStorage

    fake_git = FakeGit(tmp_path)
    fake_storage = MagicMock()
    fake_storage._stores = {"r1": fake_git}

    with (
        patch("modules.appointments.router.get_storage", return_value=fake_storage),
        patch("modules.appointments.router.get_primary_store", return_value=fake_git),
    ):
        resp = client.post(
            "/appointments",
            data={
                "title": "Python Workshop",
                "start_date": "2026-05-15",
                "end_date": "2026-05-16",
                "type": "training",
                "note": "External",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        resp = client.get("/appointments")
        assert resp.status_code == 200
        assert "Python Workshop" in resp.text


def test_edit_form_not_found(client, tmp_path, monkeypatch):
    from unittest.mock import patch

    fake_git = FakeGit(tmp_path)
    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    fake_storage._stores = {"r1": fake_git}

    with (
        patch("modules.appointments.router.get_storage", return_value=fake_storage),
        patch("modules.appointments.router.get_primary_store", return_value=fake_git),
    ):
        resp = client.get("/appointments/nonexistent/edit")
        assert resp.status_code == 404


def test_delete_not_found(client, tmp_path, monkeypatch):
    from unittest.mock import patch

    fake_git = FakeGit(tmp_path)
    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()

    with (
        patch("modules.appointments.router.get_storage", return_value=fake_storage),
        patch("modules.appointments.router.get_primary_store", return_value=fake_git),
    ):
        resp = client.post("/appointments/nonexistent/delete", follow_redirects=False)
        assert resp.status_code == 404


def test_full_crud_cycle(tmp_path):
    """Unit-level CRUD cycle via storage directly."""
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))

    # Create
    entry = s.create_entry(
        {
            "title": "DevConf",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "type": "conference",
            "note": "Berlin",
        }
    )
    assert entry["title"] == "DevConf"

    # Update
    updated = s.update_entry(
        entry["id"],
        {
            "title": "DevConf 2026",
            "start_date": "2026-10-01",
            "end_date": "2026-10-04",
            "type": "conference",
            "note": "Berlin, extended",
        },
    )
    assert updated["title"] == "DevConf 2026"
    assert updated["end_date"] == "2026-10-04"

    # Read back
    fetched = s.get_entry(entry["id"])
    assert fetched["note"] == "Berlin, extended"

    # Delete
    assert s.delete_entry(entry["id"]) is True
    assert s.get_entry(entry["id"]) is None


# ── Recurring appointments ─────────────────────────────────────────────────


def test_create_with_recurring(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Weekly Standup",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "type": "other",
            "recurring": "weekly",
        }
    )
    assert entry["recurring"] == "weekly"


def test_create_invalid_recurring_defaults_to_none(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "X",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "recurring": "biannual",
        }
    )
    assert entry["recurring"] == "none"


def test_delete_weekly_recurring_creates_next(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Weekly",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "recurring": "weekly",
        }
    )
    entry_id = entry["id"]
    assert s.delete_entry(entry_id) is True

    remaining = s.list_entries()
    assert len(remaining) == 1
    assert remaining[0]["start_date"] == "2026-05-08"
    assert remaining[0]["recurring"] == "weekly"
    assert remaining[0]["id"] != entry_id


def test_delete_monthly_recurring_creates_next(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Monthly Review",
            "start_date": "2026-01-31",
            "end_date": "2026-01-31",
            "recurring": "monthly",
        }
    )
    s.delete_entry(entry["id"])
    remaining = s.list_entries()
    assert remaining[0]["start_date"] == "2026-02-28"


def test_delete_yearly_recurring_creates_next(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "Annual Event",
            "start_date": "2026-06-15",
            "end_date": "2026-06-17",
            "recurring": "yearly",
        }
    )
    s.delete_entry(entry["id"])
    remaining = s.list_entries()
    assert remaining[0]["start_date"] == "2027-06-15"
    assert remaining[0]["end_date"] == "2027-06-17"


def test_delete_none_recurring_creates_no_next(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry(
        {
            "title": "One-off",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "recurring": "none",
        }
    )
    s.delete_entry(entry["id"])
    assert s.list_entries() == []


def test_update_sets_recurring(tmp_path):
    from modules.appointments.storage import AppointmentStorage

    s = AppointmentStorage(FakeGit(tmp_path))
    entry = s.create_entry({"title": "X", "start_date": "2026-05-01", "end_date": "2026-05-01"})
    updated = s.update_entry(
        entry["id"],
        {
            "title": "X",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "recurring": "monthly",
        },
    )
    assert updated["recurring"] == "monthly"


# ── Operations: appointments copy/move ─────────────────────────────────────


def test_operations_get_items_appointments(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.appointments.storage import AppointmentStorage

    fake_git = FakeGit(tmp_path)
    s = AppointmentStorage(fake_git)
    s.create_entry(
        {
            "title": "Training",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "type": "training",
        }
    )

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "appointments")
    assert len(result) == 1
    assert result[0]["title"] == "Training"


def test_operations_copy_appointments(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.appointments.storage import AppointmentStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    s = AppointmentStorage(src_git)
    entry = s.create_entry(
        {"title": "Copy Me", "start_date": "2026-06-01", "end_date": "2026-06-01", "type": "other"}
    )

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "appointments", [entry["id"]], "copy")
    assert count == 1
    assert errors == []
    assert (dst_path / "appointments" / "entries" / f"{entry['id']}.yaml").exists()


def test_operations_move_appointments(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.appointments.storage import AppointmentStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    s = AppointmentStorage(src_git)
    entry = s.create_entry(
        {"title": "Move Me", "start_date": "2026-07-01", "end_date": "2026-07-01", "type": "other"}
    )
    src_file = src_path / "appointments" / "entries" / f"{entry['id']}.yaml"
    assert src_file.exists()

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "appointments", [entry["id"]], "move")
    assert count == 1
    assert not src_file.exists()
