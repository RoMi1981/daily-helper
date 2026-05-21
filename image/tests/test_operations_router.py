"""Router integration tests for the Operations module."""

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


# ── _repo_name helper ──────────────────────────────────────────────────────


def test_repo_name_found():
    from modules.operations.router import _repo_name

    cfg = {"repos": [{"id": "abc", "name": "My Repo"}]}
    assert _repo_name(cfg, "abc") == "My Repo"


def test_repo_name_not_found():
    from modules.operations.router import _repo_name

    cfg = {"repos": [{"id": "abc", "name": "My Repo"}]}
    assert _repo_name(cfg, "xyz") == "xyz"


def test_repo_name_empty():
    from modules.operations.router import _repo_name

    assert _repo_name({}, "abc") == "abc"


# ── _get_items helper ──────────────────────────────────────────────────────


def test_get_items_unknown_store(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock

    storage = MagicMock()
    storage._stores = {}
    result = _get_items(storage, "missing", "notes")
    assert result == []


def test_get_items_notes(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.notes.storage import NoteStorage

    fake_git = FakeGit(tmp_path)
    ns = NoteStorage(fake_git)
    ns.create_note({"subject": "Test Note", "body": "hello"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "notes")
    assert len(result) == 1
    assert result[0]["subject"] == "Test Note"


def test_get_items_links(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.links.storage import LinkStorage

    fake_git = FakeGit(tmp_path)
    ls = LinkStorage(fake_git)
    ls.create_link({"title": "Google", "url": "https://google.com"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "links")
    assert len(result) == 1


def test_get_items_runbooks(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.runbooks.storage import RunbookStorage

    fake_git = FakeGit(tmp_path)
    rs = RunbookStorage(fake_git)
    rs.create_runbook({"title": "Deploy"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "runbooks")
    assert len(result) == 1


def test_get_items_tasks(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.tasks.storage import TaskStorage

    fake_git = FakeGit(tmp_path)
    ts = TaskStorage(fake_git)
    ts.create_task({"title": "My task"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "tasks")
    assert len(result) == 1


def test_get_items_mail_templates(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.mail_templates.storage import MailTemplateStorage

    fake_git = FakeGit(tmp_path)
    ms = MailTemplateStorage(fake_git)
    ms.create_template({"name": "Template A"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "mail_templates")
    assert len(result) == 1


def test_get_items_ticket_templates(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.ticket_templates.storage import TicketTemplateStorage

    fake_git = FakeGit(tmp_path)
    ts = TicketTemplateStorage(fake_git)
    ts.create_template({"name": "Bug Report"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "ticket_templates")
    assert len(result) == 1


# ── _do_copy_move helper ───────────────────────────────────────────────────


def test_copy_notes(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.notes.storage import NoteStorage
    import pathlib

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ns = NoteStorage(src_git)
    note = ns.create_note({"subject": "Migrate Me", "body": "content"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", [note["id"]], "copy")
    assert count == 1
    assert errors == []
    # File should exist in dst
    dst_file = dst_path / "notes" / f"{note['id']}.yaml"
    assert dst_file.exists()


def test_copy_links(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.links.storage import LinkStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ls = LinkStorage(src_git, "default")
    link = ls.create_link({"title": "Test", "url": "https://test.com"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "links", [link["id"]], "copy")
    assert count == 1
    assert errors == []


def test_copy_runbooks(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.runbooks.storage import RunbookStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    rs = RunbookStorage(src_git)
    rb = rs.create_runbook({"title": "Deploy App"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "runbooks", [rb["id"]], "copy")
    assert count == 1
    assert errors == []


def test_move_deletes_source(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.notes.storage import NoteStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ns = NoteStorage(src_git)
    note = ns.create_note({"subject": "Move Me", "body": "x"})
    src_file = src_path / "notes" / f"{note['id']}.yaml"
    assert src_file.exists()

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", [note["id"]], "move")
    assert count == 1
    assert not src_file.exists()


def test_copy_missing_store(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    storage = MagicMock()
    storage._stores = {}
    count, errors = _do_copy_move(storage, "src", "dst", "notes", ["abc"], "copy")
    assert count == 0
    assert len(errors) > 0


def test_copy_missing_item(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    storage = MagicMock()
    storage._stores = {"src": FakeGit(src_path), "dst": FakeGit(dst_path)}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", ["doesnotexist"], "copy")
    assert count == 0
    assert len(errors) > 0


# ── Routes ─────────────────────────────────────────────────────────────────


def test_index_not_shown_single_repo(client):
    # Operations tab only visible with 2+ repos — with no repos the page still renders
    resp = client.get("/operations")
    assert resp.status_code == 200


def test_execute_same_src_dst(client):
    resp = client.post(
        "/operations/execute",
        data={
            "src_repo": "repo1",
            "dst_repo": "repo1",
            "content_type": "notes",
            "action": "copy",
            "items": ["abc"],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errors=" in resp.headers["location"]


def test_execute_no_items(client):
    resp = client.post(
        "/operations/execute",
        data={
            "src_repo": "repo1",
            "dst_repo": "repo2",
            "content_type": "notes",
            "action": "copy",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errors=" in resp.headers["location"]


# ── _get_items: remaining types ────────────────────────────────────────────


def test_get_items_vacations(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.vacations.storage import VacationStorage

    fake_git = FakeGit(tmp_path)
    vs = VacationStorage(fake_git)
    vs.create_entry(
        {
            "start_date": "2026-01-01",
            "end_date": "2026-01-05",
            "type": "vacation",
            "status": "approved",
        }
    )

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "vacations")
    assert len(result) == 1


def test_get_items_knowledge(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock

    fake_git = FakeGit(tmp_path)
    # Manually create a knowledge entry file
    cat_dir = tmp_path / "knowledge" / "general"
    cat_dir.mkdir(parents=True)
    (cat_dir / "test-entry.md").write_text("# Test\ncontent")

    # Mock get_entries on the fake_git store
    fake_git.knowledge_path = tmp_path / "knowledge"

    class FakeKBGit(FakeGit):
        def get_entries(self):
            return [{"slug": "test-entry", "category": "general", "title": "Test"}]

    kb_git = FakeKBGit(tmp_path)
    storage = MagicMock()
    storage._stores = {"repo1": kb_git}
    result = _get_items(storage, "repo1", "knowledge")
    assert len(result) == 1
    assert result[0]["category"] == "general"


def test_get_items_exception_returns_empty(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock

    class BrokenGit(FakeGit):
        def get_entries(self):
            raise RuntimeError("broken")

    storage = MagicMock()
    storage._stores = {"repo1": BrokenGit(tmp_path)}
    # knowledge type calls get_entries → should swallow exception
    result = _get_items(storage, "repo1", "knowledge")
    assert result == []


# ── _do_copy_move: remaining content types ─────────────────────────────────


def test_copy_tasks(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.tasks.storage import TaskStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ts = TaskStorage(src_git)
    task = ts.create_task({"title": "Copy task"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "tasks", [task["id"]], "copy")
    assert count == 1
    assert errors == []
    assert (dst_path / "tasks" / f"{task['id']}.yaml").exists()


def test_copy_vacations(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.vacations.storage import VacationStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    vs = VacationStorage(src_git)
    entry = vs.create_entry(
        {
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "type": "vacation",
            "status": "planned",
        }
    )

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "vacations", [entry["id"]], "copy")
    assert count == 1
    assert errors == []


def test_copy_knowledge(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)
    src_git.knowledge_path = src_path / "knowledge"
    dst_git.knowledge_path = dst_path / "knowledge"

    cat_dir = src_path / "knowledge" / "howto"
    cat_dir.mkdir(parents=True)
    (cat_dir / "deploy.md").write_text("# Deploy\nsteps")

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "knowledge", ["howto/deploy"], "copy")
    assert count == 1
    assert errors == []
    assert (dst_path / "knowledge" / "howto" / "deploy.md").exists()


def test_copy_knowledge_invalid_id(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)
    src_git.knowledge_path = src_path / "knowledge"
    dst_git.knowledge_path = dst_path / "knowledge"

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    # ID without "/" is invalid for knowledge
    count, errors = _do_copy_move(storage, "src", "dst", "knowledge", ["nodash"], "copy")
    assert count == 0


def test_copy_mail_templates(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.mail_templates.storage import MailTemplateStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ms = MailTemplateStorage(src_git)
    tpl = ms.create_template({"name": "Welcome", "subject": "Hi", "body": "Hello"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "mail_templates", [tpl["id"]], "copy")
    assert count == 1
    assert errors == []


def test_copy_ticket_templates(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.ticket_templates.storage import TicketTemplateStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ts = TicketTemplateStorage(src_git)
    tpl = ts.create_template({"name": "Bug", "body": "Describe bug"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "ticket_templates", [tpl["id"]], "copy")
    assert count == 1
    assert errors == []


# ── _do_copy_move: error paths ─────────────────────────────────────────────


def test_copy_dst_pull_failure(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)

    class FailPullGit(FakeGit):
        def _pull(self):
            raise RuntimeError("network error")

    dst_git = FailPullGit(dst_path)

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", ["abc"], "copy")
    assert count == 0
    assert len(errors) > 0
    assert "sync" in errors[0].lower() or "failed" in errors[0].lower()


def test_copy_commit_failure(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.notes.storage import NoteStorage
    from core.storage import GitStorageError

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)

    class FailCommitGit(FakeGit):
        def _commit_and_push(self, msg):
            raise GitStorageError("push failed")

    dst_git = FailCommitGit(dst_path)

    ns = NoteStorage(src_git)
    note = ns.create_note({"subject": "Note", "body": "x"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", [note["id"]], "copy")
    assert count == 0
    assert len(errors) > 0


def test_move_tasks(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.tasks.storage import TaskStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ts = TaskStorage(src_git)
    task = ts.create_task({"title": "Move task"})
    src_file = src_path / "tasks" / f"{task['id']}.yaml"
    assert src_file.exists()

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "tasks", [task["id"]], "move")
    assert count == 1
    assert not src_file.exists()


def test_move_vacations(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.vacations.storage import VacationStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    vs = VacationStorage(src_git)
    entry = vs.create_entry(
        {
            "start_date": "2026-07-01",
            "end_date": "2026-07-10",
            "type": "vacation",
            "status": "planned",
        }
    )
    src_file = src_path / "vacations" / "entries" / f"{entry['id']}.yaml"
    assert src_file.exists()

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "vacations", [entry["id"]], "move")
    assert count == 1
    assert not src_file.exists()


def test_move_knowledge(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)
    src_git.knowledge_path = src_path / "knowledge"
    dst_git.knowledge_path = dst_path / "knowledge"

    cat_dir = src_path / "knowledge" / "ops"
    cat_dir.mkdir(parents=True)
    src_file = cat_dir / "restart.md"
    src_file.write_text("# Restart\nsteps")

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "knowledge", ["ops/restart"], "move")
    assert count == 1
    assert not src_file.exists()


def test_move_commit_delete_failure(tmp_path):
    """If source commit fails after move, error is added but count is correct."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.notes.storage import NoteStorage
    from core.storage import GitStorageError

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    commit_calls = []

    class SelectiveFailGit(FakeGit):
        def _commit_and_push(self, msg):
            commit_calls.append(msg)
            if "move" in msg:
                raise GitStorageError("source push failed")

    src_git = SelectiveFailGit(src_path)
    dst_git = FakeGit(dst_path)

    ns = NoteStorage(src_git)
    note = ns.create_note({"subject": "Move fail", "body": "x"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", [note["id"]], "move")
    assert count == 1  # copy succeeded
    assert any("Failed to commit" in e or "commit" in e.lower() for e in errors)


# ── Route: operations index with items ─────────────────────────────────────


def test_index_with_two_repos(client):
    from core import settings_store

    cfg = settings_store.load()
    cfg["repos"] = [
        {
            "id": "r1",
            "name": "Repo 1",
            "url": "https://x.com/r1.git",
            "platform": "gitea",
            "auth_mode": "none",
            "enabled": True,
            "permissions": {"read": True, "write": True},
        },
        {
            "id": "r2",
            "name": "Repo 2",
            "url": "https://x.com/r2.git",
            "platform": "gitea",
            "auth_mode": "none",
            "enabled": True,
            "permissions": {"read": True, "write": True},
        },
    ]
    settings_store.save(cfg)
    resp = client.get("/operations?src=r1&type=notes")
    assert resp.status_code == 200


# ── _get_items: appointments ───────────────────────────────────────────────


def test_get_items_appointments(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.appointments.storage import AppointmentStorage

    fake_git = FakeGit(tmp_path)
    aps = AppointmentStorage(fake_git)
    aps.create_entry({"title": "Meeting", "start_date": "2026-05-01", "end_date": "2026-05-01"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "appointments")
    assert len(result) == 1


# ── _do_copy_move: appointments ────────────────────────────────────────────


def test_copy_appointments(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.appointments.storage import AppointmentStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    aps = AppointmentStorage(src_git)
    entry = aps.create_entry(
        {"title": "Dentist", "start_date": "2026-06-01", "end_date": "2026-06-01"}
    )

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "appointments", [entry["id"]], "copy")
    assert count == 1
    assert errors == []
    dst_file = dst_path / "appointments" / "entries" / f"{entry['id']}.yaml"
    assert dst_file.exists()


def test_copy_appointment_not_found(tmp_path):
    """Lines 142-143: appointment not found error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    storage = MagicMock()
    storage._stores = {"src": FakeGit(src_path), "dst": FakeGit(dst_path)}

    count, errors = _do_copy_move(storage, "src", "dst", "appointments", ["doesnotexist"], "copy")
    assert count == 0
    assert any("Appointment not found" in e for e in errors)


def test_copy_knowledge_not_found(tmp_path):
    """Lines 100-101: knowledge file not found error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)
    src_git.knowledge_path = src_path / "knowledge"
    dst_git.knowledge_path = dst_path / "knowledge"

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "knowledge", ["howto/missing"], "copy")
    assert count == 0
    assert any("Not found" in e for e in errors)


def test_copy_task_not_found(tmp_path):
    """Lines 114-115: task not found error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    storage = MagicMock()
    storage._stores = {"src": FakeGit(src_path), "dst": FakeGit(dst_path)}

    count, errors = _do_copy_move(storage, "src", "dst", "tasks", ["nonexistent"], "copy")
    assert count == 0
    assert any("Task not found" in e for e in errors)


def test_copy_vacation_not_found(tmp_path):
    """Lines 128-129: vacation entry not found error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    storage = MagicMock()
    storage._stores = {"src": FakeGit(src_path), "dst": FakeGit(dst_path)}

    count, errors = _do_copy_move(storage, "src", "dst", "vacations", ["nonexistent"], "copy")
    assert count == 0
    assert any("Entry not found" in e for e in errors)


def test_copy_note_not_found(tmp_path):
    """Lines 162-163: notes/links/runbooks 'Template not found' error path."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    storage = MagicMock()
    storage._stores = {"src": FakeGit(src_path), "dst": FakeGit(dst_path)}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", ["doesnotexist"], "copy")
    assert count == 0
    assert any("Template not found" in e for e in errors)


def test_move_appointments(tmp_path):
    """Move appointment removes source file."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.appointments.storage import AppointmentStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    aps = AppointmentStorage(src_git)
    entry = aps.create_entry(
        {"title": "Call", "start_date": "2026-07-01", "end_date": "2026-07-01"}
    )
    src_file = src_path / "appointments" / "entries" / f"{entry['id']}.yaml"
    assert src_file.exists()

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "appointments", [entry["id"]], "move")
    assert count == 1
    assert not src_file.exists()


def test_move_src_pull_failure_adds_warning(tmp_path):
    """Lines 179-180: move with src pull failure adds a warning to errors."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.notes.storage import NoteStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    class FailSecondPullGit(FakeGit):
        def __init__(self, path):
            super().__init__(path)
            self._pull_count = 0

        def _pull(self):
            self._pull_count += 1
            if self._pull_count > 1:
                raise RuntimeError("network timeout")

    src_git = FailSecondPullGit(src_path)
    dst_git = FakeGit(dst_path)

    ns = NoteStorage(src_git)
    note = ns.create_note({"subject": "test", "body": "x"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "notes", [note["id"]], "move")
    assert count == 1
    assert any("sync" in e.lower() or "Warning" in e for e in errors)


def test_copy_knowledge_exception(tmp_path):
    """Lines 105-106: exception during knowledge copy adds error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock, patch
    import pathlib

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    # Create the file so it's found, but make copy raise
    kb_dir = src_path / "knowledge" / "cat"
    kb_dir.mkdir(parents=True)
    (kb_dir / "slug.md").write_text("# content")
    src_git.knowledge_path = src_path / "knowledge"
    dst_git.knowledge_path = dst_path / "knowledge"

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    with patch("shutil.copy2", side_effect=OSError("disk full")):
        count, errors = _do_copy_move(storage, "src", "dst", "knowledge", ["cat/slug"], "copy")
    assert count == 0
    assert any("cat/slug" in e or "disk full" in e for e in errors)


def test_copy_task_exception(tmp_path):
    """Lines 119-120: exception during task copy adds error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock, patch
    from modules.tasks.storage import TaskStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ts = TaskStorage(src_git)
    task = ts.create_task({"title": "Exception task"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    with patch("shutil.copy2", side_effect=OSError("io error")):
        count, errors = _do_copy_move(storage, "src", "dst", "tasks", [task["id"]], "copy")
    assert count == 0
    assert len(errors) > 0


def test_copy_vacation_exception(tmp_path):
    """Lines 133-134: exception during vacation copy adds error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock, patch
    from modules.vacations.storage import VacationStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    vs = VacationStorage(src_git)
    entry = vs.create_entry(
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-05",
            "type": "vacation",
            "status": "planned",
        }
    )

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    with patch("shutil.copy2", side_effect=OSError("permission denied")):
        count, errors = _do_copy_move(storage, "src", "dst", "vacations", [entry["id"]], "copy")
    assert count == 0
    assert len(errors) > 0


def test_copy_appointment_exception(tmp_path):
    """Lines 147-148: exception during appointment copy adds error."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock, patch
    from modules.appointments.storage import AppointmentStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    aps = AppointmentStorage(src_git)
    entry = aps.create_entry(
        {"title": "Meeting", "start_date": "2026-05-10", "end_date": "2026-05-10"}
    )

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    with patch("shutil.copy2", side_effect=OSError("disk full")):
        count, errors = _do_copy_move(storage, "src", "dst", "appointments", [entry["id"]], "copy")
    assert count == 0
    assert len(errors) > 0


def test_copy_note_exception(tmp_path):
    """Lines 162-163: exception during copy in notes/links/runbooks branch."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock, patch
    from modules.notes.storage import NoteStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ns = NoteStorage(src_git)
    note = ns.create_note({"subject": "Exception note", "body": "x"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    with patch("shutil.copy2", side_effect=OSError("notes io error")):
        count, errors = _do_copy_move(storage, "src", "dst", "notes", [note["id"]], "copy")
    assert count == 0
    assert any("notes io error" in e or note["id"] in e for e in errors)


def test_move_knowledge_with_invalid_id_skipped(tmp_path):
    """Line 187: invalid knowledge id (no '/') is skipped in the move delete phase."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)
    src_git.knowledge_path = src_path / "knowledge"
    dst_git.knowledge_path = dst_path / "knowledge"

    # Create a valid entry
    cat_dir = src_path / "knowledge" / "cat"
    cat_dir.mkdir(parents=True)
    (cat_dir / "good.md").write_text("# good")

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    # "nodash" has no "/" — it gets copied (skipped in copy phase but that means count=0)
    # We need one valid item to succeed copy so we enter delete phase
    # Pass both: "cat/good" succeeds, "nodash" is skipped in delete phase
    count, errors = _do_copy_move(
        storage, "src", "dst", "knowledge", ["cat/good", "nodash"], "move"
    )
    assert count == 1  # only cat/good succeeded


def test_move_delete_unlink_exception(tmp_path):
    """Lines 201-202: exception during file unlink in move delete phase."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock, patch
    from modules.notes.storage import NoteStorage
    from pathlib import Path

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ns = NoteStorage(src_git)
    note = ns.create_note({"subject": "Unlink fail", "body": "x"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    original_unlink = Path.unlink

    def fail_unlink(self, missing_ok=False):
        raise OSError("read-only filesystem")

    with patch.object(Path, "unlink", fail_unlink):
        count, errors = _do_copy_move(storage, "src", "dst", "notes", [note["id"]], "move")
    assert count == 1  # copy succeeded
    assert any("Delete" in e or "read-only" in e for e in errors)


# ── ZIP export ────────────────────────────────────────────────────────────────


def test_export_returns_zip_with_yaml_files(tmp_path, client):
    """GET /operations/export returns a ZIP containing YAML files."""
    from unittest.mock import patch, MagicMock
    import zipfile, io

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    tasks_dir = repo_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "abc123.yaml").write_text("title: Task 1\n")
    # non-data file should be excluded
    (repo_path / "script.py").write_text("print('hi')")

    fake_gs = MagicMock()
    fake_gs.local_path = str(repo_path)

    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.load",
            return_value={"repos": [{"id": "r1", "name": "My Repo"}]},
        ),
    ):
        resp = client.get("/operations/export?repo_id=r1")

    assert resp.status_code == 200
    assert "application/zip" in resp.headers["content-type"]
    assert "daily-helper_My_Repo-export.zip" in resp.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any("abc123.yaml" in n for n in names)
    assert not any(n.endswith(".py") for n in names)


def test_export_filename_sanitized(tmp_path, client):
    """Repo names with special chars are sanitized in the ZIP filename."""
    from unittest.mock import patch, MagicMock

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    fake_gs = MagicMock()
    fake_gs.local_path = str(repo_path)
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.load",
            return_value={"repos": [{"id": "r1", "name": "My Repo / Test!"}]},
        ),
    ):
        resp = client.get("/operations/export?repo_id=r1")

    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert "daily-helper_" in cd
    assert "/" not in cd.split("filename=")[1]


def test_export_repo_not_found(client):
    """GET /operations/export with unknown repo_id returns 404."""
    from unittest.mock import patch, MagicMock

    fake_storage = MagicMock()
    fake_storage.get_store.return_value = None

    with patch("modules.operations.router.get_storage", return_value=fake_storage):
        resp = client.get("/operations/export?repo_id=doesnotexist")

    assert resp.status_code == 404


def test_export_no_storage(client):
    """GET /operations/export without storage configured returns 503."""
    from unittest.mock import patch

    with patch("modules.operations.router.get_storage", return_value=None):
        resp = client.get("/operations/export?repo_id=r1")

    assert resp.status_code == 503


# ── ZIP import ────────────────────────────────────────────────────────────────


def _make_zip(files: dict) -> bytes:
    """Build a ZIP in-memory. files = {arcname: content_bytes}"""
    import zipfile, io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf.read()


def test_import_merge_mode_imports_new_files(tmp_path, client):
    """POST /operations/import (merge) writes new files and commits."""
    from unittest.mock import patch, MagicMock

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    fake_gs = MagicMock()
    fake_gs.local_path = str(repo_path)
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    zip_data = _make_zip({"notes/new_note.yaml": b"subject: New Note\n"})

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": True}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "merge"},
            files={"file": ("export.zip", zip_data, "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert "result=" in resp.headers["location"]
    assert (repo_path / "notes" / "new_note.yaml").exists()


def test_import_merge_skips_existing_files(tmp_path, client):
    """POST /operations/import (merge) skips files that already exist."""
    from unittest.mock import patch, MagicMock

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "notes").mkdir()
    existing = repo_path / "notes" / "existing.yaml"
    existing.write_bytes(b"subject: Original\n")

    fake_gs = MagicMock()
    fake_gs.local_path = str(repo_path)
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    zip_data = _make_zip({"notes/existing.yaml": b"subject: Overwritten\n"})

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": True}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "merge"},
            files={"file": ("export.zip", zip_data, "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    # File should NOT be overwritten
    assert existing.read_bytes() == b"subject: Original\n"


def test_import_overwrite_mode_replaces_existing(tmp_path, client):
    """POST /operations/import (overwrite) replaces existing files."""
    from unittest.mock import patch, MagicMock

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "notes").mkdir()
    existing = repo_path / "notes" / "note.yaml"
    existing.write_bytes(b"subject: Original\n")

    fake_gs = MagicMock()
    fake_gs.local_path = str(repo_path)
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    zip_data = _make_zip({"notes/note.yaml": b"subject: Updated\n"})

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": True}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "overwrite"},
            files={"file": ("export.zip", zip_data, "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert existing.read_bytes() == b"subject: Updated\n"


def test_import_path_traversal_rejected(tmp_path, client):
    """POST /operations/import rejects ZIP entries with path traversal."""
    from unittest.mock import patch, MagicMock

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    fake_gs = MagicMock()
    fake_gs.local_path = str(repo_path)
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    zip_data = _make_zip({"../evil.yaml": b"injected\n", "good/note.yaml": b"ok\n"})

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": True}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "merge"},
            files={"file": ("export.zip", zip_data, "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert not (tmp_path / "evil.yaml").exists()
    assert (repo_path / "good" / "note.yaml").exists()


def test_import_bad_zip_redirects_with_error(client):
    """POST /operations/import with invalid ZIP redirects with error message."""
    from unittest.mock import patch, MagicMock

    fake_gs = MagicMock()
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": True}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "merge"},
            files={"file": ("bad.zip", b"this is not a zip", "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert "errors=" in resp.headers["location"]


def test_import_empty_file_redirects(client):
    """POST /operations/import with empty file redirects with error."""
    from unittest.mock import patch, MagicMock

    fake_gs = MagicMock()
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": True}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "merge"},
            files={"file": ("empty.zip", b"", "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert "errors=" in resp.headers["location"]


def test_import_readonly_repo_returns_403(client):
    """POST /operations/import on read-only repo returns 403."""
    from unittest.mock import patch, MagicMock

    fake_gs = MagicMock()
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    zip_data = _make_zip({"notes/note.yaml": b"subject: Test\n"})

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": False}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "merge"},
            files={"file": ("export.zip", zip_data, "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 403


def test_import_excludes_non_data_extensions(tmp_path, client):
    """POST /operations/import ignores .py and other non-data files in the ZIP."""
    from unittest.mock import patch, MagicMock

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    fake_gs = MagicMock()
    fake_gs.local_path = str(repo_path)
    fake_storage = MagicMock()
    fake_storage.get_store.return_value = fake_gs

    zip_data = _make_zip(
        {
            "notes/valid.yaml": b"subject: Valid\n",
            "scripts/evil.py": b"import os; os.system('rm -rf /')",
        }
    )

    with (
        patch("modules.operations.router.get_storage", return_value=fake_storage),
        patch(
            "modules.operations.router.settings_store.get_repo",
            return_value={"permissions": {"write": True}},
        ),
    ):
        resp = client.post(
            "/operations/import",
            data={"repo_id": "r1", "mode": "merge"},
            files={"file": ("export.zip", zip_data, "application/zip")},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert (repo_path / "notes" / "valid.yaml").exists()
    assert not (repo_path / "scripts" / "evil.py").exists()


# ── move: remaining content types ─────────────────────────────────────────────


def test_move_delete_commit_failure(tmp_path):
    """Lines 201-202: if source delete commit fails, error added."""
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.tasks.storage import TaskStorage
    from core.storage import GitStorageError

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    commit_calls = []

    class SelectiveFailGit(FakeGit):
        def _commit_and_push(self, msg):
            commit_calls.append(msg)
            if "move" in msg:
                raise GitStorageError("source commit failed")

    src_git = SelectiveFailGit(src_path)
    dst_git = FakeGit(dst_path)

    ts = TaskStorage(src_git)
    task = ts.create_task({"title": "Delete commit fail"})
    # Manually remove the file so 'deleted' count > 0
    task_file = src_path / "tasks" / f"{task['id']}.yaml"
    assert task_file.exists()

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "tasks", [task["id"]], "move")
    assert count == 1  # copy succeeded
    assert any("commit" in e.lower() or "Failed" in e for e in errors)


# ── _get_items: snippets ───────────────────────────────────────────────────


def test_get_items_snippets(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.snippets.storage import SnippetStorage

    fake_git = FakeGit(tmp_path)
    ss = SnippetStorage(fake_git)
    ss.create_snippet({"title": "Deploy", "steps": [{"command": "kubectl apply -f ."}]})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "snippets")
    assert len(result) == 1
    assert result[0]["title"] == "Deploy"


# ── _do_copy_move: snippets ────────────────────────────────────────────────


def test_copy_snippets(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.snippets.storage import SnippetStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ss = SnippetStorage(src_git)
    snippet = ss.create_snippet({"title": "Git tips", "steps": [{"command": "git log --oneline"}]})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "snippets", [snippet["id"]], "copy")
    assert count == 1
    assert errors == []
    dst_file = dst_path / "snippets" / f"{snippet['id']}.yaml"
    assert dst_file.exists()


def test_move_snippets(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.snippets.storage import SnippetStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ss = SnippetStorage(src_git)
    snippet = ss.create_snippet({"title": "Kubectl", "steps": [{"command": "kubectl get pods"}]})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "snippets", [snippet["id"]], "move")
    assert count == 1
    assert errors == []
    src_file = src_path / "snippets" / f"{snippet['id']}.yaml"
    dst_file = dst_path / "snippets" / f"{snippet['id']}.yaml"
    assert dst_file.exists()
    assert not src_file.exists()


# ── MOTD ──────────────────────────────────────────────────────────────────────


def test_get_items_motd(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.motd.storage import MotdStorage

    fake_git = FakeGit(tmp_path)
    ms = MotdStorage(fake_git)
    ms.create_entry({"text": "Good morning!"})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "motd")
    assert len(result) == 1
    assert result[0]["text"] == "Good morning!"


def test_copy_motd(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.motd.storage import MotdStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ms = MotdStorage(src_git)
    entry, _ = ms.create_entry({"text": "Hello!"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "motd", [entry["id"]], "copy")
    assert count == 1
    assert errors == []
    dst_file = dst_path / "motd" / f"{entry['id']}.yaml"
    assert dst_file.exists()


def test_move_motd(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.motd.storage import MotdStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    ms = MotdStorage(src_git)
    entry, _ = ms.create_entry({"text": "Move me!"})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "motd", [entry["id"]], "move")
    assert count == 1
    assert errors == []
    src_file = src_path / "motd" / f"{entry['id']}.yaml"
    assert not src_file.exists()
    assert (dst_path / "motd" / f"{entry['id']}.yaml").exists()


# ── RSS ───────────────────────────────────────────────────────────────────────


def test_get_items_rss(tmp_path):
    from modules.operations.router import _get_items
    from unittest.mock import MagicMock
    from modules.rss.storage import RssStorage

    fake_git = FakeGit(tmp_path)
    rs = RssStorage(fake_git)
    rs.upsert_feed({"name": "Heise", "url": "https://heise.de/rss", "enabled": True})

    storage = MagicMock()
    storage._stores = {"repo1": fake_git}
    result = _get_items(storage, "repo1", "rss")
    assert len(result) == 1
    assert result[0]["name"] == "Heise"


def test_copy_rss(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.rss.storage import RssStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    rs = RssStorage(src_git)
    feed = rs.upsert_feed({"name": "Heise", "url": "https://heise.de/rss", "enabled": True})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "rss", [feed["id"]], "copy")
    assert count == 1
    assert errors == []
    assert (dst_path / "rss" / f"{feed['id']}.yaml").exists()


def test_move_rss(tmp_path):
    from modules.operations.router import _do_copy_move
    from unittest.mock import MagicMock
    from modules.rss.storage import RssStorage

    src_path = tmp_path / "src"
    dst_path = tmp_path / "dst"
    src_path.mkdir()
    dst_path.mkdir()

    src_git = FakeGit(src_path)
    dst_git = FakeGit(dst_path)

    rs = RssStorage(src_git)
    feed = rs.upsert_feed({"name": "The Verge", "url": "https://theverge.com/rss", "enabled": True})

    storage = MagicMock()
    storage._stores = {"src": src_git, "dst": dst_git}

    count, errors = _do_copy_move(storage, "src", "dst", "rss", [feed["id"]], "move")
    assert count == 1
    assert errors == []
    assert not (src_path / "rss" / f"{feed['id']}.yaml").exists()
    assert (dst_path / "rss" / f"{feed['id']}.yaml").exists()
