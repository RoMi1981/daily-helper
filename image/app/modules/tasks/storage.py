"""Task storage — YAML files in tasks/ subdirectory of the data repo."""

import logging
import uuid
from datetime import date, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, None: 3, "": 3}


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _task_sort_key(t: dict) -> tuple:
    done = t.get("done", False)
    due = t.get("due_date") or "9999-99-99"
    prio = _PRIORITY_ORDER.get(t.get("priority"), 3)
    return (done, due, prio)


def _next_due(due_date: str, recurring: str) -> str:
    """Calculate next due date based on recurring interval."""
    try:
        d = date.fromisoformat(due_date)
    except (ValueError, TypeError):
        d = date.today()

    if recurring == "daily":
        d += timedelta(days=1)
    elif recurring == "weekly":
        d += timedelta(weeks=1)
    elif recurring == "monthly":
        import calendar as _cal

        month = d.month + 1
        year = d.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(d.day, _cal.monthrange(year, month)[1])
        d = date(year, month, day)

    return d.isoformat()


class TaskStorage:
    """Manages tasks/{id}.yaml (open) and tasks/done/{id}.yaml (done)."""

    # Class-level: tracks repos already checked this process lifetime
    _migrated_repos: set[str] = set()

    def __init__(self, git_storage):
        self._git = git_storage
        self._tasks_dir = Path(git_storage.local_path) / "tasks"
        self._maybe_migrate()

    def _maybe_migrate(self):
        """Migrate flat done tasks (tasks/{id}.yaml with done:true) to tasks/done/."""
        repo_id = getattr(self._git, "repo_id", None)
        if repo_id in TaskStorage._migrated_repos:
            return
        TaskStorage._migrated_repos.add(repo_id)

        if not self._tasks_dir.exists():
            return

        to_migrate = []
        for f in self._tasks_dir.iterdir():
            if not (f.is_file() and f.suffix == ".yaml"):
                continue
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("done"):
                    to_migrate.append((f, data))
            except Exception:
                pass

        if not to_migrate:
            return

        logger.info("Migrating %d done task(s) to tasks/done/ in repo %s", len(to_migrate), repo_id)
        self._git._pull()
        done_dir = self._tasks_dir / "done"
        done_dir.mkdir(exist_ok=True)
        for old_path, task in to_migrate:
            new_path = done_dir / old_path.name
            new_path.write_text(
                yaml.dump(task, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            old_path.unlink()
        self._git._commit_and_push(
            f"tasks: migrate {len(to_migrate)} done task(s) to done/ subdirectory"
        )

    def _path(self, task_id: str, done: bool) -> Path:
        if done:
            return self._tasks_dir / "done" / f"{task_id}.yaml"
        return self._tasks_dir / f"{task_id}.yaml"

    def _write_task(self, task: dict):
        path = self._path(task["id"], task.get("done", False))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump(task, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def _remove_task_file(self, task_id: str):
        """Delete task file from whichever location it exists."""
        for p in [
            self._tasks_dir / f"{task_id}.yaml",
            self._tasks_dir / "done" / f"{task_id}.yaml",
        ]:
            if p.exists():
                p.unlink()

    def search_tasks(self, query: str) -> list[dict]:
        q = query.lower()
        return [
            t
            for t in self.list_tasks()
            if q in t.get("title", "").lower() or q in t.get("description", "").lower()
        ]

    def list_tasks(self) -> list[dict]:
        tasks = []
        for prefix, git_prefix in [("tasks", "tasks"), ("tasks/done", "tasks/done")]:
            for name in self._git.list_committed(prefix):
                if not name.endswith(".yaml"):
                    continue
                raw = self._git.read_committed(f"{git_prefix}/{name}")
                if raw is None:
                    continue
                t = yaml.safe_load(raw.decode("utf-8"))
                if isinstance(t, dict):
                    tasks.append(t)
        return sorted(tasks, key=_task_sort_key)

    def get_task(self, task_id: str) -> dict | None:
        for prefix in [f"tasks/{task_id}.yaml", f"tasks/done/{task_id}.yaml"]:
            raw = self._git.read_committed(prefix)
            if raw is not None:
                data = yaml.safe_load(raw.decode("utf-8"))
                return data if isinstance(data, dict) else None
        return None

    def create_task(self, data: dict) -> dict:
        task = {
            "id": _new_id(),
            "title": data.get("title", "").strip(),
            "description": data.get("description", "").strip(),
            "due_date": data.get("due_date", ""),
            "priority": data.get("priority", "medium"),
            "done": False,
            "recurring": data.get("recurring", "none"),
            "blocked_by": [b for b in data.get("blocked_by", []) if b],
            "created": date.today().isoformat(),
        }
        self._git._pull()
        self._write_task(task)
        self._git._commit_and_push(f"tasks: add '{task['title']}'")
        return task

    def update_task(self, task_id: str, data: dict) -> dict | None:
        task = self.get_task(task_id)
        if not task:
            return None
        task.update(
            {
                "title": data.get("title", task["title"]).strip(),
                "description": data.get("description", task.get("description", "")).strip(),
                "due_date": data.get("due_date", task.get("due_date", "")),
                "priority": data.get("priority", task.get("priority", "medium")),
                "recurring": data.get("recurring", task.get("recurring", "none")),
                "blocked_by": [b for b in data.get("blocked_by", task.get("blocked_by", [])) if b],
            }
        )
        self._git._pull()
        self._write_task(task)
        self._git._commit_and_push(f"tasks: update '{task['title']}'")
        return task

    def toggle_done(self, task_id: str) -> dict | None:
        task = self.get_task(task_id)
        if not task:
            return None
        task["done"] = not task.get("done", False)
        if task["done"] and task.get("recurring", "none") != "none":
            self._create_recurring_followup(task)
        self._git._pull()
        self._remove_task_file(task_id)  # remove from old location
        self._write_task(task)  # write to new location
        action = "complete" if task["done"] else "reopen"
        self._git._commit_and_push(f"tasks: {action} '{task['title']}'")
        return task

    def delete_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        title = task.get("title", task_id)
        self._git._pull()
        self._remove_task_file(task_id)
        self._git._commit_and_push(f"tasks: delete '{title}'")
        return True

    def bulk_delete_tasks(self, task_ids: list[str]) -> int:
        if not task_ids:
            return 0
        self._git._pull()
        deleted = 0
        for tid in task_ids:
            if self.get_task(tid) is not None:
                self._remove_task_file(tid)
                deleted += 1
        if deleted:
            self._git._commit_and_push(f"tasks: bulk delete {deleted} task(s)")
        return deleted

    def _create_recurring_followup(self, done_task: dict):
        due = done_task.get("due_date") or date.today().isoformat()
        new_task = {
            "id": _new_id(),
            "title": done_task["title"],
            "description": done_task.get("description", ""),
            "due_date": _next_due(due, done_task["recurring"]),
            "priority": done_task.get("priority", "medium"),
            "done": False,
            "recurring": done_task["recurring"],
            "created": date.today().isoformat(),
        }
        self._write_task(new_task)
