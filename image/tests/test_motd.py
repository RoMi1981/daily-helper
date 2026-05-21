"""Tests for MOTD module — storage and router."""

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


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []
        self._pulled = 0

    def _pull(self):
        self._pulled += 1

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def read_committed(self, path: str):
        full = os.path.join(self.local_path, path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def list_committed(self, directory: str) -> list:
        full = os.path.join(self.local_path, directory)
        if not os.path.isdir(full):
            return []
        return os.listdir(full)


@pytest.fixture()
def storage(tmp_path):
    from modules.motd.storage import MotdStorage

    return MotdStorage(FakeGit(tmp_path))


# ── Storage: CRUD ─────────────────────────────────────────────────────────────


def test_list_empty(storage):
    assert storage.list_entries() == []


def test_create_and_list(storage):
    e, _ = storage.create_entry({"text": "Hello world!"})
    assert e["text"] == "Hello world!"
    assert e["active"] is True
    assert "id" in e
    assert "created" in e
    entries = storage.list_entries()
    assert len(entries) == 1
    assert entries[0]["text"] == "Hello world!"


def test_get_entry(storage):
    e, _ = storage.create_entry({"text": "Test"})
    fetched = storage.get_entry(e["id"])
    assert fetched is not None
    assert fetched["text"] == "Test"


def test_get_entry_missing(storage):
    assert storage.get_entry("doesnotexist") is None


def test_update_entry(storage):
    e, _ = storage.create_entry({"text": "Old"})
    updated = storage.update_entry(e["id"], {"text": "New", "active": True})
    assert updated["text"] == "New"


def test_update_entry_active_false(storage):
    e, _ = storage.create_entry({"text": "Msg"})
    updated = storage.update_entry(e["id"], {"text": "Msg", "active": False})
    assert updated["active"] is False


def test_update_entry_missing(storage):
    assert storage.update_entry("ghost", {"text": "x"}) is None


def test_delete_entry(storage):
    e, _ = storage.create_entry({"text": "Bye"})
    assert storage.delete_entry(e["id"]) is True
    assert storage.get_entry(e["id"]) is None


def test_delete_entry_missing(storage):
    assert storage.delete_entry("ghost") is False


def test_commit_messages(storage):
    e, _ = storage.create_entry({"text": "Hello"})
    storage.update_entry(e["id"], {"text": "Hi", "active": True})
    storage.delete_entry(e["id"])
    commits = storage._git._committed
    assert any("add" in c for c in commits)
    assert any("update" in c for c in commits)
    assert any("delete" in c for c in commits)


# ── Storage: list_active ──────────────────────────────────────────────────────


def test_list_active_filters_inactive(storage):
    storage.create_entry({"text": "Active"})
    e2, _ = storage.create_entry({"text": "Will be inactive"})
    storage.update_entry(e2["id"], {"text": "Inactive", "active": False})
    active = storage.list_active()
    assert len(active) == 1
    assert active[0]["text"] == "Active"


# ── Storage: bulk_import ──────────────────────────────────────────────────────


def test_bulk_import_basic(storage):
    created, skipped = storage.bulk_import(["Line one", "Line two", "Line three"])
    assert created == 3
    assert skipped == 0
    assert len(storage.list_entries()) == 3


def test_bulk_import_skips_empty_lines(storage):
    created, skipped = storage.bulk_import(["Hello", "", "  ", "World"])
    assert created == 2
    assert skipped == 0


def test_bulk_import_empty_list(storage):
    result = storage.bulk_import([])
    assert result == (0, 0)


def test_bulk_import_single_commit(storage):
    before = len(storage._git._committed)
    storage.bulk_import(["A", "B", "C"])
    assert len(storage._git._committed) - before == 1


def test_bulk_import_all_active(storage):
    storage.bulk_import(["Msg1", "Msg2"])
    for e in storage.list_entries():
        assert e["active"] is True


def test_bulk_import_skips_duplicates(storage):
    storage.create_entry({"text": "Existing"})
    created, skipped = storage.bulk_import(["Existing", "New one"])
    assert created == 1
    assert skipped == 1


def test_bulk_import_skips_in_batch_duplicates(storage):
    created, skipped = storage.bulk_import(["Same", "same", "SAME", "Other"])
    assert created == 2
    assert skipped == 2


# ── Storage: get_daily ────────────────────────────────────────────────────────


def test_get_daily_none_when_empty(storage):
    assert storage.get_daily() is None


def test_get_daily_returns_entry(storage):
    storage.create_entry({"text": "Daily msg"})
    result = storage.get_daily()
    assert result is not None
    assert result["text"] == "Daily msg"


def test_get_daily_deterministic(storage):
    for i in range(5):
        storage.create_entry({"text": f"Msg {i}"})
    r1 = storage.get_daily(offset=0)
    r2 = storage.get_daily(offset=0)
    assert r1["id"] == r2["id"]


def test_get_daily_offset_changes_result(storage):
    for i in range(5):
        storage.create_entry({"text": f"Msg {i}"})
    results = {storage.get_daily(offset=i)["id"] for i in range(5)}
    assert len(results) > 1


def test_get_daily_skips_inactive(storage):
    storage.create_entry({"text": "Active"})
    e2, _ = storage.create_entry({"text": "Inactive"})
    storage.update_entry(e2["id"], {"text": "Inactive", "active": False})
    for offset in range(10):
        result = storage.get_daily(offset=offset)
        assert result["text"] == "Active"


# ── Router ────────────────────────────────────────────────────────────────────

import main as _main_module


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
def client():
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


@pytest.fixture()
def client_with_storage(tmp_path, isolated_settings):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from modules.motd.storage import MotdStorage

    reset_storage()

    fake_git = FakeGit(tmp_path)
    real_storage = MotdStorage(fake_git)

    with (
        patch("modules.motd.router.get_storage"),
        patch("modules.motd.router.get_primary_store", return_value=fake_git),
        patch("modules.motd.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


def test_list_no_storage(client):
    resp = client.get("/motd")
    assert resp.status_code == 200


def test_list_with_entries(client_with_storage):
    client, storage = client_with_storage
    storage.create_entry({"text": "Good morning!"})
    resp = client.get("/motd")
    assert resp.status_code == 200
    assert b"Good morning!" in resp.content


def test_create_entry(client_with_storage):
    client, storage = client_with_storage
    resp = client.post("/motd/new", data={"text": "Stay positive!"}, follow_redirects=False)
    assert resp.status_code == 303
    assert len(storage.list_entries()) == 1


def test_create_entry_empty_text(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/motd/new", data={"text": "  "})
    assert resp.status_code == 400


def test_edit_form(client_with_storage):
    client, storage = client_with_storage
    e, _ = storage.create_entry({"text": "Edit me"})
    resp = client.get(f"/motd/{e['id']}/edit")
    assert resp.status_code == 200
    assert b"Edit me" in resp.content


def test_edit_form_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/motd/doesnotexist/edit")
    assert resp.status_code == 404


def test_update_entry(client_with_storage):
    client, storage = client_with_storage
    e, _ = storage.create_entry({"text": "Old text"})
    resp = client.post(
        f"/motd/{e['id']}/edit", data={"text": "New text", "active": "on"}, follow_redirects=False
    )
    assert resp.status_code == 303
    updated = storage.get_entry(e["id"])
    assert updated["text"] == "New text"


def test_delete_entry_router(client_with_storage):
    client, storage = client_with_storage
    e, _ = storage.create_entry({"text": "Delete me"})
    resp = client.post(f"/motd/{e['id']}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert storage.get_entry(e["id"]) is None


def test_import_form(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/motd/import")
    assert resp.status_code == 200


def test_import_textarea(client_with_storage):
    client, storage = client_with_storage
    resp = client.post(
        "/motd/import", data={"text": "Line one\nLine two\nLine three"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert len(storage.list_entries()) == 3


def test_import_skips_empty_lines(client_with_storage):
    client, storage = client_with_storage
    resp = client.post("/motd/import", data={"text": "Hello\n\nWorld\n  "}, follow_redirects=False)
    assert resp.status_code == 303
    assert len(storage.list_entries()) == 2


def test_next_endpoint(client_with_storage):
    client, storage = client_with_storage
    storage.create_entry({"text": "First"})
    storage.create_entry({"text": "Second"})
    resp = client.post("/motd/next")
    assert resp.status_code == 200
