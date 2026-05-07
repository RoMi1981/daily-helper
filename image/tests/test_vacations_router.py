"""Router integration tests for the Vacations module."""

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


@pytest.fixture()
def client_with_storage(tmp_path, isolated_settings):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from modules.vacations.storage import VacationStorage

    reset_storage()

    fake_git = FakeGit(tmp_path)
    real_storage = VacationStorage(fake_git)

    with (
        patch("modules.vacations.router.get_storage"),
        patch("modules.vacations.router.get_primary_store", return_value=fake_git),
        patch("modules.vacations.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


# ── List ───────────────────────────────────────────────────────────────────


def test_list_no_storage(client):
    resp = client.get("/vacations")
    assert resp.status_code == 200


def test_list_with_entries(client_with_storage):
    client, storage = client_with_storage
    storage.create_entry({"start_date": "2026-07-01", "end_date": "2026-07-10"})
    resp = client.get("/vacations")
    assert resp.status_code == 200
    assert b"2026-07-01" in resp.content


def test_list_with_year_param(client_with_storage):
    client, storage = client_with_storage
    resp = client.get("/vacations?year=2025")
    assert resp.status_code == 200


# ── Calendar ───────────────────────────────────────────────────────────────


def test_calendar_no_storage(client):
    resp = client.get("/vacations/calendar")
    assert resp.status_code == 200


def test_calendar_with_storage(client_with_storage):
    client, storage = client_with_storage
    storage.create_entry(
        {"start_date": "2026-04-20", "end_date": "2026-04-24", "status": "approved"}
    )
    resp = client.get("/vacations/calendar?year=2026&month=4")
    assert resp.status_code == 200


def test_calendar_defaults_to_today(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/vacations/calendar")
    assert resp.status_code == 200


# ── Create ─────────────────────────────────────────────────────────────────


def test_create_entry(client_with_storage):
    client, storage = client_with_storage
    resp = client.post(
        "/vacations",
        data={
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "note": "Summer",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    entries = storage.list_entries()
    assert len(entries) == 1
    assert entries[0]["note"] == "Summer"


def test_create_entry_missing_dates(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/vacations", data={"start_date": "", "end_date": ""})
    assert resp.status_code in (400, 422)


def test_create_entry_no_storage(client):
    resp = client.post("/vacations", data={"start_date": "2026-08-01", "end_date": "2026-08-10"})
    assert resp.status_code in (400, 503)


# ── Edit form ──────────────────────────────────────────────────────────────


def test_edit_form(client_with_storage):
    client, storage = client_with_storage
    e = storage.create_entry({"start_date": "2026-06-01", "end_date": "2026-06-05"})
    resp = client.get(f"/vacations/{e['id']}/edit")
    assert resp.status_code == 200
    assert b"2026-06-01" in resp.content


def test_edit_form_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/vacations/ghost/edit")
    assert resp.status_code == 404


# ── Update ─────────────────────────────────────────────────────────────────


def test_update_entry(client_with_storage):
    client, storage = client_with_storage
    e = storage.create_entry({"start_date": "2026-06-01", "end_date": "2026-06-05"})
    resp = client.post(
        f"/vacations/{e['id']}/edit",
        data={
            "start_date": "2026-06-02",
            "end_date": "2026-06-06",
            "note": "Updated",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    updated = storage.get_entry(e["id"])
    assert updated["start_date"] == "2026-06-02"
    assert updated["note"] == "Updated"


def test_update_entry_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post(
        "/vacations/ghost/edit",
        data={"start_date": "2026-06-01", "end_date": "2026-06-05", "note": ""},
    )
    assert resp.status_code == 404


# ── Status ─────────────────────────────────────────────────────────────────


def test_update_status(client_with_storage):
    client, storage = client_with_storage
    e = storage.create_entry(
        {"start_date": "2026-05-01", "end_date": "2026-05-05", "status": "planned"}
    )
    resp = client.post(f"/vacations/{e['id']}/status", data={"status": "approved"})
    assert resp.status_code == 200
    assert storage.get_entry(e["id"])["status"] == "approved"


def test_update_status_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/vacations/ghost/status", data={"status": "approved"})
    assert resp.status_code == 404


# ── Delete ─────────────────────────────────────────────────────────────────


def test_delete_entry(client_with_storage):
    client, storage = client_with_storage
    e = storage.create_entry({"start_date": "2026-09-01", "end_date": "2026-09-05"})
    resp = client.post(f"/vacations/{e['id']}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert storage.get_entry(e["id"]) is None


def test_delete_entry_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/vacations/ghost/delete")
    assert resp.status_code == 404


# ── CSV export ─────────────────────────────────────────────────────────────


def test_csv_export(client_with_storage):
    client, storage = client_with_storage
    storage.create_entry(
        {"start_date": "2026-07-01", "end_date": "2026-07-05", "status": "approved"}
    )
    resp = client.get("/vacations/export.csv?year=2026")
    assert resp.status_code == 200
    assert b"start_date" in resp.content
    assert b"2026-07-01" in resp.content


def test_csv_export_empty(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/vacations/export.csv?year=2025")
    assert resp.status_code == 200
    assert b"start_date" in resp.content  # header only


# ── ICS export ─────────────────────────────────────────────────────────────


def test_ics_export_fallback(client_with_storage):
    client, storage = client_with_storage
    e = storage.create_entry(
        {"start_date": "2026-07-01", "end_date": "2026-07-05", "note": "Holiday"}
    )
    resp = client.get(f"/vacations/{e['id']}/export.ics")
    assert resp.status_code == 200
    assert b"BEGIN:VCALENDAR" in resp.content
    assert b"DTSTART" in resp.content


def test_ics_export_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/vacations/ghost/export.ics")
    assert resp.status_code == 404


def test_ics_export_no_storage(client):
    resp = client.get("/vacations/abc/export.ics")
    assert resp.status_code in (404, 503)


# ── Mail preview ────────────────────────────────────────────────────────────


def test_mail_preview_no_storage(client):
    resp = client.get("/vacations/abc/mail")
    assert resp.status_code in (404, 503)


def test_mail_preview_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/vacations/ghost/mail")
    assert resp.status_code == 404


def test_mail_preview_no_template(client_with_storage):
    """Without mail template config, preview still renders (empty fields)."""
    client, storage = client_with_storage
    e = storage.create_entry({"start_date": "2026-07-01", "end_date": "2026-07-10"})
    resp = client.get(f"/vacations/{e['id']}/mail")
    assert resp.status_code == 200


def test_mail_preview_with_template(tmp_path, isolated_settings):
    """Mail preview renders placeholders from configured template."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from core import settings_store
    from modules.vacations.storage import VacationStorage

    reset_storage()
    cfg = settings_store.load()
    cfg["vacation_mail_to"] = "manager@example.com"
    cfg["vacation_mail_subject"] = "Vacation {{from}} to {{to}}"
    cfg["vacation_mail_body"] = "I'll be off from {{from}} to {{to}} ({{working_days}} days)"
    settings_store.save(cfg)

    fake_git = FakeGit(tmp_path)
    real_storage = VacationStorage(fake_git)
    e = real_storage.create_entry({"start_date": "2026-08-01", "end_date": "2026-08-14"})

    with (
        patch("modules.vacations.router.get_storage"),
        patch("modules.vacations.router.get_primary_store", return_value=fake_git),
        patch("modules.vacations.router.get_module_stores", return_value=[fake_git]),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get(f"/vacations/{e['id']}/mail")

    assert resp.status_code == 200
    assert b"manager@example.com" in resp.content
    assert b"2026-08-01" in resp.content
    assert b"2026-08-14" in resp.content


# ── EML download ────────────────────────────────────────────────────────────


def test_eml_no_storage(client):
    resp = client.get("/vacations/abc/mail.eml")
    assert resp.status_code in (404, 503)


def test_eml_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/vacations/ghost/mail.eml")
    assert resp.status_code == 404


def test_eml_download(tmp_path, isolated_settings):
    """EML download produces valid RFC 2822 content with placeholders filled."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from core import settings_store
    from modules.vacations.storage import VacationStorage

    reset_storage()
    cfg = settings_store.load()
    cfg["vacation_mail_to"] = "boss@example.com"
    cfg["vacation_mail_cc"] = "hr@example.com"
    cfg["vacation_mail_subject"] = "Vacation {{from}} – {{to}}"
    cfg["vacation_mail_body"] = "Off from {{from}} to {{to}}, {{working_days}} working days."
    settings_store.save(cfg)

    fake_git = FakeGit(tmp_path)
    real_storage = VacationStorage(fake_git)
    e = real_storage.create_entry({"start_date": "2026-09-01", "end_date": "2026-09-05"})

    with (
        patch("modules.vacations.router.get_storage"),
        patch("modules.vacations.router.get_primary_store", return_value=fake_git),
        patch("modules.vacations.router.get_module_stores", return_value=[fake_git]),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get(f"/vacations/{e['id']}/mail.eml")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("message/rfc822")
    assert b"boss@example.com" in resp.content
    assert b"2026-09-01" in resp.content
    assert b"2026-09-05" in resp.content


# ── _days_until_next_vacation unit tests ──────────────────────────────────


def test_days_until_returns_none_when_no_future_entries():
    from datetime import date
    from modules.vacations.router import _days_until_next_vacation

    entries = [{"start_date": "2020-01-01", "end_date": "2020-01-05"}]
    days, entry = _days_until_next_vacation(entries, "BY", date(2025, 6, 1))
    assert days is None
    assert entry is None


def test_days_until_picks_nearest_future_entry():
    from datetime import date
    from modules.vacations.router import _days_until_next_vacation

    entries = [
        {"start_date": "2099-12-01", "end_date": "2099-12-05"},
        {"start_date": "2099-06-01", "end_date": "2099-06-05"},
    ]
    days, entry = _days_until_next_vacation(entries, "BY", date(2025, 1, 1))
    assert entry["start_date"] == "2099-06-01"


def test_days_until_zero_when_starts_today():
    from datetime import date
    from modules.vacations.router import _days_until_next_vacation

    today = date(2025, 6, 16)  # Monday
    entries = [{"start_date": "2025-06-16", "end_date": "2025-06-20"}]
    days, entry = _days_until_next_vacation(entries, "BY", today)
    assert days == 0


def test_days_until_counts_working_days():
    from datetime import date
    from modules.vacations.router import _days_until_next_vacation

    # Monday 2025-06-16, vacation starts Wednesday 2025-06-18 → 2 working days (Mon + Tue)
    today = date(2025, 6, 16)
    entries = [{"start_date": "2025-06-18", "end_date": "2025-06-20"}]
    days, entry = _days_until_next_vacation(entries, "BY", today)
    assert days == 2


# ── Vacation countdown ─────────────────────────────────────────────────────


def test_countdown_not_shown_without_future_vacation(client_with_storage):
    client, storage = client_with_storage
    # Only a past vacation — no countdown expected
    storage.create_entry({"start_date": "2020-01-01", "end_date": "2020-01-05"})
    resp = client.get("/vacations")
    assert resp.status_code == 200
    assert b"working day" not in resp.content
    assert b"Vacation starts tomorrow" not in resp.content


def test_countdown_shown_for_future_vacation(client_with_storage):
    client, storage = client_with_storage
    storage.create_entry({"start_date": "2099-06-01", "end_date": "2099-06-10"})
    resp = client.get("/vacations")
    assert resp.status_code == 200
    assert b"working day" in resp.content or b"Vacation starts tomorrow" in resp.content


def test_countdown_shows_nearest_vacation_date(client_with_storage):
    client, storage = client_with_storage
    storage.create_entry({"start_date": "2099-12-01", "end_date": "2099-12-05"})
    storage.create_entry({"start_date": "2099-06-01", "end_date": "2099-06-05"})
    resp = client.get("/vacations")
    assert b"2099-06-01" in resp.content


def test_countdown_vacation_tomorrow(client_with_storage):
    from datetime import date, timedelta

    client, storage = client_with_storage
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    storage.create_entry({"start_date": tomorrow, "end_date": tomorrow})
    resp = client.get("/vacations")
    assert resp.status_code == 200
    assert b"tomorrow" in resp.content
