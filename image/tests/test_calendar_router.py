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

    def write_lock(self):
        """The storage layer takes this around pull/commit."""
        if not hasattr(self, "_write_lock"):
            import threading

            self._write_lock = threading.RLock()
        return self._write_lock

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        pass

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
    from core.state import reset_storage
    from fastapi.testclient import TestClient

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
    assert "2026" in resp.text
    assert "April" in resp.text


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
    vs.create_entry(
        {
            "start_date": "2026-04-01",
            "end_date": "2026-04-03",
            "note": "Ostern",
            "status": "approved",
        }
    )

    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    fake_storage.get_categories.return_value = []

    with (
        patch("modules.calendar.router.get_storage", return_value=fake_storage),
        patch(
            "modules.calendar.router.get_primary_store",
            side_effect=lambda mod, _: fake_git if mod == "vacations" else None,
        ),
    ):
        resp = client.get("/calendar?year=2026&month=4")
        assert resp.status_code == 200


def test_calendar_with_appointment_storage(client, tmp_path):
    from unittest.mock import patch

    from modules.appointments.storage import AppointmentStorage

    fake_git = FakeGit(tmp_path)
    aps = AppointmentStorage(fake_git)
    aps.create_entry(
        {
            "title": "Conference",
            "start_date": "2026-04-15",
            "end_date": "2026-04-17",
            "type": "conference",
            "note": "",
        }
    )

    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    fake_storage.get_categories.return_value = []

    with (
        patch("modules.calendar.router.get_storage", return_value=fake_storage),
        patch(
            "modules.calendar.router.get_primary_store",
            side_effect=lambda mod, _: fake_git if mod == "appointments" else None,
        ),
    ):
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
    from unittest.mock import MagicMock, patch

    fake_storage = MagicMock()
    fake_storage.get_categories.return_value = []
    fake_storage._stores = {}

    broken_git = MagicMock()
    broken_git.list_committed.side_effect = RuntimeError("disk error")

    with (
        patch("modules.calendar.router.get_storage", return_value=fake_storage),
        patch(
            "modules.calendar.router.get_primary_store",
            side_effect=lambda mod, _: broken_git if mod == "vacations" else None,
        ),
    ):
        resp = client.get("/calendar")
        assert resp.status_code == 200


def test_calendar_appointment_storage_exception(client, tmp_path):
    """Lines 51-52: exception in AppointmentStorage is caught silently."""
    from unittest.mock import MagicMock, patch

    fake_storage = MagicMock()
    fake_storage.get_categories.return_value = []
    fake_storage._stores = {}

    broken_git = MagicMock()
    broken_git.list_committed.side_effect = RuntimeError("disk error")

    with (
        patch("modules.calendar.router.get_storage", return_value=fake_storage),
        patch(
            "modules.calendar.router.get_primary_store",
            side_effect=lambda mod, _: broken_git if mod == "appointments" else None,
        ),
    ):
        resp = client.get("/calendar")
        assert resp.status_code == 200


def test_calendar_tasks_loaded(client, tmp_path):
    """Lines 58-62: tasks loop iterates _stores."""
    from unittest.mock import MagicMock, patch

    from modules.tasks.storage import TaskStorage

    fake_git = FakeGit(tmp_path)
    ts = TaskStorage(fake_git)
    ts.create_task({"title": "Cal Task", "due_date": "2026-04-20", "priority": "medium"})

    fake_store = MagicMock()
    fake_store._stores = {"r1": fake_git}
    fake_store.get_categories.return_value = []

    with (
        patch("modules.calendar.router.get_storage", return_value=fake_store),
        patch("modules.calendar.router.get_primary_store", return_value=None),
    ):
        resp = client.get("/calendar?year=2026&month=4")
        assert resp.status_code == 200


# ── /calendar/holiday.ics ─────────────────────────────────────────────────────


def test_holiday_ics_team_and_own_blocker_profiles(client):
    """Two holiday profiles like for vacations: a team entry (all day) and an
    own blocker with times. Each download follows its own profile."""
    from core import settings_store

    team = settings_store.upsert_holiday_ics_profile({"name": "Team", "show_as": "free", "all_day": True})
    own = settings_store.upsert_holiday_ics_profile(
        {"name": "Own blocker", "show_as": "oof", "all_day": False, "start_time": "08:05", "end_time": "17:00"}
    )
    r_team = client.get(f"/calendar/holiday.ics?date=2026-01-01&name=Neujahr&profile={team['id']}")
    r_own = client.get(f"/calendar/holiday.ics?date=2026-01-01&name=Neujahr&profile={own['id']}")
    assert r_team.status_code == 200 and r_own.status_code == 200
    assert "DTSTART;VALUE=DATE:20260101" in r_team.text
    assert "DTSTART;TZID=Europe/Berlin:20260101T080500" in r_own.text
    assert "own-blocker_2026-01-01" in r_own.headers["content-disposition"]


def test_holiday_ics_without_profile_gives_plain_all_day_event(client):
    """Like the plain Outlook download for vacations: works without any
    configured profile."""
    resp = client.get("/calendar/holiday.ics?date=2026-01-01&name=Neujahr")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Neujahr" in resp.text
    assert "DTSTART;VALUE=DATE:20260101" in resp.text
    assert "DTEND;VALUE=DATE:20260102" in resp.text
    assert "holiday_2026-01-01_neujahr.ics" in resp.headers["content-disposition"]


def test_holiday_ics_unknown_profile_is_404(client):
    resp = client.get("/calendar/holiday.ics?date=2026-01-01&name=Neujahr&profile=nope")
    assert resp.status_code == 404


def test_calendar_offers_plain_holiday_download_without_profiles(client):
    """The plain download button is there even when no holiday profile exists,
    as it is for vacations."""
    resp = client.get("/calendar?year=2026&month=1")
    assert resp.status_code == 200
    assert "/calendar/holiday.ics?date=2026-01-01&name=" in resp.text


def test_holiday_profile_forms_default_to_all_day_like_vacations(client):
    """Since the export honours the times, an unchecked "all day" turns a holiday
    profile into a timed blocker. The new-profile form had it unchecked by
    default, and a legacy profile without the key showed it unchecked in the
    edit form, so saving it unchanged would have switched it silently. Both
    now default to all day, as the vacation form does."""
    import re

    from core import settings_store

    legacy = settings_store.upsert_holiday_ics_profile({"name": "Legacy", "show_as": "free"})
    html = client.get("/settings").text
    new_cb = re.search(r'<input[^>]*id="hol-ics-new-allday"[^>]*>', html).group(0)
    edit_cb = re.search(rf'<input[^>]*id="hol-ics-allday-{legacy["id"]}"[^>]*>', html).group(0)
    assert "checked" in new_cb
    assert "checked" in edit_cb
    assert 'id="hol-ics-time-fields" style="display:none"' in html
    # The profile card summary agrees: a legacy profile reads as all day.
    card = html.index(f"toggleHolIcsEditForm('{legacy['id']}')")
    header = html[html.rfind('<div class="template-card-header">', 0, card) : card]
    assert "All-day" in header, header
    assert f'id="hol-ics-edit-time-{legacy["id"]}" style="display:none"' in html


def test_holiday_ics_invalid_date_is_rejected(client):
    """A malformed date used to fall back silently to an event for today, with
    the raw string in the filename; it must fail loudly instead."""
    for bad in ("2026-13-01", "03.10.2026", 'x" y;z'):
        resp = client.get("/calendar/holiday.ics", params={"date": bad, "name": "Neujahr"})
        assert resp.status_code == 400, bad


def test_holiday_ics_requires_date_and_name(client):
    """The route is open without a profile now; a missing date or name must
    not fall through to an event for today or an empty filename."""
    assert client.get("/calendar/holiday.ics?date=2026-01-01").status_code == 400
    assert client.get("/calendar/holiday.ics?name=Neujahr").status_code == 400


def test_calendar_plain_holiday_link_encodes_the_name(client):
    """Holiday names contain spaces (and could contain & or #), which would
    break the query string unencoded."""
    resp = client.get("/calendar?year=2026&month=10")
    assert "name=Tag%20der%20Deutschen%20Einheit" in resp.text
