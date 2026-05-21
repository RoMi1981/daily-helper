"""Snippets module — router."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.snippets.storage import SnippetStorage

router = APIRouter(prefix="/snippets", dependencies=[require_module("snippets")])


def _get_storage() -> SnippetStorage | None:
    """Primary storage — used only for creating new snippets."""
    store = get_primary_store("snippets", get_storage())
    return SnippetStorage(store) if store else None


def _get_all_storages() -> list[SnippetStorage]:
    return [SnippetStorage(s) for s in get_module_stores("snippets", get_storage())]


def _find_storage(snippet_id: str) -> SnippetStorage | None:
    for ss in _get_all_storages():
        if ss.get_snippet(snippet_id):
            return ss
    return None


@router.get("", response_class=HTMLResponse)
async def list_snippets(request: Request, q: str = "", saved: str = ""):
    from core import favorites as _fav

    seen: set[str] = set()
    snippets: list[dict] = []
    for ss in _get_all_storages():
        for sn in ss.list_snippets(query=q):
            if sn["id"] not in seen:
                seen.add(sn["id"])
                snippets.append(sn)
    fav_entries = _fav.list_favorites()
    favorite_ids = {e["id"] for e in fav_entries if e.get("module") == "snippets"}
    return templates.TemplateResponse(
        request,
        "modules/snippets/list.html",
        {
            "snippets": snippets,
            "configured": bool(_get_all_storages()),
            "active_module": "snippets",
            "q": q,
            "saved": saved,
            "favorite_ids": favorite_ids,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_snippet_form(request: Request):
    return templates.TemplateResponse(
        request,
        "modules/snippets/form.html",
        {
            "snippet": None,
            "active_module": "snippets",
        },
    )


@router.post("/new")
async def create_snippet(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
):
    ss = _get_storage()
    if not ss:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")

    form = await request.form()
    steps = _parse_steps(form)
    sn = ss.create_snippet({"title": title, "description": description, "steps": steps})
    return RedirectResponse(f"/snippets/{sn['id']}", status_code=303)


@router.get("/{snippet_id}", response_class=HTMLResponse)
async def view_snippet(request: Request, snippet_id: str):
    snippet = None
    for ss in _get_all_storages():
        snippet = ss.get_snippet(snippet_id)
        if snippet:
            break
    if not snippet:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "modules/snippets/detail.html",
        {
            "snippet": snippet,
            "active_module": "snippets",
        },
    )


@router.get("/{snippet_id}/edit", response_class=HTMLResponse)
async def edit_form(snippet_id: str, request: Request):
    snippet = None
    for ss in _get_all_storages():
        snippet = ss.get_snippet(snippet_id)
        if snippet:
            break
    if not snippet:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "modules/snippets/form.html",
        {
            "snippet": snippet,
            "active_module": "snippets",
        },
    )


@router.post("/{snippet_id}/edit")
async def update_snippet(
    snippet_id: str,
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
):
    ss = _find_storage(snippet_id)
    if not ss:
        raise HTTPException(status_code=404)
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")

    form = await request.form()
    steps = _parse_steps(form)
    if not ss.update_snippet(
        snippet_id, {"title": title, "description": description, "steps": steps}
    ):
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/snippets/{snippet_id}", status_code=303)


@router.get("/{snippet_id}/history", response_class=HTMLResponse)
async def snippet_history(request: Request, snippet_id: str):
    ss = _find_storage(snippet_id)
    if not ss:
        raise HTTPException(status_code=404, detail="Snippet not found")
    sn = ss.get_snippet(snippet_id)
    path = f"snippets/{snippet_id}.yaml"
    commits = ss._git.get_file_history(path)
    sha = request.query_params.get("sha")
    diff = ss._git.get_file_diff(sha, path) if sha else None
    return templates.TemplateResponse(
        request,
        "modules/snippets/history.html",
        {
            "item": sn,
            "item_title": sn.get("title", snippet_id),
            "back_url": f"/snippets/{snippet_id}",
            "commits": commits,
            "diff": diff,
            "selected_sha": sha,
            "active_module": "snippets",
        },
    )


@router.post("/{snippet_id}/delete")
async def delete_snippet(snippet_id: str):
    ss = _find_storage(snippet_id)
    if not ss:
        raise HTTPException(status_code=404)
    ss.delete_snippet(snippet_id)
    return RedirectResponse("/snippets", status_code=303)


@router.post("/bulk-delete", response_class=RedirectResponse)
async def bulk_delete_snippets(ids: list[str] = Form(default=[])):
    if not ids:
        return RedirectResponse("/snippets", status_code=303)
    by_storage: dict[int, tuple[SnippetStorage, list[str]]] = {}
    for sn_id in ids:
        ss = _find_storage(sn_id)
        if ss:
            key = id(ss._git)
            if key not in by_storage:
                by_storage[key] = (ss, [])
            by_storage[key][1].append(sn_id)
    for ss, batch in by_storage.values():
        ss.bulk_delete_snippets(batch)
    return RedirectResponse("/snippets", status_code=303)


def _parse_steps(form) -> list[dict]:
    """Extract ordered steps from flat form fields step_desc_N / step_cmd_N."""
    steps = []
    idx = 0
    while True:
        if f"step_cmd_{idx}" not in form:
            break
        cmd = form.get(f"step_cmd_{idx}", "").strip()
        desc = form.get(f"step_desc_{idx}", "").strip()
        if cmd:
            steps.append({"description": desc, "command": cmd})
        idx += 1
    return steps
