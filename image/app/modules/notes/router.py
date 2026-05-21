"""Notes module — router."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.notes.storage import NoteStorage

router = APIRouter(prefix="/notes", dependencies=[require_module("notes")])


def _get_storage() -> NoteStorage | None:
    """Primary storage — used only for creating new notes."""
    store = get_primary_store("notes", get_storage())
    return NoteStorage(store) if store else None


def _get_all_storages() -> list[NoteStorage]:
    return [NoteStorage(s) for s in get_module_stores("notes", get_storage())]


def _find_storage(note_id: str) -> NoteStorage | None:
    """Return the storage that contains note_id (active or archived)."""
    for ns in _get_all_storages():
        if ns.get_note(note_id) or ns.get_archived_note(note_id):
            return ns
    return None


@router.get("", response_class=HTMLResponse)
async def list_notes(request: Request, q: str = "", saved: str = ""):
    from core import favorites as _fav

    seen: set[str] = set()
    notes: list[dict] = []
    for ns in _get_all_storages():
        for n in ns.list_notes(query=q):
            if n["id"] not in seen:
                seen.add(n["id"])
                notes.append(n)
    fav_entries = _fav.list_favorites()
    favorite_ids = {e["id"] for e in fav_entries if e.get("module") == "notes"}
    return templates.TemplateResponse(
        request,
        "modules/notes/list.html",
        {
            "notes": notes,
            "configured": bool(_get_all_storages()),
            "active_module": "notes",
            "q": q,
            "saved": saved,
            "favorite_ids": favorite_ids,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_note_form(request: Request):
    from core import settings_store

    cfg = settings_store.load()
    return templates.TemplateResponse(
        request,
        "modules/notes/form.html",
        {
            "note": None,
            "line_numbers": cfg.get("notes_line_numbers", False),
            "active_module": "notes",
            "encryption_available": True,
        },
    )


@router.post("/new")
async def create_note(
    subject: str = Form(...),
    body: str = Form(""),
    encrypt: str = Form(""),
):
    ns = _get_storage()
    if not ns:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not subject.strip():
        raise HTTPException(status_code=400, detail="Subject required")
    note = ns.create_note({"subject": subject, "body": body, "encrypt": encrypt == "on"})
    return RedirectResponse(f"/notes/{note['id']}", status_code=303)


# ── Archive routes (must be before /{note_id} to avoid conflicts) ──────────────


@router.get("/archive", response_class=HTMLResponse)
async def list_archive(request: Request, q: str = ""):
    seen: set[str] = set()
    notes: list[dict] = []
    for ns in _get_all_storages():
        for n in ns.list_archived_notes(query=q):
            if n["id"] not in seen:
                seen.add(n["id"])
                notes.append(n)
    return templates.TemplateResponse(
        request,
        "modules/notes/archive.html",
        {
            "notes": notes,
            "configured": bool(_get_all_storages()),
            "active_module": "notes",
            "q": q,
        },
    )


@router.post("/archive/{note_id}/restore")
async def restore_note(note_id: str):
    ns = _find_storage(note_id)
    if not ns:
        raise HTTPException(status_code=404)
    if not ns.restore_note(note_id):
        raise HTTPException(status_code=404)
    return RedirectResponse("/notes/archive", status_code=303)


# ── Per-note routes ─────────────────────────────────────────────────────────────


@router.get("/{note_id}", response_class=HTMLResponse)
async def view_note(request: Request, note_id: str):
    from core import settings_store

    note = None
    for ns in _get_all_storages():
        note = ns.get_note(note_id)
        if note:
            break
    if not note:
        raise HTTPException(status_code=404)
    cfg = settings_store.load()
    scroll_position = cfg.get("notes_scroll_position", "end")
    return templates.TemplateResponse(
        request,
        "modules/notes/detail.html",
        {
            "note": note,
            "scroll_position": scroll_position,
            "line_numbers": cfg.get("notes_line_numbers", False),
            "active_module": "notes",
        },
    )


@router.get("/{note_id}/history", response_class=HTMLResponse)
async def note_history(request: Request, note_id: str):
    ns = _find_storage(note_id)
    if not ns:
        raise HTTPException(status_code=404)
    note = ns.get_note(note_id)
    path = f"notes/{note_id}.yaml"
    commits = ns._git.get_file_history(path)
    sha = request.query_params.get("sha")
    diff = ns._git.get_file_diff(sha, path) if sha else None
    return templates.TemplateResponse(
        request,
        "modules/notes/history.html",
        {
            "note": note,
            "commits": commits,
            "diff": diff,
            "selected_sha": sha,
            "active_module": "notes",
        },
    )


@router.get("/{note_id}/edit", response_class=HTMLResponse)
async def edit_form(note_id: str, request: Request):
    from core import settings_store

    note = None
    for ns in _get_all_storages():
        note = ns.get_note(note_id)
        if note:
            break
    if not note:
        raise HTTPException(status_code=404)
    cfg = settings_store.load()
    return templates.TemplateResponse(
        request,
        "modules/notes/form.html",
        {
            "note": note,
            "line_numbers": cfg.get("notes_line_numbers", False),
            "scroll_position": cfg.get("notes_scroll_position", "end"),
            "active_module": "notes",
            "encryption_available": True,
            "is_edit": True,
        },
    )


@router.post("/{note_id}/edit")
async def update_note(
    note_id: str,
    subject: str = Form(...),
    body: str = Form(""),
    encrypt: str = Form(""),
):
    ns = _find_storage(note_id)
    if not ns:
        raise HTTPException(status_code=404)
    if not subject.strip():
        raise HTTPException(status_code=400, detail="Subject required")
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    if not ns.update_note(note_id, {"subject": subject, "body": body, "encrypt": encrypt == "on"}):
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/notes/{note_id}?saved=1", status_code=303)


@router.post("/{note_id}/delete")
async def delete_note(note_id: str):
    ns = _find_storage(note_id)
    if not ns:
        raise HTTPException(status_code=404)
    ns.delete_note(note_id)
    return RedirectResponse("/notes", status_code=303)


@router.post("/{note_id}/archive")
async def archive_note(note_id: str):
    ns = _find_storage(note_id)
    if not ns:
        raise HTTPException(status_code=404)
    if not ns.archive_note(note_id):
        raise HTTPException(status_code=404)
    return RedirectResponse("/notes", status_code=303)


@router.post("/bulk-delete", response_class=RedirectResponse)
async def bulk_delete_notes(ids: list[str] = Form(default=[])):
    if not ids:
        return RedirectResponse("/notes", status_code=303)
    # Group ids by storage to minimise git commits
    by_storage: dict[int, tuple[NoteStorage, list[str]]] = {}
    for note_id in ids:
        ns = _find_storage(note_id)
        if ns:
            key = id(ns._git)
            if key not in by_storage:
                by_storage[key] = (ns, [])
            by_storage[key][1].append(note_id)
    for ns, batch in by_storage.values():
        ns.bulk_delete_notes(batch)
    return RedirectResponse("/notes", status_code=303)
