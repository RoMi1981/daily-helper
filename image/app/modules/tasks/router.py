"""Tasks module — router for task management."""

import logging

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.tasks.storage import TaskStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", dependencies=[require_module("tasks")])


def _get_task_storage() -> TaskStorage | None:
    """Primary storage — used only for creating new tasks."""
    store = get_primary_store("tasks", get_storage())
    return TaskStorage(store) if store else None


def _get_all_task_storages() -> list[TaskStorage]:
    return [TaskStorage(s) for s in get_module_stores("tasks", get_storage())]


def _find_task_storage(task_id: str) -> TaskStorage | None:
    """Return the storage that contains task_id (for updates/deletes/toggles)."""
    for ts in _get_all_task_storages():
        if ts.get_task(task_id):
            return ts
    return None


@router.get("", response_class=HTMLResponse)
async def task_list(request: Request, q: str = "", saved: str = ""):
    storage = get_storage()
    categories = storage.get_categories() if storage else []

    seen: set[str] = set()
    tasks: list[dict] = []
    for ts in _get_all_task_storages():
        items = ts.search_tasks(q) if q else ts.list_tasks()
        for t in items:
            if t["id"] not in seen:
                seen.add(t["id"])
                tasks.append(t)

    open_tasks = [t for t in tasks if not t.get("done")]
    done_tasks = [t for t in tasks if t.get("done")]

    from datetime import date
    from core import favorites as _fav

    today = date.today().isoformat()
    fav_entries = _fav.list_favorites()
    favorite_ids = {e["id"] for e in fav_entries if e.get("module") == "tasks"}

    open_ids = {t["id"] for t in open_tasks}
    blocked_by_open: dict[str, list[str]] = {}
    for t in tasks:
        open_blockers = [bid for bid in t.get("blocked_by", []) if bid in open_ids]
        if open_blockers:
            blocked_by_open[t["id"]] = open_blockers

    return templates.TemplateResponse(
        request,
        "modules/tasks/list.html",
        {
            "open_tasks": open_tasks,
            "done_tasks": done_tasks,
            "categories": categories,
            "today": today,
            "active_module": "tasks",
            "configured": bool(_get_all_task_storages()),
            "saved": saved,
            "q": q,
            "favorite_ids": favorite_ids,
            "blocked_by_open": blocked_by_open,
        },
    )


@router.post("", response_class=RedirectResponse)
async def create_task(
    title: str = Form(...),
    description: str = Form(""),
    due_date: str = Form(""),
    priority: str = Form("medium"),
    recurring: str = Form("none"),
):
    task_storage = _get_task_storage()
    if not task_storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")
    task_storage.create_task(
        {
            "title": title,
            "description": description,
            "due_date": due_date,
            "priority": priority,
            "recurring": recurring,
        }
    )
    return RedirectResponse("/tasks?saved=1", status_code=303)


@router.get("/{task_id}/edit", response_class=HTMLResponse)
async def edit_task_form(request: Request, task_id: str):
    task = None
    for ts in _get_all_task_storages():
        task = ts.get_task(task_id)
        if task:
            break
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    storage = get_storage()
    categories = storage.get_categories() if storage else []
    all_open_tasks = [
        t
        for ts in _get_all_task_storages()
        for t in ts.list_tasks()
        if not t.get("done") and t["id"] != task_id
    ]
    return templates.TemplateResponse(
        request,
        "modules/tasks/form.html",
        {
            "task": task,
            "categories": categories,
            "active_module": "tasks",
            "all_open_tasks": all_open_tasks,
        },
    )


@router.post("/{task_id}/edit", response_class=RedirectResponse)
async def update_task(
    request: Request,
    task_id: str,
    title: str = Form(...),
    description: str = Form(""),
    due_date: str = Form(""),
    priority: str = Form("medium"),
    recurring: str = Form("none"),
):
    form = await request.form()
    blocked_by = list(form.getlist("blocked_by"))
    ts = _find_task_storage(task_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Task not found")
    task = ts.update_task(
        task_id,
        {
            "title": title,
            "description": description,
            "due_date": due_date,
            "priority": priority,
            "recurring": recurring,
            "blocked_by": blocked_by,
        },
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return RedirectResponse("/tasks?saved=1", status_code=303)


@router.post("/{task_id}/toggle", response_class=HTMLResponse)
async def toggle_task(request: Request, task_id: str):
    ts = _find_task_storage(task_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Task not found")
    task = ts.toggle_done(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    from datetime import date
    from core import favorites as _fav

    today = date.today().isoformat()
    fav_entries = _fav.list_favorites()
    favorite_ids = {e["id"] for e in fav_entries if e.get("module") == "tasks"}
    all_tasks = [t for s in _get_all_task_storages() for t in s.list_tasks()]
    open_ids = {t["id"] for t in all_tasks if not t.get("done")}
    open_blockers = [bid for bid in task.get("blocked_by", []) if bid in open_ids]
    blocked_by_open = {task["id"]: open_blockers} if open_blockers else {}
    return templates.TemplateResponse(
        request,
        "modules/tasks/_task_row.html",
        {
            "task": task,
            "today": today,
            "favorite_ids": favorite_ids,
            "blocked_by_open": blocked_by_open,
        },
    )


@router.get("/{task_id}/history", response_class=HTMLResponse)
async def task_history(request: Request, task_id: str):
    ts = _find_task_storage(task_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Task not found")
    task = ts.get_task(task_id)
    path = f"tasks/done/{task_id}.yaml" if task.get("done") else f"tasks/{task_id}.yaml"
    commits = ts._git.get_file_history(path)
    if not commits:
        alt = f"tasks/{task_id}.yaml" if task.get("done") else f"tasks/done/{task_id}.yaml"
        commits = ts._git.get_file_history(alt)
    sha = request.query_params.get("sha")
    diff = ts._git.get_file_diff(sha, path) if sha else None
    return templates.TemplateResponse(
        request,
        "modules/tasks/history.html",
        {
            "item": task,
            "item_title": task.get("title", task_id),
            "back_url": "/tasks",
            "commits": commits,
            "diff": diff,
            "selected_sha": sha,
            "active_module": "tasks",
        },
    )


@router.post("/{task_id}/delete", response_class=RedirectResponse)
async def delete_task(task_id: str):
    ts = _find_task_storage(task_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Task not found")
    if not ts.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return RedirectResponse("/tasks", status_code=303)


@router.post("/bulk-delete", response_class=RedirectResponse)
async def bulk_delete_tasks(ids: Annotated[list[str], Form()] = []):
    if not ids:
        return RedirectResponse("/tasks", status_code=303)
    by_storage: dict[int, tuple[TaskStorage, list[str]]] = {}
    for task_id in ids:
        ts = _find_task_storage(task_id)
        if ts:
            key = id(ts._git)
            if key not in by_storage:
                by_storage[key] = (ts, [])
            by_storage[key][1].append(task_id)
    for ts, batch in by_storage.values():
        ts.bulk_delete_tasks(batch)
    return RedirectResponse("/tasks", status_code=303)
