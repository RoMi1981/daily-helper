"""Tests for global search route GET /search."""

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
    def _commit_and_push(self, msg): self._committed.append(msg)

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


def test_search_empty_query_renders_form(client):
    """GET /search with no query shows the search form."""
    resp = client.get("/search")
    assert resp.status_code == 200
    assert b"Search" in resp.content
    assert b"Search everything" in resp.content


def test_search_no_storage_returns_empty_groups(client):
    """Search with a query but no storage configured returns no groups."""
    resp = client.get("/search?q=anything")
    assert resp.status_code == 200
    assert b"No results for" in resp.content


def test_search_shows_query_in_form(client):
    """The search input shows the submitted query value."""
    resp = client.get("/search?q=hello")
    assert resp.status_code == 200
    assert b"hello" in resp.content


def test_search_with_notes_results(tmp_path, isolated_settings):
    """When notes storage has a match, the Notes group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.notes.storage import NoteStorage
    note_store = NoteStorage(fake_git)
    note_store.create_note({"subject": "My SSH Guide", "body": "ssh-keygen tips"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        if module == "notes":
            return fake_git
        return None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=SSH")

    assert resp.status_code == 200
    assert b"Notes" in resp.content
    assert b"My SSH Guide" in resp.content


def test_search_with_snippets_results(tmp_path, isolated_settings):
    """When snippets storage has a match, the Snippets group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.snippets.storage import SnippetStorage
    sn_store = SnippetStorage(fake_git)
    sn_store.create_snippet({"title": "Kubectl cheatsheet", "steps": [
        {"description": "List pods", "command": "kubectl get pods"},
    ]})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        if module == "snippets":
            return fake_git
        return None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=kubectl")

    assert resp.status_code == 200
    assert b"Snippets" in resp.content
    assert b"Kubectl cheatsheet" in resp.content


def test_search_with_runbooks_results(tmp_path, isolated_settings):
    """When runbooks storage has a match, the Runbooks group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.runbooks.storage import RunbookStorage
    rb_store = RunbookStorage(fake_git)
    rb_store.create_runbook({"title": "Deploy to production"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        if module == "runbooks":
            return fake_git
        return None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=deploy")

    assert resp.status_code == 200
    assert b"Runbooks" in resp.content
    assert b"Deploy to production" in resp.content


def test_search_total_count_shown(tmp_path, isolated_settings):
    """Result count is shown in the summary line."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.snippets.storage import SnippetStorage
    sn_store = SnippetStorage(fake_git)
    sn_store.create_snippet({"title": "Alpha snippet"})
    sn_store.create_snippet({"title": "Alpha two"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        return fake_git if module == "snippets" else None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=alpha")

    assert resp.status_code == 200
    assert b"result" in resp.content  # "2 results"


def test_search_module_exception_does_not_crash(tmp_path, isolated_settings):
    """An exception in one module search doesn't crash the whole page."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": MagicMock()}
    mock_storage.search.side_effect = RuntimeError("boom")

    def fake_get_primary(module, storage):
        raise RuntimeError("storage error")

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=anything")

    assert resp.status_code == 200
    assert b"No results for" in resp.content


def test_search_with_tasks_results(tmp_path, isolated_settings):
    """When tasks storage has a match, the Tasks group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.tasks.storage import TaskStorage
    ts = TaskStorage(fake_git)
    ts.create_task({"title": "Deploy hotfix to prod"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        return fake_git if module == "tasks" else None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=hotfix")

    assert resp.status_code == 200
    assert b"Tasks" in resp.content
    assert b"Deploy hotfix to prod" in resp.content


def test_search_with_links_results(tmp_path, isolated_settings):
    """When links storage has a match, the Links group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.links.storage import LinkStorage
    ls = LinkStorage(fake_git)
    ls.create_link({"title": "Prometheus Docs", "url": "https://prometheus.io"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        return fake_git if module == "links" else None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=prometheus")

    assert resp.status_code == 200
    assert b"Links" in resp.content
    assert b"Prometheus Docs" in resp.content


def test_search_with_mail_templates_results(tmp_path, isolated_settings):
    """When mail_templates storage has a match, the Mail Templates group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.mail_templates.storage import MailTemplateStorage
    ms = MailTemplateStorage(fake_git)
    ms.create_template({"name": "Incident Alert", "subject": "INCIDENT: down", "body": "Service is down"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        return fake_git if module == "mail_templates" else None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=incident")

    assert resp.status_code == 200
    assert b"Mail Templates" in resp.content
    assert b"Incident Alert" in resp.content


def test_search_with_ticket_templates_results(tmp_path, isolated_settings):
    """When ticket_templates storage has a match, the Ticket Templates group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.ticket_templates.storage import TicketTemplateStorage
    ts = TicketTemplateStorage(fake_git)
    ts.create_template({"name": "Bug Report Template", "description": "reproduction steps"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        return fake_git if module == "ticket_templates" else None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=bug+report")

    assert resp.status_code == 200
    assert b"Ticket Templates" in resp.content
    assert b"Bug Report Template" in resp.content


def test_search_with_vacations_results(tmp_path, isolated_settings):
    """When vacations storage has a match, the Vacations group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.vacations.storage import VacationStorage
    vs = VacationStorage(fake_git)
    vs.create_entry({"start_date": "2026-08-01", "end_date": "2026-08-10", "note": "Summer holiday"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        return fake_git if module == "vacations" else None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=2026-08")

    assert resp.status_code == 200
    assert b"Vacations" in resp.content
    assert b"2026-08-01" in resp.content


def test_search_with_appointments_results(tmp_path, isolated_settings):
    """When appointments storage has a match, the Appointments group appears."""
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.appointments.storage import AppointmentStorage
    aps = AppointmentStorage(fake_git)
    aps.create_entry({"title": "KubeCon Conference", "start_date": "2026-09-01", "end_date": "2026-09-03"})

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        return fake_git if module == "appointments" else None

    with patch("main.get_storage", return_value=mock_storage), \
         patch("core.module_repos.get_primary_store", side_effect=fake_get_primary):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=kubecon")

    assert resp.status_code == 200
    assert b"Appointments" in resp.content
    assert b"KubeCon Conference" in resp.content
