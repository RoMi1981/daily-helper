"""Router integration tests for the Tasks module."""

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
        self._committed = []

    def _pull(self): pass

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
    from modules.tasks.storage import TaskStorage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    real_storage = TaskStorage(fake_git)

    with patch("modules.tasks.router.get_storage"), \
         patch("modules.tasks.router.get_primary_store", return_value=fake_git), \
         patch("modules.tasks.router.get_module_stores", return_value=[fake_git]):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


# ── List ───────────────────────────────────────────────────────────────────

def test_list_no_storage(client):
    resp = client.get("/tasks")
    assert resp.status_code == 200


def test_list_with_tasks(client_with_storage):
    client, storage = client_with_storage
    storage.create_task({"title": "Write docs", "priority": "high"})
    storage.create_task({"title": "Done task"})
    storage.toggle_done(storage.list_tasks()[1]["id"])
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert b"Write docs" in resp.content


# ── Create ─────────────────────────────────────────────────────────────────

def test_create_task(client_with_storage):
    client, storage = client_with_storage
    resp = client.post("/tasks", data={
        "title": "New task",
        "priority": "high",
        "due_date": "2026-05-01",
        "recurring": "none",
    }, follow_redirects=False)
    assert resp.status_code == 303
    tasks = storage.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "New task"


def test_create_task_empty_title(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/tasks", data={"title": "  "})
    assert resp.status_code == 400


def test_create_task_no_storage(client):
    resp = client.post("/tasks", data={"title": "Test"})
    assert resp.status_code in (400, 503)


# ── Edit form ──────────────────────────────────────────────────────────────

def test_edit_form(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_task({"title": "Edit me", "priority": "low"})
    resp = client.get(f"/tasks/{t['id']}/edit")
    assert resp.status_code == 200
    assert b"Edit me" in resp.content


def test_edit_form_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/tasks/doesnotexist/edit")
    assert resp.status_code == 404


def test_edit_form_no_storage(client):
    resp = client.get("/tasks/abc/edit")
    assert resp.status_code in (404, 503)


# ── Update ─────────────────────────────────────────────────────────────────

def test_update_task(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_task({"title": "Before"})
    resp = client.post(f"/tasks/{t['id']}/edit", data={
        "title": "After",
        "priority": "high",
        "due_date": "",
        "recurring": "none",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert storage.get_task(t["id"])["title"] == "After"


def test_update_task_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/tasks/ghost/edit", data={
        "title": "x", "priority": "low", "due_date": "", "recurring": "none"
    })
    assert resp.status_code == 404


def test_update_task_no_storage(client):
    resp = client.post("/tasks/abc/edit", data={
        "title": "x", "priority": "low", "due_date": "", "recurring": "none"
    })
    assert resp.status_code in (404, 503)


# ── Toggle ─────────────────────────────────────────────────────────────────

def test_toggle_task(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_task({"title": "Toggle me"})
    resp = client.post(f"/tasks/{t['id']}/toggle")
    assert resp.status_code == 200
    assert storage.get_task(t["id"])["done"] is True


def test_toggle_task_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/tasks/ghost/toggle")
    assert resp.status_code == 404


# ── Delete ─────────────────────────────────────────────────────────────────

def test_delete_task(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_task({"title": "Delete me"})
    resp = client.post(f"/tasks/{t['id']}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert storage.get_task(t["id"]) is None


def test_delete_task_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/tasks/ghost/delete")
    assert resp.status_code == 404


def test_delete_task_no_storage(client):
    resp = client.post("/tasks/abc/delete")
    assert resp.status_code in (404, 503)
