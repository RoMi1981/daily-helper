"""Tests for Runbooks module — storage and router."""

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

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)


@pytest.fixture()
def rb_storage(tmp_path):
    from modules.runbooks.storage import RunbookStorage

    return RunbookStorage(FakeGit(tmp_path))


# ── Storage tests ──────────────────────────────────────────────────────────


def test_list_empty(rb_storage):
    assert rb_storage.list_runbooks() == []


def test_create_and_list(rb_storage):
    rb = rb_storage.create_runbook({"title": "Deploy App", "description": "Steps to deploy"})
    assert rb["title"] == "Deploy App"
    assert rb["description"] == "Steps to deploy"
    assert rb["steps"] == []
    assert "id" in rb
    assert "created" in rb
    listed = rb_storage.list_runbooks()
    assert len(listed) == 1


def test_create_with_steps(rb_storage):
    steps = [
        {"title": "Check health", "body": "curl /health"},
        {"title": "Deploy", "body": "kubectl apply"},
    ]
    rb = rb_storage.create_runbook({"title": "K8s Deploy", "steps": steps})
    assert len(rb["steps"]) == 2
    assert rb["steps"][0]["title"] == "Check health"
    assert rb["steps"][0]["body"] == "curl /health"


def test_steps_filter_empty_title(rb_storage):
    steps = [
        {"title": "Valid step", "body": "do something"},
        {"title": "", "body": "body without title"},
        {"title": "  ", "body": "whitespace title"},
    ]
    rb = rb_storage.create_runbook({"title": "Test", "steps": steps})
    assert len(rb["steps"]) == 1
    assert rb["steps"][0]["title"] == "Valid step"


def test_get_runbook(rb_storage):
    rb = rb_storage.create_runbook({"title": "Rollback"})
    fetched = rb_storage.get_runbook(rb["id"])
    assert fetched is not None
    assert fetched["title"] == "Rollback"


def test_get_runbook_missing(rb_storage):
    assert rb_storage.get_runbook("doesnotexist") is None


def test_update_runbook(rb_storage):
    rb = rb_storage.create_runbook({"title": "Old Title"})
    updated = rb_storage.update_runbook(
        rb["id"],
        {
            "title": "New Title",
            "description": "Updated desc",
            "steps": [{"title": "Step 1", "body": "do it"}],
        },
    )
    assert updated["title"] == "New Title"
    assert updated["description"] == "Updated desc"
    assert len(updated["steps"]) == 1


def test_update_runbook_missing(rb_storage):
    assert rb_storage.update_runbook("ghost", {"title": "x"}) is None


def test_delete_runbook(rb_storage):
    rb = rb_storage.create_runbook({"title": "Temp"})
    assert rb_storage.delete_runbook(rb["id"]) is True
    assert rb_storage.get_runbook(rb["id"]) is None


def test_delete_runbook_missing(rb_storage):
    assert rb_storage.delete_runbook("ghost") is False


def test_search_by_title(rb_storage):
    rb_storage.create_runbook({"title": "Deploy Application"})
    rb_storage.create_runbook({"title": "Rollback Procedure"})
    results = rb_storage.list_runbooks(query="deploy")
    assert len(results) == 1
    assert results[0]["title"] == "Deploy Application"


def test_search_by_description(rb_storage):
    rb_storage.create_runbook({"title": "Runbook A", "description": "kubernetes steps"})
    rb_storage.create_runbook({"title": "Runbook B", "description": "docker commands"})
    results = rb_storage.list_runbooks(query="kubernetes")
    assert len(results) == 1


def test_list_sorted_by_title(rb_storage):
    rb_storage.create_runbook({"title": "Zebra"})
    rb_storage.create_runbook({"title": "Alpha"})
    rb_storage.create_runbook({"title": "Mango"})
    results = rb_storage.list_runbooks()
    titles = [r["title"] for r in results]
    assert titles == sorted(titles, key=str.lower)


def test_commit_on_create(rb_storage):
    rb_storage.create_runbook({"title": "Test"})
    assert any("add" in m for m in rb_storage._git._committed)


def test_commit_on_update(rb_storage):
    rb = rb_storage.create_runbook({"title": "Test"})
    rb_storage._git._committed.clear()
    rb_storage.update_runbook(rb["id"], {"title": "Updated"})
    assert any("update" in m for m in rb_storage._git._committed)


def test_commit_on_delete(rb_storage):
    rb = rb_storage.create_runbook({"title": "Test"})
    rb_storage._git._committed.clear()
    rb_storage.delete_runbook(rb["id"])
    assert any("delete" in m for m in rb_storage._git._committed)


# ── Router tests ───────────────────────────────────────────────────────────

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

    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.runbooks.storage import RunbookStorage

    real_storage = RunbookStorage(fake_git)

    with (
        patch("modules.runbooks.router.get_storage"),
        patch("modules.runbooks.router.get_primary_store", return_value=fake_git),
        patch("modules.runbooks.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


def test_list_no_storage(client):
    resp = client.get("/runbooks")
    assert resp.status_code == 200
    assert b"No repository configured" in resp.content


def test_list_with_storage(client_with_storage):
    client, storage = client_with_storage
    storage.create_runbook({"title": "My Runbook"})
    resp = client.get("/runbooks")
    assert resp.status_code == 200
    assert b"My Runbook" in resp.content


def test_new_form(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/runbooks/new")
    assert resp.status_code == 200
    assert b"New Runbook" in resp.content


def test_create_runbook(client_with_storage):
    client, storage = client_with_storage
    resp = client.post(
        "/runbooks/new",
        data={
            "title": "Test Runbook",
            "description": "A test",
            "step_title_0": "First step",
            "step_body_0": "do this",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    runbooks = storage.list_runbooks()
    assert len(runbooks) == 1
    assert runbooks[0]["title"] == "Test Runbook"
    assert len(runbooks[0]["steps"]) == 1


def test_create_runbook_empty_title(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/runbooks/new", data={"title": "  ", "description": ""})
    assert resp.status_code == 400


def test_view_runbook(client_with_storage):
    client, storage = client_with_storage
    rb = storage.create_runbook(
        {"title": "View Me", "steps": [{"title": "Step 1", "body": "body"}]}
    )
    resp = client.get(f"/runbooks/{rb['id']}")
    assert resp.status_code == 200
    assert b"View Me" in resp.content
    assert b"Step 1" in resp.content


def test_view_runbook_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/runbooks/doesnotexist")
    assert resp.status_code == 404


def test_edit_form(client_with_storage):
    client, storage = client_with_storage
    rb = storage.create_runbook({"title": "Edit Me"})
    resp = client.get(f"/runbooks/{rb['id']}/edit")
    assert resp.status_code == 200
    assert b"Edit Runbook" in resp.content


def test_update_runbook(client_with_storage):
    client, storage = client_with_storage
    rb = storage.create_runbook({"title": "Before"})
    resp = client.post(
        f"/runbooks/{rb['id']}/edit",
        data={
            "title": "After",
            "description": "",
            "step_title_0": "Updated step",
            "step_body_0": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    updated = storage.get_runbook(rb["id"])
    assert updated["title"] == "After"


def test_delete_runbook(client_with_storage):
    client, storage = client_with_storage
    rb = storage.create_runbook({"title": "Delete Me"})
    resp = client.post(f"/runbooks/{rb['id']}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert storage.get_runbook(rb["id"]) is None


def test_search_runbooks(client_with_storage):
    client, storage = client_with_storage
    storage.create_runbook({"title": "Deploy App"})
    storage.create_runbook({"title": "Rollback"})
    resp = client.get("/runbooks?q=deploy")
    assert resp.status_code == 200
    assert b"Deploy App" in resp.content
    assert b"Rollback" not in resp.content
