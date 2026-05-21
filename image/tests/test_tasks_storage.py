"""Tests for TaskStorage and helper functions."""

import os
import sys
from datetime import date, timedelta

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


@pytest.fixture()
def storage(tmp_path):
    from modules.tasks.storage import TaskStorage
    return TaskStorage(FakeGit(tmp_path))


# ── _next_due ──────────────────────────────────────────────────────────────

def test_next_due_daily():
    from modules.tasks.storage import _next_due
    result = _next_due("2026-04-15", "daily")
    assert result == "2026-04-16"


def test_next_due_weekly():
    from modules.tasks.storage import _next_due
    result = _next_due("2026-04-15", "weekly")
    assert result == "2026-04-22"


def test_next_due_monthly():
    from modules.tasks.storage import _next_due
    result = _next_due("2026-01-31", "monthly")
    assert result == "2026-02-28"  # Feb has 28 days in 2026


def test_next_due_monthly_normal():
    from modules.tasks.storage import _next_due
    result = _next_due("2026-04-10", "monthly")
    assert result == "2026-05-10"


def test_next_due_invalid_date():
    from modules.tasks.storage import _next_due
    # Falls back to today + interval — just check it returns a valid date string
    result = _next_due("not-a-date", "daily")
    expected = (date.today() + timedelta(days=1)).isoformat()
    assert result == expected


# ── _task_sort_key ─────────────────────────────────────────────────────────

def test_sort_key_done_last():
    from modules.tasks.storage import _task_sort_key
    done = _task_sort_key({"done": True, "due_date": "2026-01-01", "priority": "high"})
    not_done = _task_sort_key({"done": False, "due_date": "2026-12-31", "priority": "low"})
    assert not_done < done


def test_sort_key_priority_order():
    from modules.tasks.storage import _task_sort_key
    high = _task_sort_key({"done": False, "due_date": "2026-04-15", "priority": "high"})
    medium = _task_sort_key({"done": False, "due_date": "2026-04-15", "priority": "medium"})
    low = _task_sort_key({"done": False, "due_date": "2026-04-15", "priority": "low"})
    assert high < medium < low


# ── TaskStorage CRUD ───────────────────────────────────────────────────────

def test_list_empty(storage):
    assert storage.list_tasks() == []


def test_create_and_list(storage):
    t = storage.create_task({"title": "Write tests", "priority": "high"})
    assert t["title"] == "Write tests"
    assert t["priority"] == "high"
    assert t["done"] is False
    assert "id" in t
    assert "created" in t
    tasks = storage.list_tasks()
    assert len(tasks) == 1


def test_get_task(storage):
    t = storage.create_task({"title": "Fetch me"})
    fetched = storage.get_task(t["id"])
    assert fetched is not None
    assert fetched["title"] == "Fetch me"


def test_get_task_missing(storage):
    assert storage.get_task("doesnotexist") is None


def test_update_task(storage):
    t = storage.create_task({"title": "Old title", "priority": "low"})
    updated = storage.update_task(t["id"], {"title": "New title", "priority": "high"})
    assert updated["title"] == "New title"
    assert updated["priority"] == "high"


def test_update_task_missing(storage):
    assert storage.update_task("ghost", {"title": "x"}) is None


def test_delete_task(storage):
    t = storage.create_task({"title": "Bye"})
    assert storage.delete_task(t["id"]) is True
    assert storage.get_task(t["id"]) is None


def test_delete_task_missing(storage):
    assert storage.delete_task("ghost") is False


def test_toggle_done(storage):
    t = storage.create_task({"title": "Toggle me"})
    assert t["done"] is False
    toggled = storage.toggle_done(t["id"])
    assert toggled["done"] is True
    toggled_back = storage.toggle_done(t["id"])
    assert toggled_back["done"] is False


def test_toggle_done_missing(storage):
    assert storage.toggle_done("ghost") is None


# ── Recurring tasks ────────────────────────────────────────────────────────

def test_recurring_followup_created_on_toggle(storage):
    t = storage.create_task({
        "title": "Daily standup",
        "due_date": "2026-04-15",
        "recurring": "daily",
    })
    storage.toggle_done(t["id"])
    tasks = storage.list_tasks()
    # Original (done) + new followup
    assert len(tasks) == 2
    open_tasks = [x for x in tasks if not x["done"]]
    assert len(open_tasks) == 1
    assert open_tasks[0]["due_date"] == "2026-04-16"
    assert open_tasks[0]["recurring"] == "daily"


def test_no_followup_for_non_recurring(storage):
    t = storage.create_task({"title": "One-off", "recurring": "none"})
    storage.toggle_done(t["id"])
    tasks = storage.list_tasks()
    assert len(tasks) == 1


# ── Sort order ─────────────────────────────────────────────────────────────

def test_list_sorted_by_done_then_due_then_priority(storage):
    storage.create_task({"title": "Low prio", "due_date": "2026-04-20", "priority": "low"})
    storage.create_task({"title": "High prio", "due_date": "2026-04-20", "priority": "high"})
    storage.create_task({"title": "Earlier", "due_date": "2026-04-15", "priority": "low"})
    tasks = storage.list_tasks()
    assert tasks[0]["title"] == "Earlier"
    assert tasks[1]["title"] == "High prio"
    assert tasks[2]["title"] == "Low prio"


# ── Commit messages ────────────────────────────────────────────────────────

def test_commit_on_create(storage):
    storage.create_task({"title": "My task"})
    assert any("add" in m and "My task" in m for m in storage._git._committed)


def test_commit_on_update(storage):
    t = storage.create_task({"title": "Task"})
    storage._git._committed.clear()
    storage.update_task(t["id"], {"title": "Updated"})
    assert any("update" in m for m in storage._git._committed)


def test_commit_on_delete(storage):
    t = storage.create_task({"title": "Task"})
    storage._git._committed.clear()
    storage.delete_task(t["id"])
    assert any("delete" in m for m in storage._git._committed)


def test_commit_on_toggle_complete(storage):
    t = storage.create_task({"title": "Task"})
    storage._git._committed.clear()
    storage.toggle_done(t["id"])
    assert any("complete" in m for m in storage._git._committed)


def test_commit_on_toggle_reopen(storage):
    t = storage.create_task({"title": "Task"})
    storage.toggle_done(t["id"])
    storage._git._committed.clear()
    storage.toggle_done(t["id"])
    assert any("reopen" in m for m in storage._git._committed)


# ── done/ subdirectory structure ───────────────────────────────────────────

def test_done_task_written_to_done_subdir(storage, tmp_path):
    t = storage.create_task({"title": "Done task"})
    storage.toggle_done(t["id"])
    done_path = tmp_path / "tasks" / "done" / f"{t['id']}.yaml"
    open_path = tmp_path / "tasks" / f"{t['id']}.yaml"
    assert done_path.exists()
    assert not open_path.exists()


def test_reopened_task_moved_back_to_tasks(storage, tmp_path):
    t = storage.create_task({"title": "Reopen me"})
    storage.toggle_done(t["id"])
    storage.toggle_done(t["id"])
    done_path = tmp_path / "tasks" / "done" / f"{t['id']}.yaml"
    open_path = tmp_path / "tasks" / f"{t['id']}.yaml"
    assert open_path.exists()
    assert not done_path.exists()


def test_get_task_finds_done_task(storage):
    t = storage.create_task({"title": "Find me done"})
    storage.toggle_done(t["id"])
    fetched = storage.get_task(t["id"])
    assert fetched is not None
    assert fetched["done"] is True


def test_delete_done_task(storage, tmp_path):
    t = storage.create_task({"title": "Delete done"})
    storage.toggle_done(t["id"])
    result = storage.delete_task(t["id"])
    assert result is True
    assert storage.get_task(t["id"]) is None
    assert not (tmp_path / "tasks" / "done" / f"{t['id']}.yaml").exists()


def test_open_count_excludes_done(storage, tmp_path):
    """list_committed('tasks') non-recursive must not count done/ subdir entries."""
    storage.create_task({"title": "Open task"})
    t2 = storage.create_task({"title": "Done task"})
    storage.toggle_done(t2["id"])
    import os
    open_yamls = [
        n for n in os.listdir(tmp_path / "tasks")
        if n.endswith(".yaml")
    ]
    assert len(open_yamls) == 1
