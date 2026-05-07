"""Tests for Appointments ICS generator and export routes."""

import os
import sys
from datetime import date

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


# ── Fixtures ────────────────────────────────────────────────────────────────


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)

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
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


# ── ics_generator: _all_days ────────────────────────────────────────────────


def test_all_days_single():
    from modules.appointments.ics_generator import _all_days

    days = _all_days("2026-05-01", "2026-05-01")
    assert days == [date(2026, 5, 1)]


def test_all_days_range():
    from modules.appointments.ics_generator import _all_days

    days = _all_days("2026-05-01", "2026-05-03")
    assert len(days) == 3
    assert days[0] == date(2026, 5, 1)
    assert days[2] == date(2026, 5, 3)


def test_all_days_includes_weekends():
    from modules.appointments.ics_generator import _all_days

    # 2026-05-01 is Friday, 2026-05-04 is Monday
    days = _all_days("2026-05-01", "2026-05-04")
    assert len(days) == 4  # Fri, Sat, Sun, Mon — all included


def test_all_days_empty_on_inverted_range():
    from modules.appointments.ics_generator import _all_days

    assert _all_days("2026-05-05", "2026-05-01") == []


def test_all_days_invalid_date():
    from modules.appointments.ics_generator import _all_days

    assert _all_days("not-a-date", "2026-05-01") == []


# ── ics_generator: generate_ics ─────────────────────────────────────────────


def test_generate_ics_basic():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "test-1",
        "title": "Python Training",
        "start_date": "2026-05-04",
        "end_date": "2026-05-05",
        "type": "training",
        "note": "External provider",
    }
    profile = {"show_as": "busy", "all_day": True, "subject": "{title}"}
    ics = generate_ics(entry, profile)
    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "Python Training" in ics
    assert "PRODID:-//Daily Helper//Appointments//EN" in ics


def test_generate_ics_all_day_events():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t1",
        "title": "Conf",
        "start_date": "2026-06-01",
        "end_date": "2026-06-02",
        "type": "conference",
        "note": "",
    }
    profile = {"show_as": "busy", "all_day": True, "subject": "{title}"}
    ics = generate_ics(entry, profile)
    assert "DTSTART;VALUE=DATE:20260601" in ics
    assert "DTEND;VALUE=DATE:20260602" in ics
    assert "DTSTART;VALUE=DATE:20260602" in ics
    assert "DTEND;VALUE=DATE:20260603" in ics  # +1 day (exclusive)


def test_generate_ics_timed_events():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t2",
        "title": "Meeting",
        "start_date": "2026-05-04",
        "end_date": "2026-05-04",
        "type": "team_event",
        "note": "",
    }
    profile = {
        "show_as": "busy",
        "all_day": False,
        "start_time": "09:00",
        "end_time": "17:00",
        "subject": "{title}",
    }
    ics = generate_ics(entry, profile)
    assert "VTIMEZONE" in ics
    assert "DTSTART;TZID=Europe/Berlin:20260504T090000" in ics
    assert "DTEND;TZID=Europe/Berlin:20260504T170000" in ics


def test_generate_ics_timed_fallback_time():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t3",
        "title": "X",
        "start_date": "2026-05-04",
        "end_date": "2026-05-04",
        "type": "other",
        "note": "",
    }
    profile = {
        "show_as": "busy",
        "all_day": False,
        "start_time": "bad",
        "end_time": "bad",
        "subject": "{title}",
    }
    ics = generate_ics(entry, profile)
    assert "T080000" in ics  # fallback 08:00
    assert "T170000" in ics  # fallback 17:00


def test_generate_ics_placeholders():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t4",
        "title": "Schulung",
        "start_date": "2026-05-04",
        "end_date": "2026-05-06",
        "type": "training",
        "note": "Wichtig",
    }
    profile = {
        "show_as": "busy",
        "all_day": True,
        "subject": "{title} {start_date}–{end_date}",
        "body": "{note} ({days} days)",
    }
    ics = generate_ics(entry, profile)
    assert "Schulung 2026-05-04" in ics
    assert "Wichtig (3 days)" in ics


def test_generate_ics_with_recipients():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t5",
        "title": "Team Day",
        "start_date": "2026-05-04",
        "end_date": "2026-05-04",
        "type": "team_event",
        "note": "",
    }
    profile = {
        "show_as": "free",
        "all_day": True,
        "subject": "{title}",
        "recipients": ["boss@company.com", "team@company.com"],
    }
    ics = generate_ics(entry, profile)
    assert "mailto:boss@company.com" in ics
    assert "mailto:team@company.com" in ics


def test_generate_ics_with_category():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t6",
        "title": "Trip",
        "start_date": "2026-05-04",
        "end_date": "2026-05-04",
        "type": "business_trip",
        "note": "",
    }
    profile = {"show_as": "oof", "all_day": True, "subject": "{title}", "category": "Blue Category"}
    ics = generate_ics(entry, profile)
    assert "CATEGORIES:Blue Category" in ics


def test_generate_ics_empty_range():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t7",
        "title": "X",
        "start_date": "2026-05-05",
        "end_date": "2026-05-04",
        "type": "other",
        "note": "",
    }
    profile = {"show_as": "busy", "all_day": True, "subject": "{title}"}
    ics = generate_ics(entry, profile)
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" not in ics  # no days → no events


def test_generate_ics_default_subject():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t8",
        "title": "Workshop",
        "start_date": "2026-06-01",
        "end_date": "2026-06-01",
        "type": "training",
        "note": "",
    }
    profile = {"show_as": "busy", "all_day": True}  # no subject key
    ics = generate_ics(entry, profile)
    assert "Workshop" in ics  # default uses {title}


def test_generate_ics_oof_busystatus():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t9",
        "title": "Away",
        "start_date": "2026-06-01",
        "end_date": "2026-06-01",
        "type": "other",
        "note": "",
    }
    profile = {"show_as": "oof", "all_day": True, "subject": "Away"}
    ics = generate_ics(entry, profile)
    assert "X-MICROSOFT-CDO-BUSYSTATUS:OOF" in ics
    assert "TRANSP:OPAQUE" in ics


def test_generate_ics_free_transparent():
    from modules.appointments.ics_generator import generate_ics

    entry = {
        "id": "t10",
        "title": "Flex",
        "start_date": "2026-06-01",
        "end_date": "2026-06-01",
        "type": "other",
        "note": "",
    }
    profile = {"show_as": "free", "all_day": True, "subject": "Flex"}
    ics = generate_ics(entry, profile)
    assert "TRANSP:TRANSPARENT" in ics
    assert "X-MICROSOFT-CDO-BUSYSTATUS:FREE" in ics


# ── profile_filename ─────────────────────────────────────────────────────────


def test_profile_filename_basic():
    from modules.appointments.ics_generator import profile_filename

    p = {"name": "Team Calendar"}
    fn = profile_filename(p)
    assert fn == "team-calendar.ics"


def test_profile_filename_with_entry():
    from modules.appointments.ics_generator import profile_filename

    p = {"name": "My Profile"}
    e = {"start_date": "2026-05-04", "end_date": "2026-05-08"}
    fn = profile_filename(p, e)
    assert fn == "my-profile_2026-05-04_2026-05-08.ics"


def test_profile_filename_special_chars():
    from modules.appointments.ics_generator import profile_filename

    p = {"name": "Büro & Team!"}
    fn = profile_filename(p)
    assert ".ics" in fn
    assert "&" not in fn


def test_profile_filename_empty_name():
    from modules.appointments.ics_generator import profile_filename

    fn = profile_filename({})
    assert fn == "export.ics"


# ── settings_store: appointment_ics_profiles ─────────────────────────────────


def test_get_appointment_ics_profiles_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)
    assert settings_store.get_appointment_ics_profiles() == []


def test_upsert_and_get_appointment_ics_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)

    profile = settings_store.upsert_appointment_ics_profile(
        {
            "name": "Team Cal",
            "show_as": "busy",
            "all_day": True,
            "subject": "{title}",
            "body": "{note}",
        }
    )
    assert profile["id"]
    fetched = settings_store.get_appointment_ics_profile(profile["id"])
    assert fetched["name"] == "Team Cal"


def test_upsert_appointment_ics_profile_update(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)

    p = settings_store.upsert_appointment_ics_profile(
        {"name": "Old", "show_as": "busy", "all_day": True}
    )
    settings_store.upsert_appointment_ics_profile(
        {"id": p["id"], "name": "New", "show_as": "free", "all_day": False}
    )
    profiles = settings_store.get_appointment_ics_profiles()
    assert len(profiles) == 1
    assert profiles[0]["name"] == "New"


def test_delete_appointment_ics_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)

    p = settings_store.upsert_appointment_ics_profile(
        {"name": "X", "show_as": "busy", "all_day": True}
    )
    assert settings_store.delete_appointment_ics_profile(p["id"]) is True
    assert settings_store.get_appointment_ics_profiles() == []


def test_delete_appointment_ics_profile_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)

    assert settings_store.delete_appointment_ics_profile("nonexistent") is False


def test_get_appointment_ics_profile_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)

    assert settings_store.get_appointment_ics_profile("not-there") is None


# ── main.py: appointment-ics-profiles routes ─────────────────────────────────


def test_add_appointment_ics_profile(client):
    resp = client.post(
        "/settings/appointment-ics-profiles",
        data={
            "name": "My Profile",
            "show_as": "busy",
            "all_day": "on",
            "subject": "{title}",
            "body": "{note}",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    profiles = settings_store.get_appointment_ics_profiles()
    assert len(profiles) == 1
    assert profiles[0]["name"] == "My Profile"
    assert profiles[0]["all_day"] is True


def test_add_appointment_ics_profile_timed(client):
    resp = client.post(
        "/settings/appointment-ics-profiles",
        data={
            "name": "Timed",
            "show_as": "oof",
            "start_time": "09:00",
            "end_time": "17:30",
            "subject": "{title} {start_date}",
            "body": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    profiles = settings_store.get_appointment_ics_profiles()
    assert profiles[0]["all_day"] is False
    assert profiles[0]["start_time"] == "09:00"


def test_edit_appointment_ics_profile(client):
    from core import settings_store

    p = settings_store.upsert_appointment_ics_profile(
        {
            "name": "Old",
            "show_as": "busy",
            "all_day": True,
            "subject": "X",
            "body": "",
        }
    )
    resp = client.post(
        f"/settings/appointment-ics-profiles/{p['id']}/edit",
        data={
            "name": "Updated",
            "show_as": "free",
            "all_day": "on",
            "subject": "{title} updated",
            "body": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    updated = settings_store.get_appointment_ics_profile(p["id"])
    assert updated["name"] == "Updated"
    assert updated["show_as"] == "free"


def test_delete_appointment_ics_profile_route(client):
    from core import settings_store

    p = settings_store.upsert_appointment_ics_profile(
        {
            "name": "ToDelete",
            "show_as": "busy",
            "all_day": True,
            "subject": "X",
            "body": "",
        }
    )
    resp = client.post(
        f"/settings/appointment-ics-profiles/{p['id']}/delete", follow_redirects=False
    )
    assert resp.status_code == 303
    assert settings_store.get_appointment_ics_profiles() == []


# ── export.ics route ─────────────────────────────────────────────────────────


def test_export_ics_no_storage(client):
    resp = client.get("/appointments/test-id/export.ics")
    assert resp.status_code == 503


def test_export_ics_entry_not_found(client, tmp_path):
    from unittest.mock import patch

    fake_git = FakeGit(tmp_path)
    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()

    with (
        patch("modules.appointments.router.get_storage", return_value=fake_storage),
        patch("modules.appointments.router.get_primary_store", return_value=fake_git),
        patch("modules.appointments.router.get_module_stores", return_value=[fake_git]),
    ):
        resp = client.get("/appointments/nonexistent/export.ics")
        assert resp.status_code == 404


def test_export_ics_default_profile(client, tmp_path):
    from unittest.mock import patch
    from modules.appointments.storage import AppointmentStorage

    fake_git = FakeGit(tmp_path)
    s = AppointmentStorage(fake_git)
    entry = s.create_entry(
        {
            "title": "Training",
            "start_date": "2026-05-04",
            "end_date": "2026-05-05",
            "type": "training",
            "note": "",
        }
    )
    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()

    with (
        patch("modules.appointments.router.get_storage", return_value=fake_storage),
        patch("modules.appointments.router.get_primary_store", return_value=fake_git),
        patch("modules.appointments.router.get_module_stores", return_value=[fake_git]),
    ):
        resp = client.get(f"/appointments/{entry['id']}/export.ics")
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers["content-type"]
        assert "BEGIN:VCALENDAR" in resp.text


def test_export_ics_with_profile(client, tmp_path):
    from unittest.mock import patch
    from modules.appointments.storage import AppointmentStorage
    from core import settings_store

    profile = settings_store.upsert_appointment_ics_profile(
        {
            "name": "Team",
            "show_as": "busy",
            "all_day": True,
            "subject": "{title}",
            "body": "",
        }
    )

    fake_git = FakeGit(tmp_path)
    s = AppointmentStorage(fake_git)
    entry = s.create_entry(
        {
            "title": "Conference",
            "start_date": "2026-06-10",
            "end_date": "2026-06-11",
            "type": "conference",
            "note": "",
        }
    )
    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()

    with (
        patch("modules.appointments.router.get_storage", return_value=fake_storage),
        patch("modules.appointments.router.get_primary_store", return_value=fake_git),
        patch("modules.appointments.router.get_module_stores", return_value=[fake_git]),
    ):
        resp = client.get(f"/appointments/{entry['id']}/export.ics?profile={profile['id']}")
        assert resp.status_code == 200
        assert "Conference" in resp.text
        cd = resp.headers.get("content-disposition", "")
        assert "team" in cd.lower()


def test_export_ics_profile_not_found(client, tmp_path):
    from unittest.mock import patch
    from modules.appointments.storage import AppointmentStorage

    fake_git = FakeGit(tmp_path)
    s = AppointmentStorage(fake_git)
    entry = s.create_entry(
        {
            "title": "X",
            "start_date": "2026-06-01",
            "end_date": "2026-06-01",
            "type": "other",
            "note": "",
        }
    )
    fake_storage = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()

    with (
        patch("modules.appointments.router.get_storage", return_value=fake_storage),
        patch("modules.appointments.router.get_primary_store", return_value=fake_git),
        patch("modules.appointments.router.get_module_stores", return_value=[fake_git]),
    ):
        resp = client.get(f"/appointments/{entry['id']}/export.ics?profile=nonexistent")
        assert resp.status_code == 404
