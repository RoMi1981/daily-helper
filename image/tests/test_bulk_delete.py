"""Tests for bulk_delete_* methods across all storage classes."""

import os
import sys

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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


# ── Notes ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def note_storage(tmp_path):
    from modules.notes.storage import NoteStorage
    return NoteStorage(FakeGit(tmp_path))


def test_bulk_delete_notes_removes_files(note_storage):
    n1 = note_storage.create_note({"subject": "A", "body": ""})
    n2 = note_storage.create_note({"subject": "B", "body": ""})
    n3 = note_storage.create_note({"subject": "C", "body": ""})
    count = note_storage.bulk_delete_notes([n1["id"], n2["id"]])
    assert count == 2
    assert note_storage.get_note(n1["id"]) is None
    assert note_storage.get_note(n2["id"]) is None
    assert note_storage.get_note(n3["id"]) is not None


def test_bulk_delete_notes_empty_list(note_storage):
    note_storage.create_note({"subject": "Keep", "body": ""})
    count = note_storage.bulk_delete_notes([])
    assert count == 0
    assert len(note_storage.list_notes()) == 1


def test_bulk_delete_notes_ignores_missing(note_storage):
    n = note_storage.create_note({"subject": "Real", "body": ""})
    count = note_storage.bulk_delete_notes([n["id"], "doesnotexist"])
    assert count == 1


def test_bulk_delete_notes_single_commit(note_storage):
    n1 = note_storage.create_note({"subject": "A", "body": ""})
    n2 = note_storage.create_note({"subject": "B", "body": ""})
    before = len(note_storage._git._committed)
    note_storage.bulk_delete_notes([n1["id"], n2["id"]])
    after = len(note_storage._git._committed)
    assert after - before == 1  # only one commit for the batch


def test_bulk_delete_notes_no_commit_when_nothing_deleted(note_storage):
    before = len(note_storage._git._committed)
    note_storage.bulk_delete_notes(["ghost1", "ghost2"])
    assert len(note_storage._git._committed) == before


# ── Tasks ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def task_storage(tmp_path):
    from modules.tasks.storage import TaskStorage
    return TaskStorage(FakeGit(tmp_path))


def test_bulk_delete_tasks_removes_files(task_storage):
    t1 = task_storage.create_task({"title": "T1", "priority": "medium"})
    t2 = task_storage.create_task({"title": "T2", "priority": "low"})
    t3 = task_storage.create_task({"title": "T3", "priority": "high"})
    count = task_storage.bulk_delete_tasks([t1["id"], t2["id"]])
    assert count == 2
    assert task_storage.get_task(t1["id"]) is None
    assert task_storage.get_task(t2["id"]) is None
    assert task_storage.get_task(t3["id"]) is not None


def test_bulk_delete_tasks_empty_list(task_storage):
    task_storage.create_task({"title": "Keep", "priority": "medium"})
    count = task_storage.bulk_delete_tasks([])
    assert count == 0


def test_bulk_delete_tasks_ignores_missing(task_storage):
    t = task_storage.create_task({"title": "Real", "priority": "medium"})
    count = task_storage.bulk_delete_tasks([t["id"], "ghost"])
    assert count == 1


def test_bulk_delete_tasks_single_commit(task_storage):
    t1 = task_storage.create_task({"title": "A", "priority": "medium"})
    t2 = task_storage.create_task({"title": "B", "priority": "medium"})
    before = len(task_storage._git._committed)
    task_storage.bulk_delete_tasks([t1["id"], t2["id"]])
    assert len(task_storage._git._committed) - before == 1


def test_bulk_delete_tasks_no_commit_when_nothing_deleted(task_storage):
    before = len(task_storage._git._committed)
    task_storage.bulk_delete_tasks(["ghost"])
    assert len(task_storage._git._committed) == before


# ── Links ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def link_storage(tmp_path):
    from modules.links.storage import LinkStorage
    return LinkStorage(FakeGit(tmp_path), "default")


def test_bulk_delete_links_removes_files(link_storage):
    l1 = link_storage.create_link({"title": "L1", "url": "https://a.com"})
    l2 = link_storage.create_link({"title": "L2", "url": "https://b.com"})
    l3 = link_storage.create_link({"title": "L3", "url": "https://c.com"})
    count = link_storage.bulk_delete_links([l1["id"], l2["id"]])
    assert count == 2
    assert link_storage.get_link(l1["id"]) is None
    assert link_storage.get_link(l2["id"]) is None
    assert link_storage.get_link(l3["id"]) is not None


def test_bulk_delete_links_empty_list(link_storage):
    link_storage.create_link({"title": "Keep", "url": "https://keep.com"})
    count = link_storage.bulk_delete_links([])
    assert count == 0


def test_bulk_delete_links_ignores_missing(link_storage):
    l = link_storage.create_link({"title": "Real", "url": "https://real.com"})
    count = link_storage.bulk_delete_links([l["id"], "ghost"])
    assert count == 1


def test_bulk_delete_links_finds_in_section_subdir(tmp_path):
    """Link stored in section subdirectory (not flat) must be found and deleted."""
    from modules.links.storage import LinkStorage
    git = FakeGit(tmp_path)
    ls = LinkStorage(git, "work")
    l = ls.create_link({"title": "Work Link", "url": "https://work.example"})
    # stored in links/work/{id}.yaml
    assert (tmp_path / "links" / "work" / f"{l['id']}.yaml").exists()
    count = ls.bulk_delete_links([l["id"]])
    assert count == 1
    assert ls.get_link(l["id"]) is None


def test_bulk_delete_links_single_commit(link_storage):
    l1 = link_storage.create_link({"title": "A", "url": "https://a.com"})
    l2 = link_storage.create_link({"title": "B", "url": "https://b.com"})
    before = len(link_storage._git._committed)
    link_storage.bulk_delete_links([l1["id"], l2["id"]])
    assert len(link_storage._git._committed) - before == 1


# ── Snippets ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def snippet_storage(tmp_path):
    from modules.snippets.storage import SnippetStorage
    return SnippetStorage(FakeGit(tmp_path))


def test_bulk_delete_snippets_removes_files(snippet_storage):
    s1 = snippet_storage.create_snippet({"title": "S1", "steps": []})
    s2 = snippet_storage.create_snippet({"title": "S2", "steps": []})
    s3 = snippet_storage.create_snippet({"title": "S3", "steps": []})
    count = snippet_storage.bulk_delete_snippets([s1["id"], s2["id"]])
    assert count == 2
    assert snippet_storage.get_snippet(s1["id"]) is None
    assert snippet_storage.get_snippet(s2["id"]) is None
    assert snippet_storage.get_snippet(s3["id"]) is not None


def test_bulk_delete_snippets_empty_list(snippet_storage):
    snippet_storage.create_snippet({"title": "Keep", "steps": []})
    count = snippet_storage.bulk_delete_snippets([])
    assert count == 0


def test_bulk_delete_snippets_ignores_missing(snippet_storage):
    s = snippet_storage.create_snippet({"title": "Real", "steps": []})
    count = snippet_storage.bulk_delete_snippets([s["id"], "ghost"])
    assert count == 1


def test_bulk_delete_snippets_single_commit(snippet_storage):
    s1 = snippet_storage.create_snippet({"title": "A", "steps": []})
    s2 = snippet_storage.create_snippet({"title": "B", "steps": []})
    before = len(snippet_storage._git._committed)
    snippet_storage.bulk_delete_snippets([s1["id"], s2["id"]])
    assert len(snippet_storage._git._committed) - before == 1


# ── Runbooks ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def runbook_storage(tmp_path):
    from modules.runbooks.storage import RunbookStorage
    return RunbookStorage(FakeGit(tmp_path))


def test_bulk_delete_runbooks_removes_files(runbook_storage):
    r1 = runbook_storage.create_runbook({"title": "R1", "steps": []})
    r2 = runbook_storage.create_runbook({"title": "R2", "steps": []})
    r3 = runbook_storage.create_runbook({"title": "R3", "steps": []})
    count = runbook_storage.bulk_delete_runbooks([r1["id"], r2["id"]])
    assert count == 2
    assert runbook_storage.get_runbook(r1["id"]) is None
    assert runbook_storage.get_runbook(r2["id"]) is None
    assert runbook_storage.get_runbook(r3["id"]) is not None


def test_bulk_delete_runbooks_empty_list(runbook_storage):
    runbook_storage.create_runbook({"title": "Keep", "steps": []})
    count = runbook_storage.bulk_delete_runbooks([])
    assert count == 0


def test_bulk_delete_runbooks_ignores_missing(runbook_storage):
    r = runbook_storage.create_runbook({"title": "Real", "steps": []})
    count = runbook_storage.bulk_delete_runbooks([r["id"], "ghost"])
    assert count == 1


def test_bulk_delete_runbooks_single_commit(runbook_storage):
    r1 = runbook_storage.create_runbook({"title": "A", "steps": []})
    r2 = runbook_storage.create_runbook({"title": "B", "steps": []})
    before = len(runbook_storage._git._committed)
    runbook_storage.bulk_delete_runbooks([r1["id"], r2["id"]])
    assert len(runbook_storage._git._committed) - before == 1
