"""Tests for Notes module — storage and router."""

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


# ── Storage tests ────────────────────────────────────────────────────────────


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._pulled = 0
        self._committed = []

    def _pull(self):
        self._pulled += 1

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


@pytest.fixture()
def note_storage(tmp_path):
    from modules.notes.storage import NoteStorage

    return NoteStorage(FakeGit(tmp_path))


def test_list_empty(note_storage):
    assert note_storage.list_notes() == []


def test_create_and_list(note_storage):
    n = note_storage.create_note({"subject": "Hello", "body": "World"})
    assert n["subject"] == "Hello"
    assert n["body"] == "World"
    assert "id" in n
    assert "created" in n
    notes = note_storage.list_notes()
    assert len(notes) == 1
    assert notes[0]["subject"] == "Hello"


def test_get_note(note_storage):
    n = note_storage.create_note({"subject": "Test", "body": "Body"})
    fetched = note_storage.get_note(n["id"])
    assert fetched is not None
    assert fetched["subject"] == "Test"


def test_get_note_missing(note_storage):
    assert note_storage.get_note("doesnotexist") is None


def test_update_note(note_storage):
    n = note_storage.create_note({"subject": "Old", "body": "Old body"})
    updated = note_storage.update_note(n["id"], {"subject": "New", "body": "New body"})
    assert updated["subject"] == "New"
    assert updated["body"] == "New body"
    assert updated["updated"] >= updated["created"]


def test_update_missing(note_storage):
    assert note_storage.update_note("missing", {"subject": "x"}) is None


def test_delete_note(note_storage):
    n = note_storage.create_note({"subject": "Bye", "body": ""})
    assert note_storage.delete_note(n["id"]) is True
    assert note_storage.get_note(n["id"]) is None


def test_delete_missing(note_storage):
    assert note_storage.delete_note("ghost") is False


def test_search_subject(note_storage):
    note_storage.create_note({"subject": "Python tips", "body": "Use list comprehensions"})
    note_storage.create_note({"subject": "Shopping list", "body": "Milk, eggs"})
    results = note_storage.list_notes(query="python")
    assert len(results) == 1
    assert results[0]["subject"] == "Python tips"


def test_search_body(note_storage):
    note_storage.create_note({"subject": "Random", "body": "Contains keyword secret"})
    note_storage.create_note({"subject": "Other", "body": "Nothing here"})
    results = note_storage.list_notes(query="secret")
    assert len(results) == 1


def test_search_no_match(note_storage):
    note_storage.create_note({"subject": "Hello", "body": "World"})
    assert note_storage.list_notes(query="zzznomatch") == []


def test_list_sorted_by_updated(note_storage):
    n1 = note_storage.create_note({"subject": "First", "body": ""})
    note_storage.create_note({"subject": "Second", "body": ""})
    note_storage.update_note(n1["id"], {"subject": "First Updated", "body": ""})
    notes = note_storage.list_notes()
    subjects = [n["subject"] for n in notes]
    assert "First Updated" in subjects
    assert "Second" in subjects


def test_commit_messages(note_storage):
    n = note_storage.create_note({"subject": "My Note", "body": ""})
    note_storage.update_note(n["id"], {"subject": "My Note", "body": "changed"})
    note_storage.delete_note(n["id"])
    commits = note_storage._git._committed
    assert any("add" in c for c in commits)
    assert any("update" in c for c in commits)
    assert any("delete" in c for c in commits)


# ── Archive tests ────────────────────────────────────────────────────────────


def test_archive_note(note_storage):
    n = note_storage.create_note({"subject": "To Archive", "body": "body"})
    result = note_storage.archive_note(n["id"])
    assert result is True
    # no longer in active list
    assert note_storage.list_notes() == []
    # appears in archive
    archived = note_storage.list_archived_notes()
    assert len(archived) == 1
    assert archived[0]["subject"] == "To Archive"


def test_archive_missing(note_storage):
    assert note_storage.archive_note("ghost") is False


def test_get_archived_note(note_storage):
    n = note_storage.create_note({"subject": "Get Archived", "body": "data"})
    note_storage.archive_note(n["id"])
    fetched = note_storage.get_archived_note(n["id"])
    assert fetched is not None
    assert fetched["subject"] == "Get Archived"


def test_restore_note(note_storage):
    n = note_storage.create_note({"subject": "Restore Me", "body": "content"})
    note_storage.archive_note(n["id"])
    result = note_storage.restore_note(n["id"])
    assert result is True
    # back in active list
    active = note_storage.list_notes()
    assert len(active) == 1
    assert active[0]["subject"] == "Restore Me"
    # gone from archive
    assert note_storage.list_archived_notes() == []


def test_restore_removes_empty_archive_dir(note_storage, tmp_path):
    n = note_storage.create_note({"subject": "Cleanup", "body": ""})
    note_storage.archive_note(n["id"])
    note_storage.restore_note(n["id"])
    archive_dir = tmp_path / "notes" / "archive"
    assert not archive_dir.exists()


def test_restore_missing(note_storage):
    assert note_storage.restore_note("ghost") is False


def test_archive_commit_messages(note_storage):
    n = note_storage.create_note({"subject": "Commit Test", "body": ""})
    note_storage.archive_note(n["id"])
    note_storage.restore_note(n["id"])
    commits = note_storage._git._committed
    assert any("archive" in c for c in commits)
    assert any("restore" in c for c in commits)


def test_archive_search(note_storage):
    n1 = note_storage.create_note({"subject": "Python tips", "body": "use comprehensions"})
    n2 = note_storage.create_note({"subject": "Shopping", "body": "eggs"})
    note_storage.archive_note(n1["id"])
    note_storage.archive_note(n2["id"])
    results = note_storage.list_archived_notes(query="python")
    assert len(results) == 1
    assert results[0]["subject"] == "Python tips"


# ── Router tests ─────────────────────────────────────────────────────────────

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
def client_with_storage(tmp_path, isolated_settings, monkeypatch):
    from unittest.mock import MagicMock, patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.notes.storage import NoteStorage

    real_storage = NoteStorage(fake_git)

    mock_multi = MagicMock()
    mock_multi._stores = {"repo1": fake_git}

    with (
        patch("core.state.get_storage", return_value=mock_multi),
        patch("modules.notes.router.get_storage", return_value=mock_multi),
        patch("modules.notes.router.get_primary_store", return_value=fake_git),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


def test_notes_list_no_storage(client):
    resp = client.get("/notes")
    assert resp.status_code == 200
    assert "No repository" in resp.text


def test_notes_new_form_no_storage(client):
    resp = client.get("/notes/new")
    assert resp.status_code == 200


def test_notes_404_disabled(client):
    from core import settings_store

    cfg = settings_store.load()
    cfg["modules_enabled"]["notes"] = False
    settings_store.save(cfg)
    resp = client.get("/notes")
    assert resp.status_code == 404


def test_notes_create_and_list(client_with_storage):
    client, storage = client_with_storage
    resp = client.post(
        "/notes/new", data={"subject": "Test Note", "body": "Hello World"}, follow_redirects=True
    )
    assert resp.status_code == 200
    notes = storage.list_notes()
    assert len(notes) == 1
    assert notes[0]["subject"] == "Test Note"


def test_notes_view(client_with_storage):
    client, storage = client_with_storage
    n = storage.create_note({"subject": "View Me", "body": "Some content here"})
    resp = client.get(f"/notes/{n['id']}")
    assert resp.status_code == 200
    assert "View Me" in resp.text
    assert "Some content here" in resp.text


def test_notes_view_404(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/notes/doesnotexist")
    assert resp.status_code == 404


def test_notes_edit_form(client_with_storage):
    client, storage = client_with_storage
    n = storage.create_note({"subject": "Edit Me", "body": "Body"})
    resp = client.get(f"/notes/{n['id']}/edit")
    assert resp.status_code == 200
    assert "Edit Me" in resp.text


def test_notes_update(client_with_storage):
    client, storage = client_with_storage
    n = storage.create_note({"subject": "Old Subject", "body": "Old"})
    resp = client.post(
        f"/notes/{n['id']}/edit",
        data={"subject": "New Subject", "body": "New body"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = storage.get_note(n["id"])
    assert updated["subject"] == "New Subject"


def test_notes_delete(client_with_storage):
    client, storage = client_with_storage
    n = storage.create_note({"subject": "To Delete", "body": ""})
    resp = client.post(f"/notes/{n['id']}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert storage.get_note(n["id"]) is None


def test_notes_search(client_with_storage):
    client, storage = client_with_storage
    storage.create_note({"subject": "Alpha Note", "body": "content"})
    storage.create_note({"subject": "Beta Note", "body": "content"})
    resp = client.get("/notes?q=alpha")
    assert resp.status_code == 200
    assert "Alpha Note" in resp.text
    assert "Beta Note" not in resp.text


def test_notes_archive_page(client_with_storage):
    client, storage = client_with_storage
    n = storage.create_note({"subject": "Archived Note", "body": "archived body"})
    storage.archive_note(n["id"])
    resp = client.get("/notes/archive")
    assert resp.status_code == 200
    assert "Archived Note" in resp.text


def test_notes_archive_action(client_with_storage):
    client, storage = client_with_storage
    n = storage.create_note({"subject": "To Archive", "body": ""})
    resp = client.post(f"/notes/{n['id']}/archive", follow_redirects=True)
    assert resp.status_code == 200
    assert storage.list_notes() == []
    assert len(storage.list_archived_notes()) == 1


def test_notes_restore_action(client_with_storage):
    client, storage = client_with_storage
    n = storage.create_note({"subject": "To Restore", "body": ""})
    storage.archive_note(n["id"])
    resp = client.post(f"/notes/archive/{n['id']}/restore", follow_redirects=True)
    assert resp.status_code == 200
    assert len(storage.list_notes()) == 1
    assert storage.list_archived_notes() == []


def test_notes_archive_empty_page(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/notes/archive")
    assert resp.status_code == 200
    assert "No archived notes" in resp.text
