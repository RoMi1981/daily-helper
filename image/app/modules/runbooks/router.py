"""Runbooks module — router."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Annotated

from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.runbooks.storage import RunbookStorage

router = APIRouter(prefix="/runbooks", dependencies=[require_module("runbooks")])


def _get_storage() -> RunbookStorage | None:
    """Primary storage — used only for creating new runbooks."""
    store = get_primary_store("runbooks", get_storage())
    return RunbookStorage(store) if store else None


def _get_all_storages() -> list[RunbookStorage]:
    return [RunbookStorage(s) for s in get_module_stores("runbooks", get_storage())]


def _find_storage(runbook_id: str) -> RunbookStorage | None:
    for rs in _get_all_storages():
        if rs.get_runbook(runbook_id):
            return rs
    return None


@router.get("", response_class=HTMLResponse)
async def list_runbooks(request: Request, q: str = "", saved: str = ""):
    from core import favorites as _fav

    seen: set[str] = set()
    runbooks: list[dict] = []
    for rs in _get_all_storages():
        for rb in rs.list_runbooks(query=q):
            if rb["id"] not in seen:
                seen.add(rb["id"])
                runbooks.append(rb)
    fav_entries = _fav.list_favorites()
    favorite_ids = {e["id"] for e in fav_entries if e.get("module") == "runbooks"}
    return templates.TemplateResponse(
        request,
        "modules/runbooks/list.html",
        {
            "runbooks": runbooks,
            "configured": bool(_get_all_storages()),
            "active_module": "runbooks",
            "q": q,
            "saved": saved,
            "favorite_ids": favorite_ids,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_runbook_form(request: Request):
    return templates.TemplateResponse(
        request,
        "modules/runbooks/form.html",
        {
            "runbook": None,
            "active_module": "runbooks",
        },
    )


@router.post("/new")
async def create_runbook(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
):
    rs = _get_storage()
    if not rs:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")

    form = await request.form()
    steps = _parse_steps(form)
    rb = rs.create_runbook({"title": title, "description": description, "steps": steps})
    return RedirectResponse(f"/runbooks/{rb['id']}", status_code=303)


@router.get("/{runbook_id}", response_class=HTMLResponse)
async def view_runbook(request: Request, runbook_id: str):
    runbook = None
    for rs in _get_all_storages():
        runbook = rs.get_runbook(runbook_id)
        if runbook:
            break
    if not runbook:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "modules/runbooks/detail.html",
        {
            "runbook": runbook,
            "active_module": "runbooks",
        },
    )


@router.get("/{runbook_id}/edit", response_class=HTMLResponse)
async def edit_form(runbook_id: str, request: Request):
    runbook = None
    for rs in _get_all_storages():
        runbook = rs.get_runbook(runbook_id)
        if runbook:
            break
    if not runbook:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "modules/runbooks/form.html",
        {
            "runbook": runbook,
            "active_module": "runbooks",
        },
    )


@router.post("/{runbook_id}/edit")
async def update_runbook(
    runbook_id: str,
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
):
    rs = _find_storage(runbook_id)
    if not rs:
        raise HTTPException(status_code=404)
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")

    form = await request.form()
    steps = _parse_steps(form)
    if not rs.update_runbook(
        runbook_id, {"title": title, "description": description, "steps": steps}
    ):
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/runbooks/{runbook_id}", status_code=303)


@router.get("/{runbook_id}/history", response_class=HTMLResponse)
async def runbook_history(request: Request, runbook_id: str):
    rs = _find_storage(runbook_id)
    if not rs:
        raise HTTPException(status_code=404, detail="Runbook not found")
    rb = rs.get_runbook(runbook_id)
    path = f"runbooks/{runbook_id}.yaml"
    commits = rs._git.get_file_history(path)
    sha = request.query_params.get("sha")
    diff = rs._git.get_file_diff(sha, path) if sha else None
    return templates.TemplateResponse(
        request,
        "modules/runbooks/history.html",
        {
            "item": rb,
            "item_title": rb.get("title", runbook_id),
            "back_url": f"/runbooks/{runbook_id}",
            "commits": commits,
            "diff": diff,
            "selected_sha": sha,
            "active_module": "runbooks",
        },
    )


@router.post("/{runbook_id}/delete")
async def delete_runbook(runbook_id: str):
    rs = _find_storage(runbook_id)
    if not rs:
        raise HTTPException(status_code=404)
    rs.delete_runbook(runbook_id)
    return RedirectResponse("/runbooks", status_code=303)


@router.post("/bulk-delete", response_class=RedirectResponse)
async def bulk_delete_runbooks(ids: Annotated[list[str], Form()] = []):
    if not ids:
        return RedirectResponse("/runbooks", status_code=303)
    by_storage: dict[int, tuple[RunbookStorage, list[str]]] = {}
    for rb_id in ids:
        rs = _find_storage(rb_id)
        if rs:
            key = id(rs._git)
            if key not in by_storage:
                by_storage[key] = (rs, [])
            by_storage[key][1].append(rb_id)
    for rs, batch in by_storage.values():
        rs.bulk_delete_runbooks(batch)
    return RedirectResponse("/runbooks", status_code=303)


def _parse_steps(form) -> list[dict]:
    """Extract ordered steps from flat form fields step_title_N / step_body_N."""
    steps = []
    idx = 0
    while True:
        title = form.get(f"step_title_{idx}", "").strip()
        if title == "" and f"step_title_{idx}" not in form:
            break
        body = form.get(f"step_body_{idx}", "").strip()
        if title:
            steps.append({"title": title, "body": body})
        idx += 1
    return steps
