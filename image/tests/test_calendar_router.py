"""Tests for the central Calendar module router."""

import os
import sys

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"

import main as _main_module


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
    def _pull(self): pass
    def _commit_and_push(self, msg): pass

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


# ── /calendar ─────────────────────────────────────────────────────────────────

def test_calendar_loads(client):
    resp = client.get("/calendar")
    assert resp.status_code == 200
    assert "Calendar" in resp.text


def test_calendar_with_year_month(client):
    resp = client.get("/calendar?year=2026&month=4")
    assert resp.status_code == 200


def test_calendar_defaults_to_today(client):
    from datetime import date
    resp = client.get("/calendar")
    assert resp.status_code == 200
    today = date.today()
    assert str(today.year) in resp.text


def test_calendar_with_no_storage(client):
    """Works even without any repos configured."""
    resp = client.get("/calendar")
    assert resp.status_code == 200


def test_calendar_with_vacation_storage(client, tmp_path):
    from unittest.mock import patch
    from modules.vacations.storage import VacationStorage

    fake_git = FakeGit(tmp_path)
    vs = VacationStorage(fake_git)
    vs.create_entry({
        "start_date": "2026-04-01",
        "end_date": "2026-04-03",
        "note": "Ostern",
        "status": "approved",
    })

    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    fake_storage.get_categories.return_value = []

    with patch("modules.calendar.router.get_storage", return_value=fake_storage), \
         patch("modules.calendar.router.get_primary_store", side_effect=lambda mod, _: fake_git if mod == "vacations" else None):
        resp = client.get("/calendar?year=2026&month=4")
        assert resp.status_code == 200


def test_calendar_with_appointment_storage(client, tmp_path):
    from unittest.mock import patch
    from modules.appointments.storage import AppointmentStorage

    fake_git = FakeGit(tmp_path)
    aps = AppointmentStorage(fake_git)
    aps.create_entry({
        "title": "Conference",
        "start_date": "2026-04-15",
        "end_date": "2026-04-17",
        "type": "conference",
        "note": "",
    })

    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    fake_storage.get_categories.return_value = []

    with patch("modules.calendar.router.get_storage", return_value=fake_storage), \
         patch("modules.calendar.router.get_primary_store", side_effect=lambda mod, _: fake_git if mod == "appointments" else None):
        resp = client.get("/calendar?year=2026&month=4")
        assert resp.status_code == 200
        assert "Conference" in resp.text


def test_calendar_both_modules_disabled(client, tmp_path):
    from core import settings_store
    cfg = settings_store.load()
    cfg["modules_enabled"]["vacations"] = False
    cfg["modules_enabled"]["appointments"] = False
    settings_store.save(cfg)

    resp = client.get("/calendar")
    assert resp.status_code == 200


# ── Redirects from old module calendar URLs ──────────────────────────────────

def test_vacations_calendar_redirect(client):
    resp = client.get("/vacations/calendar", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"].startswith("/calendar")


def test_vacations_calendar_redirect_with_params(client):
    resp = client.get("/vacations/calendar?year=2026&month=6", follow_redirects=False)
    assert resp.status_code == 301
    loc = resp.headers["location"]
    assert "year=2026" in loc
    assert "month=6" in loc


def test_appointments_calendar_redirect(client):
    resp = client.get("/appointments/calendar", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"].startswith("/calendar")


def test_appointments_calendar_redirect_with_params(client):
    resp = client.get("/appointments/calendar?year=2025&month=12", follow_redirects=False)
    assert resp.status_code == 301
    loc = resp.headers["location"]
    assert "year=2025" in loc
    assert "month=12" in loc


def test_appointments_calendar_redirect_no_params(client):
    resp = client.get("/appointments/calendar", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/calendar"


def test_calendar_vacations_redirect_endpoint(client):
    resp = client.get("/calendar/vacations-redirect", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/calendar"


def test_calendar_vacations_redirect_with_params(client):
    resp = client.get("/calendar/vacations-redirect?year=2026&month=8", follow_redirects=False)
    assert resp.status_code == 301
    loc = resp.headers["location"]
    assert "year=2026" in loc
    assert "month=8" in loc


def test_calendar_vacation_storage_exception(client, tmp_path):
    """Lines 40-41: exception in VacationStorage is caught silently."""
    from unittest.mock import patch, MagicMock

    fake_storage = MagicMock()
    fake_storage.get_categories.return_value = []
    fake_storage._stores = {}

    broken_git = MagicMock()
    broken_git.list_committed.side_effect = RuntimeError("disk error")

    with patch("modules.calendar.router.get_storage", return_value=fake_storage), \
         patch("modules.calendar.router.get_primary_store", side_effect=lambda mod, _: broken_git if mod == "vacations" else None):
        resp = client.get("/calendar")
        assert resp.status_code == 200


def test_calendar_appointment_storage_exception(client, tmp_path):
    """Lines 51-52: exception in AppointmentStorage is caught silently."""
    from unittest.mock import patch, MagicMock

    fake_storage = MagicMock()
    fake_storage.get_categories.return_value = []
    fake_storage._stores = {}

    broken_git = MagicMock()
    broken_git.list_committed.side_effect = RuntimeError("disk error")

    with patch("modules.calendar.router.get_storage", return_value=fake_storage), \
         patch("modules.calendar.router.get_primary_store", side_effect=lambda mod, _: broken_git if mod == "appointments" else None):
        resp = client.get("/calendar")
        assert resp.status_code == 200


def test_calendar_tasks_loaded(client, tmp_path):
    """Lines 58-62: tasks loop iterates _stores."""
    from unittest.mock import patch, MagicMock
    from modules.tasks.storage import TaskStorage

    fake_git = FakeGit(tmp_path)
    ts = TaskStorage(fake_git)
    ts.create_task({"title": "Cal Task", "due_date": "2026-04-20", "priority": "medium"})

    fake_store = MagicMock()
    fake_store._stores = {"r1": fake_git}
    fake_store.get_categories.return_value = []

    with patch("modules.calendar.router.get_storage", return_value=fake_store), \
         patch("modules.calendar.router.get_primary_store", return_value=None):
        resp = client.get("/calendar?year=2026&month=4")
        assert resp.status_code == 200
