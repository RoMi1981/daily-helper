"""Integration tests for GitStorage against a real git repository.

Requires the deploy key at ~/.ssh/dh_test_deploy_key (or TEST_DEPLOY_KEY_PRIVATE env var).
The test repo contains known seed data committed beforehand.

Skipped automatically if the key is not available.
"""

import os
import sys
import shutil
import tempfile
import time

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"
os.environ["PULL_THROTTLE_SECONDS"] = "0"  # always fetch in integration tests

TEST_REPO_URL = os.environ.get(
    "TEST_REPO_URL",
    "ssh://git@gitea.nas.trabs.net:2222/Tests/daily-helper-data-test.git",
)
KEY_PATH = os.path.expanduser("~/.ssh/dh_test_deploy_key")
KEY_ENV_VAR = "TEST_DEPLOY_KEY_PRIVATE"


def _get_key_path() -> str | None:
    """Return path to deploy key, writing from env var if needed."""
    if os.path.exists(KEY_PATH):
        return KEY_PATH
    key_content = os.environ.get(KEY_ENV_VAR)
    if key_content:
        os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
        with open(KEY_PATH, "w") as f:
            f.write(key_content.strip() + "\n")
        os.chmod(KEY_PATH, 0o600)
        return KEY_PATH
    return None


_key = _get_key_path()
pytestmark = pytest.mark.skipif(
    _key is None,
    reason="Deploy key not available (set TEST_DEPLOY_KEY_PRIVATE env var or place key at ~/.ssh/dh_test_deploy_key)",
)

SETTINGS = {
    "auth_mode": "ssh",
    "ssh_key": open(_key).read() if _key else "",
    "git_user_name": "CI Test",
    "git_user_email": "ci@test.local",
    "push_retry_count": 5,
}


@pytest.fixture(autouse=True, scope="module")
def _disable_pull_throttle():
    """Disable pull throttle for all integration tests so sequential writes don't conflict."""
    import core.storage as _storage_mod
    original = _storage_mod.PULL_THROTTLE_SECONDS
    _storage_mod.PULL_THROTTLE_SECONDS = 0
    yield
    _storage_mod.PULL_THROTTLE_SECONDS = original


@pytest.fixture(scope="module")
def storage():
    """Real GitStorage instance cloned to a temp directory."""
    from core.storage import GitStorage

    orig_path_attr = GitStorage.__init__.__code__  # keep ref
    repo_id = f"integration-test-{int(time.time())}"

    # Patch local_path to use a temp dir so we don't collide with production
    tmp_base = tempfile.mkdtemp(prefix="dh-integration-")
    from pathlib import Path
    from unittest.mock import patch

    with patch.object(
        GitStorage, "__init__",
        lambda self, rid, url, settings: _patched_init(self, rid, url, settings, tmp_base),
    ):
        gs = GitStorage.__new__(GitStorage)
        _patched_init(gs, repo_id, TEST_REPO_URL, SETTINGS, tmp_base)

    yield gs

    # Cleanup local clone
    shutil.rmtree(tmp_base, ignore_errors=True)


def _patched_init(self, repo_id, repo_url, settings, tmp_base):
    """GitStorage.__init__ with custom local_path."""
    import tempfile, os
    from pathlib import Path
    from core.storage import GitStorage
    self.repo_id = repo_id
    self.repo_url = repo_url
    self.local_path = Path(tmp_base) / repo_id
    self._settings = settings
    self._ssh_key_file = None
    self._ca_cert_file = None
    self._askpass_file = None
    self._gpg_home = None
    self._gpg_key_id = None
    self._last_pull = 0.0
    self._push_retry_count = int(settings.get("push_retry_count", 1))
    self._setup_credentials()
    self._ensure_repo()


# ── read_committed / list_committed ────────────────────────────────────────

class TestListCommitted:
    def test_notes_returns_seed_file(self, storage):
        names = storage.list_committed("notes")
        assert "note-seed-001.yaml" in names

    def test_tasks_returns_seed_file(self, storage):
        names = storage.list_committed("tasks")
        assert "task-seed-001.yaml" in names

    def test_links_returns_seed_file(self, storage):
        # Seed may be flat or already migrated to links/default/
        flat = storage.list_committed("links")
        in_default = storage.list_committed("links/default")
        assert "link-seed-001.yaml" in flat or "link-seed-001.yaml" in in_default

    def test_vacations_returns_seed_file(self, storage):
        names = storage.list_committed("vacations/entries")
        assert "vac-seed-001.yaml" in names

    def test_names_are_filenames_not_paths(self, storage):
        """Must return bare filenames, not prefixed paths like 'notes/file.yaml'."""
        for name in storage.list_committed("notes"):
            assert "/" not in name, f"Expected filename, got path: {name}"

    def test_nonexistent_directory_returns_empty(self, storage):
        assert storage.list_committed("does-not-exist") == []


class TestReadCommitted:
    def test_read_note_returns_bytes(self, storage):
        raw = storage.read_committed("notes/note-seed-001.yaml")
        assert raw is not None
        assert b"note-seed-001" in raw

    def test_read_task_returns_bytes(self, storage):
        raw = storage.read_committed("tasks/task-seed-001.yaml")
        assert raw is not None
        assert b"Seed Task" in raw

    def test_read_nonexistent_returns_none(self, storage):
        assert storage.read_committed("notes/does-not-exist.yaml") is None

    def test_read_knowledge_entry(self, storage):
        raw = storage.read_committed("knowledge/Linux/bash-basics.md")
        assert raw is not None
        assert b"Bash Basics" in raw


class TestListCommittedRecursive:
    def test_knowledge_returns_all_entries(self, storage):
        paths = storage.list_committed_recursive("knowledge")
        assert "knowledge/Linux/bash-basics.md" in paths
        assert "knowledge/Python/list-comprehensions.md" in paths

    def test_paths_include_subdirectory(self, storage):
        paths = storage.list_committed_recursive("knowledge")
        for p in paths:
            assert p.startswith("knowledge/")


# ── pull / commit / push ───────────────────────────────────────────────────

class TestWriteOperations:
    """Write tests create and clean up their own entries."""

    def test_pull_succeeds(self, storage):
        storage._pull()  # should not raise

    def test_create_and_delete_note(self, storage):
        import yaml
        from pathlib import Path

        storage._pull()

        note_id = "ci-test-note-tmp"
        path = storage.local_path / "notes" / f"{note_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump({
            "id": note_id,
            "subject": "CI Test Note",
            "body": "Created by integration test",
            "created": "2026-01-01",
            "updated": "2026-01-01",
        }), encoding="utf-8")

        storage._commit_and_push(f"test: add {note_id}")

        # verify readable via read_committed
        storage._last_pull = 0  # force re-fetch
        raw = storage.read_committed(f"notes/{note_id}.yaml")
        assert raw is not None
        assert b"CI Test Note" in raw

        # cleanup
        storage._pull()
        path.unlink()
        storage._commit_and_push(f"test: remove {note_id}")

        storage._last_pull = 0
        assert storage.read_committed(f"notes/{note_id}.yaml") is None

    def test_note_appears_in_list_after_create(self, storage):
        import yaml

        storage._pull()
        note_id = "ci-test-list-tmp"
        path = storage.local_path / "notes" / f"{note_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump({"id": note_id, "subject": "List Test"}), encoding="utf-8")
        storage._commit_and_push(f"test: add {note_id}")

        storage._last_pull = 0
        names = storage.list_committed("notes")
        assert f"{note_id}.yaml" in names

        # cleanup
        storage._pull()
        path.unlink()
        storage._commit_and_push(f"test: remove {note_id}")


# ── NoteStorage / TaskStorage end-to-end ──────────────────────────────────

class TestNoteStorageIntegration:
    @pytest.fixture()
    def note_storage(self, storage):
        from modules.notes.storage import NoteStorage
        return NoteStorage(storage)

    def test_list_notes_contains_seed(self, note_storage):
        notes = note_storage.list_notes()
        assert any(n["id"] == "note-seed-001" for n in notes)

    def test_get_note_seed(self, note_storage):
        note = note_storage.get_note("note-seed-001")
        assert note is not None
        assert note["subject"] == "Seed Note"

    def test_get_note_missing_returns_none(self, note_storage):
        assert note_storage.get_note("does-not-exist") is None

    def test_create_update_delete(self, note_storage):
        note = note_storage.create_note({"subject": "Integration Create", "body": "body"})
        nid = note["id"]

        fetched = note_storage.get_note(nid)
        assert fetched is not None
        assert fetched["subject"] == "Integration Create"

        updated = note_storage.update_note(nid, {"subject": "Integration Updated"})
        assert updated["subject"] == "Integration Updated"

        assert note_storage.delete_note(nid) is True
        assert note_storage.get_note(nid) is None

    def test_search_finds_seed(self, note_storage):
        results = note_storage.list_notes(query="seed")
        assert any(n["id"] == "note-seed-001" for n in results)


class TestTaskStorageIntegration:
    @pytest.fixture()
    def task_storage(self, storage):
        from modules.tasks.storage import TaskStorage
        return TaskStorage(storage)

    def test_list_tasks_contains_seed(self, task_storage):
        tasks = task_storage.list_tasks()
        assert any(t["id"] == "task-seed-001" for t in tasks)

    def test_get_task_seed(self, task_storage):
        task = task_storage.get_task("task-seed-001")
        assert task is not None
        assert task["title"] == "Seed Task"

    def test_get_task_missing_returns_none(self, task_storage):
        assert task_storage.get_task("does-not-exist") is None

    def test_create_toggle_delete(self, task_storage):
        task = task_storage.create_task({"title": "Integration Task", "priority": "high"})
        tid = task["id"]

        toggled = task_storage.toggle_done(tid)
        assert toggled["done"] is True

        assert task_storage.delete_task(tid) is True
        assert task_storage.get_task(tid) is None

    def test_create_update_task(self, task_storage):
        task = task_storage.create_task({"title": "Update Me", "priority": "low"})
        tid = task["id"]
        updated = task_storage.update_task(tid, {"title": "Updated Title", "priority": "high"})
        assert updated["title"] == "Updated Title"
        assert updated["priority"] == "high"
        task_storage.delete_task(tid)

    def test_delete_missing_returns_false(self, task_storage):
        assert task_storage.delete_task("does-not-exist") is False

    def test_toggle_missing_returns_none(self, task_storage):
        assert task_storage.toggle_done("does-not-exist") is None

    def test_list_sorted_done_last(self, task_storage):
        t1 = task_storage.create_task({"title": "Open Task"})
        t2 = task_storage.create_task({"title": "Done Task"})
        task_storage.toggle_done(t2["id"])
        tasks = task_storage.list_tasks()
        ids = [t["id"] for t in tasks]
        assert ids.index(t1["id"]) < ids.index(t2["id"])
        task_storage.delete_task(t1["id"])
        task_storage.delete_task(t2["id"])


# ── LinkStorage ────────────────────────────────────────────────────────────

class TestLinkStorageIntegration:
    @pytest.fixture()
    def link_storage(self, storage):
        from modules.links.storage import LinkStorage
        from modules.links.migration import migrate_flat_to_section
        # Migrate flat links/*.yaml → links/default/ if not done yet
        migrate_flat_to_section(storage, "default")
        return LinkStorage(storage, "default")

    def test_list_contains_seed(self, link_storage):
        links = link_storage.list_links()
        assert any(l["id"] == "link-seed-001" for l in links)

    def test_get_seed(self, link_storage):
        link = link_storage.get_link("link-seed-001")
        assert link is not None
        assert link["title"] == "Gitea"
        assert link["category"] == "Tools"

    def test_get_missing_returns_none(self, link_storage):
        assert link_storage.get_link("does-not-exist") is None

    def test_get_categories_contains_tools(self, link_storage):
        cats = link_storage.get_categories()
        assert "Tools" in cats

    def test_search_by_title(self, link_storage):
        results = link_storage.list_links(query="gitea")
        assert any(l["id"] == "link-seed-001" for l in results)

    def test_filter_by_category(self, link_storage):
        results = link_storage.list_links(category="Tools")
        assert any(l["id"] == "link-seed-001" for l in results)

    def test_filter_no_match(self, link_storage):
        assert link_storage.list_links(category="Nonexistent") == []

    def test_create_update_delete(self, link_storage):
        link = link_storage.create_link({
            "title": "Example", "url": "https://example.com",
            "category": "Test", "description": "desc",
        })
        lid = link["id"]
        assert link_storage.get_link(lid)["title"] == "Example"

        updated = link_storage.update_link(lid, {"title": "Example Updated"})
        assert updated["title"] == "Example Updated"

        assert link_storage.delete_link(lid) is True
        assert link_storage.get_link(lid) is None

    def test_delete_missing_returns_false(self, link_storage):
        assert link_storage.delete_link("does-not-exist") is False

    def test_sorted_by_category_then_title(self, link_storage):
        l1 = link_storage.create_link({"title": "B Link", "url": "https://b.com", "category": "AAA"})
        l2 = link_storage.create_link({"title": "A Link", "url": "https://a.com", "category": "AAA"})
        links = link_storage.list_links(category="AAA")
        titles = [l["title"] for l in links]
        assert titles.index("A Link") < titles.index("B Link")
        link_storage.delete_link(l1["id"])
        link_storage.delete_link(l2["id"])


# ── VacationStorage ────────────────────────────────────────────────────────

class TestVacationStorageIntegration:
    @pytest.fixture()
    def vac_storage(self, storage):
        from modules.vacations.storage import VacationStorage
        return VacationStorage(storage)

    def test_list_contains_seed(self, vac_storage):
        entries = vac_storage.list_entries()
        assert any(e["id"] == "vac-seed-001" for e in entries)

    def test_get_seed(self, vac_storage):
        entry = vac_storage.get_entry("vac-seed-001")
        assert entry is not None
        assert entry["status"] == "approved"
        assert entry["start_date"] == "2026-07-01"

    def test_get_missing_returns_none(self, vac_storage):
        assert vac_storage.get_entry("does-not-exist") is None

    def test_filter_by_year(self, vac_storage):
        entries_2026 = vac_storage.list_entries(year=2026)
        assert any(e["id"] == "vac-seed-001" for e in entries_2026)
        entries_2025 = vac_storage.list_entries(year=2025)
        assert not any(e["id"] == "vac-seed-001" for e in entries_2025)

    def test_create_update_status_delete(self, vac_storage):
        entry = vac_storage.create_entry({
            "start_date": "2026-09-01", "end_date": "2026-09-05", "note": "CI test",
        })
        eid = entry["id"]
        assert entry["status"] == "planned"

        updated = vac_storage.update_status(eid, "approved")
        assert updated["status"] == "approved"

        assert vac_storage.delete_entry(eid) is True
        assert vac_storage.get_entry(eid) is None

    def test_update_entry_fields(self, vac_storage):
        entry = vac_storage.create_entry({
            "start_date": "2026-10-01", "end_date": "2026-10-03",
        })
        eid = entry["id"]
        updated = vac_storage.update_entry(eid, {
            "start_date": "2026-10-02", "end_date": "2026-10-04", "note": "updated",
        })
        assert updated["start_date"] == "2026-10-02"
        assert updated["note"] == "updated"
        vac_storage.delete_entry(eid)

    def test_delete_missing_returns_false(self, vac_storage):
        assert vac_storage.delete_entry("does-not-exist") is False

    def test_account_includes_approved_seed(self, vac_storage):
        account = vac_storage.get_account(year=2026, total_days=30, state="BY")
        assert account["used_days"] > 0  # seed has approved entry in 2026

    def test_sorted_by_start_date(self, vac_storage):
        e1 = vac_storage.create_entry({"start_date": "2026-11-10", "end_date": "2026-11-11"})
        e2 = vac_storage.create_entry({"start_date": "2026-11-01", "end_date": "2026-11-02"})
        entries = vac_storage.list_entries(year=2026)
        dates = [e["start_date"] for e in entries]
        assert dates.index("2026-11-01") < dates.index("2026-11-10")
        vac_storage.delete_entry(e1["id"])
        vac_storage.delete_entry(e2["id"])


# ── AppointmentStorage ─────────────────────────────────────────────────────

class TestAppointmentStorageIntegration:
    @pytest.fixture()
    def appt_storage(self, storage):
        from modules.appointments.storage import AppointmentStorage
        return AppointmentStorage(storage)

    def test_list_contains_seed(self, appt_storage):
        entries = appt_storage.list_entries()
        assert any(e["id"] == "appt-seed-001" for e in entries)

    def test_get_seed(self, appt_storage):
        entry = appt_storage.get_entry("appt-seed-001")
        assert entry is not None
        assert entry["title"] == "Team Workshop"
        assert entry["type"] == "team_event"

    def test_get_missing_returns_none(self, appt_storage):
        assert appt_storage.get_entry("does-not-exist") is None

    def test_create_update_delete(self, appt_storage):
        entry = appt_storage.create_entry({
            "title": "CI Training", "start_date": "2026-08-01",
            "end_date": "2026-08-02", "type": "training",
        })
        eid = entry["id"]
        assert appt_storage.get_entry(eid)["title"] == "CI Training"

        updated = appt_storage.update_entry(eid, {"title": "CI Training Updated", "note": "updated"})
        assert updated["title"] == "CI Training Updated"

        assert appt_storage.delete_entry(eid) is True
        assert appt_storage.get_entry(eid) is None

    def test_delete_missing_returns_false(self, appt_storage):
        assert appt_storage.delete_entry("does-not-exist") is False

    def test_filter_by_year(self, appt_storage):
        entries = appt_storage.list_entries(year=2026)
        assert any(e["id"] == "appt-seed-001" for e in entries)
        assert appt_storage.list_entries(year=2025) == []


# ── RunbookStorage ─────────────────────────────────────────────────────────

class TestRunbookStorageIntegration:
    @pytest.fixture()
    def rb_storage(self, storage):
        from modules.runbooks.storage import RunbookStorage
        return RunbookStorage(storage)

    def test_list_contains_seed(self, rb_storage):
        runbooks = rb_storage.list_runbooks()
        assert any(r["id"] == "runbook-seed-001" for r in runbooks)

    def test_get_seed(self, rb_storage):
        rb = rb_storage.get_runbook("runbook-seed-001")
        assert rb is not None
        assert rb["title"] == "Deploy Checklist"
        assert len(rb["steps"]) == 2

    def test_get_missing_returns_none(self, rb_storage):
        assert rb_storage.get_runbook("does-not-exist") is None

    def test_create_update_delete(self, rb_storage):
        rb = rb_storage.create_runbook({
            "title": "CI Runbook",
            "description": "Test runbook",
            "steps": [{"title": "Step 1", "body": "do something"}],
        })
        rid = rb["id"]
        assert rb_storage.get_runbook(rid)["title"] == "CI Runbook"

        updated = rb_storage.update_runbook(rid, {"title": "CI Runbook Updated"})
        assert updated["title"] == "CI Runbook Updated"

        assert rb_storage.delete_runbook(rid) is True
        assert rb_storage.get_runbook(rid) is None

    def test_delete_missing_returns_false(self, rb_storage):
        assert rb_storage.delete_runbook("does-not-exist") is False


# ── MailTemplateStorage ────────────────────────────────────────────────────

class TestMailTemplateStorageIntegration:
    @pytest.fixture()
    def mail_storage(self, storage):
        from modules.mail_templates.storage import MailTemplateStorage
        return MailTemplateStorage(storage)

    def test_list_contains_seed(self, mail_storage):
        templates = mail_storage.list_templates()
        assert any(t["id"] == "mail-seed-001" for t in templates)

    def test_get_seed(self, mail_storage):
        tmpl = mail_storage.get_template("mail-seed-001")
        assert tmpl is not None
        assert tmpl["name"] == "Meeting Request"
        assert tmpl["to"] == "team@example.com"

    def test_get_missing_returns_none(self, mail_storage):
        assert mail_storage.get_template("does-not-exist") is None

    def test_create_update_delete(self, mail_storage):
        tmpl = mail_storage.create_template({
            "name": "CI Mail", "to": "ci@test.local",
            "subject": "CI Subject", "body": "CI Body",
        })
        tid = tmpl["id"]
        assert mail_storage.get_template(tid)["name"] == "CI Mail"

        updated = mail_storage.update_template(tid, {"name": "CI Mail Updated"})
        assert updated["name"] == "CI Mail Updated"

        assert mail_storage.delete_template(tid) is True
        assert mail_storage.get_template(tid) is None

    def test_delete_missing_returns_false(self, mail_storage):
        assert mail_storage.delete_template("does-not-exist") is False


# ── TicketTemplateStorage ──────────────────────────────────────────────────

class TestTicketTemplateStorageIntegration:
    @pytest.fixture()
    def ticket_storage(self, storage):
        from modules.ticket_templates.storage import TicketTemplateStorage
        return TicketTemplateStorage(storage)

    def test_list_contains_seed(self, ticket_storage):
        templates = ticket_storage.list_templates()
        assert any(t["id"] == "ticket-seed-001" for t in templates)

    def test_get_seed(self, ticket_storage):
        tmpl = ticket_storage.get_template("ticket-seed-001")
        assert tmpl is not None
        assert tmpl["name"] == "Bug Report"

    def test_get_missing_returns_none(self, ticket_storage):
        assert ticket_storage.get_template("does-not-exist") is None

    def test_create_update_delete(self, ticket_storage):
        tmpl = ticket_storage.create_template({
            "name": "CI Ticket", "description": "Desc", "body": "Body",
        })
        tid = tmpl["id"]
        assert ticket_storage.get_template(tid)["name"] == "CI Ticket"

        updated = ticket_storage.update_template(tid, {"name": "CI Ticket Updated"})
        assert updated["name"] == "CI Ticket Updated"

        assert ticket_storage.delete_template(tid) is True
        assert ticket_storage.get_template(tid) is None

    def test_delete_missing_returns_false(self, ticket_storage):
        assert ticket_storage.delete_template("does-not-exist") is False


# ── GitStorage Knowledge ───────────────────────────────────────────────────

class TestKnowledgeStorageIntegration:
    def test_get_categories(self, storage):
        cats = storage.get_categories()
        assert "Linux" in cats
        assert "Python" in cats

    def test_get_entries_all(self, storage):
        entries = storage.get_entries()
        slugs = [e["slug"] for e in entries]
        assert "bash-basics" in slugs
        assert "list-comprehensions" in slugs

    def test_get_entries_by_category(self, storage):
        entries = storage.get_entries(category="Linux")
        assert all(e["category"] == "Linux" for e in entries)
        assert any(e["slug"] == "bash-basics" for e in entries)

    def test_get_entry(self, storage):
        entry = storage.get_entry("Linux", "bash-basics")
        assert entry is not None
        assert entry["title"] == "Bash Basics"
        assert "Basic bash" in entry["content"]

    def test_get_entry_missing_returns_none(self, storage):
        assert storage.get_entry("Linux", "does-not-exist") is None

    def test_save_and_delete_entry(self, storage):
        storage.save_entry("Linux", "CI Test Entry", "Test content for CI.")
        entry = storage.get_entry("Linux", "ci-test-entry")
        assert entry is not None
        assert entry["title"] == "CI Test Entry"

        assert storage.delete_entry("Linux", "ci-test-entry") is True
        assert storage.get_entry("Linux", "ci-test-entry") is None

    def test_update_entry(self, storage):
        storage.save_entry("Linux", "CI Update Test", "Original content.")
        storage.update_entry("Linux", "ci-update-test", "CI Update Test", "Updated content.")
        entry = storage.get_entry("Linux", "ci-update-test")
        assert "Updated content" in entry["content"]
        storage.delete_entry("Linux", "ci-update-test")

    def test_toggle_pin(self, storage):
        storage.save_entry("Linux", "CI Pin Test", "Pinnable entry.")
        result = storage.toggle_pin("Linux", "ci-pin-test")
        assert result["pinned"] is True

        result2 = storage.toggle_pin("Linux", "ci-pin-test")
        assert result2["pinned"] is False

        storage.delete_entry("Linux", "ci-pin-test")

    def test_search(self, storage):
        results = storage.search("bash")
        assert any(e["slug"] == "bash-basics" for e in results)

    def test_pinned_entry_appears_in_list(self, storage):
        entries = storage.get_entries()
        pinned = [e for e in entries if e.get("pinned")]
        # list-comprehensions seed is pinned=true
        assert any(e["slug"] == "list-comprehensions" for e in pinned)


# ── SnippetStorage ────────────────────────────────────────────────────────

class TestSnippetStorageIntegration:
    @pytest.fixture()
    def snippet_storage(self, storage):
        from modules.snippets.storage import SnippetStorage
        return SnippetStorage(storage)

    def test_list_is_list(self, snippet_storage):
        result = snippet_storage.list_snippets()
        assert isinstance(result, list)

    def test_get_missing_returns_none(self, snippet_storage):
        assert snippet_storage.get_snippet("does-not-exist") is None

    def test_create_update_delete(self, snippet_storage):
        sn = snippet_storage.create_snippet({
            "title": "CI Snippet",
            "description": "Integration test snippet",
            "steps": [
                {"description": "Show pods", "command": "kubectl get pods"},
                {"description": "", "command": "kubectl describe pod $POD"},
            ],
        })
        sid = sn["id"]

        got = snippet_storage.get_snippet(sid)
        assert got is not None
        assert got["title"] == "CI Snippet"
        assert len(got["steps"]) == 2
        assert got["steps"][0]["command"] == "kubectl get pods"

        updated = snippet_storage.update_snippet(sid, {"title": "CI Snippet Updated"})
        assert updated["title"] == "CI Snippet Updated"

        assert snippet_storage.delete_snippet(sid) is True
        assert snippet_storage.get_snippet(sid) is None

    def test_delete_missing_returns_false(self, snippet_storage):
        assert snippet_storage.delete_snippet("does-not-exist") is False

    def test_search_by_title(self, snippet_storage):
        sn = snippet_storage.create_snippet({
            "title": "CI Search Unique XYZ",
            "steps": [{"command": "echo hi"}],
        })
        results = snippet_storage.list_snippets(query="unique xyz")
        assert any(s["id"] == sn["id"] for s in results)
        snippet_storage.delete_snippet(sn["id"])

    def test_search_by_step_command(self, snippet_storage):
        sn = snippet_storage.create_snippet({
            "title": "CI Step Search",
            "steps": [{"command": "git log --unique-ci-marker"}],
        })
        results = snippet_storage.list_snippets(query="unique-ci-marker")
        assert any(s["id"] == sn["id"] for s in results)
        snippet_storage.delete_snippet(sn["id"])
