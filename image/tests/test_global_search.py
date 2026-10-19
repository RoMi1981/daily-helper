"""Tests for global search route GET /search."""

import inspect
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

    def write_lock(self):
        """The storage layer takes this around pull/commit."""
        if not hasattr(self, "_write_lock"):
            import threading

            self._write_lock = threading.RLock()
        return self._write_lock

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
    from core.state import reset_storage
    from fastapi.testclient import TestClient

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
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=SSH")

    assert resp.status_code == 200
    assert b"Notes" in resp.content
    assert b"My SSH Guide" in resp.content


def test_search_with_snippets_results(tmp_path, isolated_settings):
    """When snippets storage has a match, the Snippets group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

    reset_storage()

    fake_git = FakeGit(tmp_path)
    from modules.snippets.storage import SnippetStorage

    sn_store = SnippetStorage(fake_git)
    sn_store.create_snippet(
        {
            "title": "Kubectl cheatsheet",
            "steps": [
                {"description": "List pods", "command": "kubectl get pods"},
            ],
        }
    )

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": fake_git}
    mock_storage.search.return_value = []

    def fake_get_primary(module, storage):
        if module == "snippets":
            return fake_git
        return None

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=kubectl")

    assert resp.status_code == 200
    assert b"Snippets" in resp.content
    assert b"Kubectl cheatsheet" in resp.content


def test_search_with_runbooks_results(tmp_path, isolated_settings):
    """When runbooks storage has a match, the Runbooks group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=deploy")

    assert resp.status_code == 200
    assert b"Runbooks" in resp.content
    assert b"Deploy to production" in resp.content


def test_search_total_count_shown(tmp_path, isolated_settings):
    """Result count is shown in the summary line."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=alpha")

    assert resp.status_code == 200
    assert b"result" in resp.content  # "2 results"


def test_search_module_exception_does_not_crash(tmp_path, isolated_settings):
    """An exception in one module search doesn't crash the whole page."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

    reset_storage()

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": MagicMock()}
    mock_storage.search.side_effect = RuntimeError("boom")

    def fake_get_primary(module, storage):
        raise RuntimeError("storage error")

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=anything")

    assert resp.status_code == 200
    assert b"No results for" in resp.content


def test_search_with_tasks_results(tmp_path, isolated_settings):
    """When tasks storage has a match, the Tasks group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=hotfix")

    assert resp.status_code == 200
    assert b"Tasks" in resp.content
    assert b"Deploy hotfix to prod" in resp.content


def test_search_with_links_results(tmp_path, isolated_settings):
    """When links storage has a match, the Links group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=prometheus")

    assert resp.status_code == 200
    assert b"Links" in resp.content
    assert b"Prometheus Docs" in resp.content


def test_search_with_mail_templates_results(tmp_path, isolated_settings):
    """When mail_templates storage has a match, the Mail Templates group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=incident")

    assert resp.status_code == 200
    assert b"Mail Templates" in resp.content
    assert b"Incident Alert" in resp.content


def test_search_with_ticket_templates_results(tmp_path, isolated_settings):
    """When ticket_templates storage has a match, the Ticket Templates group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=bug+report")

    assert resp.status_code == 200
    assert b"Ticket Templates" in resp.content
    assert b"Bug Report Template" in resp.content


def test_search_with_vacations_results(tmp_path, isolated_settings):
    """When vacations storage has a match, the Vacations group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=2026-08")

    assert resp.status_code == 200
    assert b"Vacations" in resp.content
    assert b"2026-08-01" in resp.content


def test_search_with_appointments_results(tmp_path, isolated_settings):
    """When appointments storage has a match, the Appointments group appears."""
    from unittest.mock import MagicMock, patch

    from core.state import reset_storage
    from fastapi.testclient import TestClient

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

    with (
        patch("main.get_storage", return_value=mock_storage),
        patch("core.module_repos.get_primary_store", side_effect=fake_get_primary),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = c.get("/search?q=kubecon")

    assert resp.status_code == 200
    assert b"Appointments" in resp.content
    assert b"KubeCon Conference" in resp.content


class TestProviderTable:
    """The provider table replaced twelve near-identical if-blocks. What the
    blocks could not get wrong — a typo'd module key silently disabling a
    module's search — is now checkable."""

    def test_provider_modules_are_real_and_unique(self):
        from core.global_search import PROVIDERS
        from core.settings_store import DEFAULTS

        names = [p.module for p in PROVIDERS]
        assert len(names) == len(set(names))
        unknown = [n for n in names if n not in DEFAULTS["modules_enabled"]]
        assert unknown == [], f"{unknown} is not a module, so modules_enabled.get() would always default to True"

    def test_modules_without_a_provider_are_the_expected_ones(self):
        from core.global_search import PROVIDERS
        from core.settings_store import DEFAULTS

        # These hold images or single-line texts; there is nothing to search.
        assert set(DEFAULTS["modules_enabled"]) - {p.module for p in PROVIDERS} == {"motd", "potd", "memes", "rss"}

    def test_a_failing_provider_does_not_break_the_page(self):
        from unittest.mock import patch

        from core.global_search import PROVIDERS, Provider, run_global_search

        def boom(query):
            raise RuntimeError("storage down")

        good = Provider("tasks", "x", "Tasks", "/tasks", lambda q: [{"title": "t", "url": "/tasks"}])
        with patch("core.global_search.PROVIDERS", (Provider("notes", "x", "Notes", "/notes", boom), good)):
            groups = run_global_search("q", "", "", {}, object())
        assert [g["module"] for g in groups] == ["tasks"]
        assert PROVIDERS  # table itself untouched

    def test_results_are_capped_per_module(self):
        from unittest.mock import patch

        from core.global_search import MAX_RESULTS_PER_MODULE, Provider, run_global_search

        many = [{"title": str(i), "url": "/tasks"} for i in range(50)]
        with patch("core.global_search.PROVIDERS", (Provider("tasks", "x", "Tasks", "/tasks", lambda q: many),)):
            groups = run_global_search("unique-query-for-cap-test", "", "", {}, object())
        assert len(groups[0]["results"]) == MAX_RESULTS_PER_MODULE


class TestKnowledgeResultFields:
    """Two silent-fallback bugs lived here: the knowledge provider read keys
    that GitStorage.search() never returns, so the date filter passed
    everything through and every result rendered without context."""

    def _query(self, results, date_from="", date_to=""):
        from unittest.mock import MagicMock

        from core.global_search import Query, _search_knowledge

        storage = MagicMock()
        storage.search.return_value = results
        return _search_knowledge(Query(q="needle", date_from=date_from, date_to=date_to, storage=storage))

    def test_search_results_carry_created_so_the_date_filter_applies(self):
        from core.storage import GitStorage

        # The field the filter reads has to exist on the producing side.
        source = inspect.getsource(GitStorage.search)
        assert '"created"' in source, "search() must return created, or the /search date filter is a no-op"

    def test_entry_outside_the_date_range_is_dropped(self):
        old = {"repo_id": "r1", "title": "Old", "category": "c", "slug": "s", "snippet": "x", "created": "2026-01-01"}
        assert self._query([old]) != []
        assert self._query([old], date_from="2026-06-01") == []

    def test_entry_without_a_date_is_kept(self):
        """Older cached results predate the created field; dropping them would
        make the search look broken after an upgrade."""
        undated = {"repo_id": "r1", "title": "Undated", "category": "c", "slug": "s", "snippet": "x"}
        assert self._query([undated], date_from="2026-06-01") != []

    def test_snippet_is_highlighted_from_the_search_excerpt(self):
        entry = {
            "repo_id": "r1",
            "title": "T",
            "category": "c",
            "slug": "s",
            "snippet": "find lines with needle in them",
            "created": "2026-01-01",
        }
        result = self._query([entry])[0]
        assert result["snippet"] == "find lines with <mark>needle</mark> in them"


class TestLinkSections:
    """Links live in user-defined sections (links/{section}/). The provider used
    LinkStorage's default section, so every link the user had filed anywhere
    else was invisible to the global search — no error, just no result."""

    def test_all_sections_are_searched(self):
        from unittest.mock import MagicMock, patch

        from core.global_search import Query, _search_links

        by_section = {
            "default": [{"id": "1", "title": "in default", "url": "https://a", "created": "2026-01-01"}],
            "work": [{"id": "2", "title": "in work", "url": "https://b", "created": "2026-01-01"}],
        }

        class FakeLinkStorage:
            def __init__(self, store, section_id="default"):
                self._section = section_id

            def list_links(self, query=""):
                return by_section.get(self._section, [])

        with (
            patch("modules.links.storage.LinkStorage", FakeLinkStorage),
            patch(
                "core.settings_store.get_link_sections",
                return_value=[{"id": "default"}, {"id": "work"}],
            ),
            patch("core.global_search.get_primary_store", return_value=MagicMock()),
        ):
            results = _search_links(Query(q="in", date_from="", date_to="", storage=MagicMock()))

        assert sorted(r["title"] for r in results) == ["in default", "in work"]

    def test_a_link_in_two_sections_is_listed_once(self):
        from unittest.mock import MagicMock, patch

        from core.global_search import Query, _search_links

        same = [{"id": "1", "title": "shared", "url": "https://a", "created": "2026-01-01"}]

        class FakeLinkStorage:
            def __init__(self, store, section_id="default"):
                pass

            def list_links(self, query=""):
                return same

        with (
            patch("modules.links.storage.LinkStorage", FakeLinkStorage),
            patch(
                "core.settings_store.get_link_sections",
                return_value=[{"id": "default"}, {"id": "work"}],
            ),
            patch("core.global_search.get_primary_store", return_value=MagicMock()),
        ):
            results = _search_links(Query(q="shared", date_from="", date_to="", storage=MagicMock()))

        assert len(results) == 1
