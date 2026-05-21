"""Router integration tests for the Ticket Templates module."""

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
os.environ["DATA_DIR"] = "/tmp/daily-helper-test-ticket-templates"

import main as _main_module


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def get_file_history(self, path: str) -> list:
        return []

    def get_file_diff(self, sha: str, path: str):
        return None


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
    from modules.ticket_templates.storage import TicketTemplateStorage

    reset_storage()

    fake_git = FakeGit(tmp_path)
    real_storage = TicketTemplateStorage(fake_git)

    with (
        patch("modules.ticket_templates.router.get_storage"),
        patch("modules.ticket_templates.router.get_primary_store", return_value=fake_git),
        patch("modules.ticket_templates.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


# ── List ───────────────────────────────────────────────────────────────────


def test_list_no_storage(client):
    resp = client.get("/ticket-templates")
    assert resp.status_code == 200


def test_list_with_templates(client_with_storage):
    client, storage = client_with_storage
    storage.create_template({"name": "Bug Report", "description": "For bugs", "body": "## Steps"})
    storage.create_template({"name": "Feature Request", "description": "For features", "body": ""})
    resp = client.get("/ticket-templates")
    assert resp.status_code == 200
    assert b"Bug Report" in resp.content
    assert b"Feature Request" in resp.content


def test_list_deduplicates_across_storages(tmp_path, isolated_settings):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from modules.ticket_templates.storage import TicketTemplateStorage

    reset_storage()
    fake_git1 = FakeGit(tmp_path / "repo1")
    fake_git2 = FakeGit(tmp_path / "repo2")
    storage1 = TicketTemplateStorage(fake_git1)
    storage2 = TicketTemplateStorage(fake_git2)

    t = storage1.create_template({"name": "SharedDedupTemplate", "description": "", "body": ""})
    # Manually copy the same file to repo2 to simulate a duplicate id
    import shutil

    (tmp_path / "repo2" / "ticket_templates").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        tmp_path / "repo1" / "ticket_templates" / f"{t['id']}.yaml",
        tmp_path / "repo2" / "ticket_templates" / f"{t['id']}.yaml",
    )

    with (
        patch("modules.ticket_templates.router.get_storage"),
        patch("modules.ticket_templates.router.get_primary_store", return_value=fake_git1),
        patch(
            "modules.ticket_templates.router.get_module_stores", return_value=[fake_git1, fake_git2]
        ),
    ):
        # Capture the templates list passed to the template context via a side-effectful approach:
        # easier: just assert only one edit-link for this id appears in the rendered HTML
        resp = TestClient(_main_module.app, raise_server_exceptions=False).get("/ticket-templates")
    assert resp.status_code == 200
    # The template id appears once per row (in the edit/delete/history links).
    # If dedup works, there is exactly one row, so the id appears exactly 3 times (edit/history/delete).
    # If dedup fails, there would be 6 occurrences.
    id_count = resp.content.count(t["id"].encode())
    assert id_count == 3, (
        f"Expected 3 links for one template, got {id_count} (dedup may have failed)"
    )


# ── New template form ──────────────────────────────────────────────────────


def test_new_form(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/ticket-templates/new")
    assert resp.status_code == 200


# ── Create ─────────────────────────────────────────────────────────────────


def test_create_template(client_with_storage):
    client, storage = client_with_storage
    resp = client.post(
        "/ticket-templates/new",
        data={
            "name": "New Template",
            "description": "A description",
            "body": "## Body",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ticket-templates?saved=1"
    templates = storage.list_templates()
    assert len(templates) == 1
    assert templates[0]["name"] == "New Template"


def test_create_template_empty_name(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/ticket-templates/new", data={"name": "  ", "description": "", "body": ""})
    assert resp.status_code == 400


def test_create_template_missing_name_field(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/ticket-templates/new", data={"description": "no name"})
    assert resp.status_code == 422


def test_create_template_no_storage(client):
    resp = client.post(
        "/ticket-templates/new", data={"name": "Test", "description": "", "body": ""}
    )
    assert resp.status_code in (400, 503)


# ── Edit form ──────────────────────────────────────────────────────────────


def test_edit_form(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_template({"name": "Edit Me", "description": "desc", "body": "body"})
    resp = client.get(f"/ticket-templates/{t['id']}/edit")
    assert resp.status_code == 200
    assert b"Edit Me" in resp.content


def test_edit_form_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/ticket-templates/doesnotexist/edit")
    assert resp.status_code == 404


# ── Update ─────────────────────────────────────────────────────────────────


def test_update_template(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_template({"name": "Before", "description": "", "body": ""})
    resp = client.post(
        f"/ticket-templates/{t['id']}/edit",
        data={
            "name": "After",
            "description": "new desc",
            "body": "new body",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ticket-templates?saved=1"
    updated = storage.get_template(t["id"])
    assert updated["name"] == "After"
    assert updated["description"] == "new desc"


def test_update_template_empty_name(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_template({"name": "Valid", "description": "", "body": ""})
    resp = client.post(
        f"/ticket-templates/{t['id']}/edit",
        data={
            "name": "  ",
            "description": "",
            "body": "",
        },
    )
    assert resp.status_code == 400


def test_update_template_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post(
        "/ticket-templates/ghost/edit", data={"name": "x", "description": "", "body": ""}
    )
    assert resp.status_code == 404


# ── Delete ─────────────────────────────────────────────────────────────────


def test_delete_template(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_template({"name": "Delete Me", "description": "", "body": ""})
    resp = client.post(f"/ticket-templates/{t['id']}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert storage.get_template(t["id"]) is None


def test_delete_template_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/ticket-templates/ghost/delete")
    assert resp.status_code == 404


# ── History ────────────────────────────────────────────────────────────────


def test_history(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_template({"name": "History Test", "description": "", "body": ""})
    resp = client.get(f"/ticket-templates/{t['id']}/history")
    assert resp.status_code == 200
    assert b"History Test" in resp.content


def test_history_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/ticket-templates/ghost/history")
    assert resp.status_code == 404


def test_history_with_sha(client_with_storage):
    client, storage = client_with_storage
    t = storage.create_template({"name": "Diff Test", "description": "", "body": ""})
    resp = client.get(f"/ticket-templates/{t['id']}/history?sha=abc123")
    assert resp.status_code == 200
