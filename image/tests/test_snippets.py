"""Tests for Snippets module — storage and router."""

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
def sn_storage(tmp_path):
    from modules.snippets.storage import SnippetStorage

    return SnippetStorage(FakeGit(tmp_path))


# ── Storage tests ──────────────────────────────────────────────────────────


def test_list_empty(sn_storage):
    assert sn_storage.list_snippets() == []


def test_create_and_list(sn_storage):
    sn = sn_storage.create_snippet(
        {"title": "Docker cleanup", "description": "Remove dangling images"}
    )
    assert sn["title"] == "Docker cleanup"
    assert sn["description"] == "Remove dangling images"
    assert sn["steps"] == []
    assert "id" in sn
    assert "created" in sn
    assert len(sn_storage.list_snippets()) == 1


def test_create_with_steps(sn_storage):
    steps = [
        {"description": "List containers", "command": "docker ps -a"},
        {"description": "Remove stopped", "command": "docker container prune -f"},
    ]
    sn = sn_storage.create_snippet({"title": "Docker", "steps": steps})
    assert len(sn["steps"]) == 2
    assert sn["steps"][0]["description"] == "List containers"
    assert sn["steps"][0]["command"] == "docker ps -a"


def test_steps_filter_empty_command(sn_storage):
    """Steps without a command are dropped."""
    steps = [
        {"description": "Valid", "command": "echo hello"},
        {"description": "No command", "command": ""},
        {"description": "Whitespace", "command": "   "},
    ]
    sn = sn_storage.create_snippet({"title": "Test", "steps": steps})
    assert len(sn["steps"]) == 1
    assert sn["steps"][0]["command"] == "echo hello"


def test_get_snippet(sn_storage):
    sn = sn_storage.create_snippet({"title": "SSH tunnel"})
    fetched = sn_storage.get_snippet(sn["id"])
    assert fetched is not None
    assert fetched["title"] == "SSH tunnel"


def test_get_snippet_missing(sn_storage):
    assert sn_storage.get_snippet("doesnotexist") is None


def test_update_snippet(sn_storage):
    sn = sn_storage.create_snippet({"title": "Old"})
    updated = sn_storage.update_snippet(
        sn["id"],
        {
            "title": "New Title",
            "description": "Updated",
            "steps": [{"description": "Check", "command": "ping -c1 8.8.8.8"}],
        },
    )
    assert updated["title"] == "New Title"
    assert updated["description"] == "Updated"
    assert len(updated["steps"]) == 1
    assert updated["steps"][0]["command"] == "ping -c1 8.8.8.8"


def test_update_snippet_missing(sn_storage):
    assert sn_storage.update_snippet("ghost", {"title": "x"}) is None


def test_delete_snippet(sn_storage):
    sn = sn_storage.create_snippet({"title": "Temp"})
    assert sn_storage.delete_snippet(sn["id"]) is True
    assert sn_storage.get_snippet(sn["id"]) is None


def test_delete_snippet_missing(sn_storage):
    assert sn_storage.delete_snippet("ghost") is False


def test_search_by_title(sn_storage):
    sn_storage.create_snippet({"title": "Git rebase tips"})
    sn_storage.create_snippet({"title": "Docker compose"})
    results = sn_storage.list_snippets(query="git")
    assert len(results) == 1
    assert results[0]["title"] == "Git rebase tips"


def test_search_by_description(sn_storage):
    sn_storage.create_snippet({"title": "A", "description": "kubernetes cleanup"})
    sn_storage.create_snippet({"title": "B", "description": "docker stuff"})
    assert len(sn_storage.list_snippets(query="kubernetes")) == 1


def test_search_by_step_command(sn_storage):
    """Search should match commands inside steps."""
    sn_storage.create_snippet(
        {"title": "Misc", "steps": [{"description": "", "command": "kubectl get pods"}]}
    )
    sn_storage.create_snippet({"title": "Other"})
    results = sn_storage.list_snippets(query="kubectl")
    assert len(results) == 1
    assert results[0]["title"] == "Misc"


def test_search_by_step_description(sn_storage):
    """Search should match step descriptions."""
    sn_storage.create_snippet(
        {
            "title": "Net",
            "steps": [{"description": "ping the gateway", "command": "ping -c1 192.168.1.1"}],
        }
    )
    sn_storage.create_snippet({"title": "Other"})
    assert len(sn_storage.list_snippets(query="gateway")) == 1


def test_list_sorted_by_title(sn_storage):
    sn_storage.create_snippet({"title": "Zebra"})
    sn_storage.create_snippet({"title": "Alpha"})
    sn_storage.create_snippet({"title": "Mango"})
    titles = [s["title"] for s in sn_storage.list_snippets()]
    assert titles == sorted(titles, key=str.lower)


def test_commit_on_create(sn_storage):
    sn_storage.create_snippet({"title": "Test"})
    assert any("add" in m for m in sn_storage._git._committed)


def test_commit_on_update(sn_storage):
    sn = sn_storage.create_snippet({"title": "Test"})
    sn_storage._git._committed.clear()
    sn_storage.update_snippet(sn["id"], {"title": "Updated"})
    assert any("update" in m for m in sn_storage._git._committed)


def test_commit_on_delete(sn_storage):
    sn = sn_storage.create_snippet({"title": "Test"})
    sn_storage._git._committed.clear()
    sn_storage.delete_snippet(sn["id"])
    assert any("delete" in m for m in sn_storage._git._committed)


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
    from modules.snippets.storage import SnippetStorage

    real_storage = SnippetStorage(fake_git)

    with (
        patch("modules.snippets.router.get_storage"),
        patch("modules.snippets.router.get_primary_store", return_value=fake_git),
        patch("modules.snippets.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


def test_list_no_storage(client):
    resp = client.get("/snippets")
    assert resp.status_code == 200
    assert b"No repository configured" in resp.content


def test_list_with_storage(client_with_storage):
    client, storage = client_with_storage
    storage.create_snippet({"title": "My Snippet"})
    resp = client.get("/snippets")
    assert resp.status_code == 200
    assert b"My Snippet" in resp.content


def test_new_form(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/snippets/new")
    assert resp.status_code == 200
    assert b"New Snippet" in resp.content


def test_create_snippet(client_with_storage):
    client, storage = client_with_storage
    resp = client.post(
        "/snippets/new",
        data={
            "title": "Test Snippet",
            "description": "A test",
            "step_desc_0": "List files",
            "step_cmd_0": "ls -la",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    snippets = storage.list_snippets()
    assert len(snippets) == 1
    assert snippets[0]["title"] == "Test Snippet"
    assert len(snippets[0]["steps"]) == 1
    assert snippets[0]["steps"][0]["command"] == "ls -la"


def test_create_snippet_empty_title(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/snippets/new", data={"title": "  ", "description": ""})
    assert resp.status_code == 400


def test_create_snippet_no_storage(client):
    resp = client.post("/snippets/new", data={"title": "X"})
    assert resp.status_code == 503


def test_view_snippet(client_with_storage):
    client, storage = client_with_storage
    sn = storage.create_snippet(
        {
            "title": "View Me",
            "steps": [
                {"description": "check", "command": "echo hello"},
            ],
        }
    )
    resp = client.get(f"/snippets/{sn['id']}")
    assert resp.status_code == 200
    assert b"View Me" in resp.content
    assert b"echo hello" in resp.content


def test_view_snippet_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/snippets/doesnotexist")
    assert resp.status_code == 404


def test_edit_form(client_with_storage):
    client, storage = client_with_storage
    sn = storage.create_snippet({"title": "Edit Me"})
    resp = client.get(f"/snippets/{sn['id']}/edit")
    assert resp.status_code == 200
    assert b"Edit Snippet" in resp.content


def test_update_snippet(client_with_storage):
    client, storage = client_with_storage
    sn = storage.create_snippet({"title": "Before"})
    resp = client.post(
        f"/snippets/{sn['id']}/edit",
        data={
            "title": "After",
            "description": "",
            "step_desc_0": "",
            "step_cmd_0": "new-cmd",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    updated = storage.get_snippet(sn["id"])
    assert updated["title"] == "After"
    assert updated["steps"][0]["command"] == "new-cmd"


def test_update_snippet_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/snippets/ghost/edit", data={"title": "x"}, follow_redirects=False)
    assert resp.status_code == 404


def test_delete_snippet(client_with_storage):
    client, storage = client_with_storage
    sn = storage.create_snippet({"title": "Delete Me"})
    resp = client.post(f"/snippets/{sn['id']}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert storage.get_snippet(sn["id"]) is None


def test_search_snippets(client_with_storage):
    client, storage = client_with_storage
    storage.create_snippet({"title": "Kubernetes Tips"})
    storage.create_snippet({"title": "Docker Stuff"})
    resp = client.get("/snippets?q=kubernetes")
    assert resp.status_code == 200
    assert b"Kubernetes Tips" in resp.content
    assert b"Docker Stuff" not in resp.content
