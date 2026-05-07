"""MOTD module — router."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import cache
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.motd.storage import MotdStorage

router = APIRouter(prefix="/motd", dependencies=[require_module("motd")])

_REDIS_KEY_PREFIX = "motd:offset:"


def _get_storage() -> MotdStorage | None:
    """Primary storage — used only for creating/editing entries."""
    store = get_primary_store("motd", get_storage())
    return MotdStorage(store) if store else None


def _get_all_storages() -> list[MotdStorage]:
    return [MotdStorage(s) for s in get_module_stores("motd", get_storage())]


def _find_storage(motd_id: str) -> MotdStorage | None:
    for ms in _get_all_storages():
        if ms.get_entry(motd_id):
            return ms
    return None


def _list_all_entries() -> list[dict]:
    seen: set[str] = set()
    entries: list[dict] = []
    for ms in _get_all_storages():
        for e in ms.list_entries():
            if e["id"] not in seen:
                seen.add(e["id"])
                entries.append(e)
    return entries


def get_daily_all(offset: int = 0) -> dict | None:
    """Return today's MOTD from merged pool across all repos."""
    from datetime import date

    entries = [e for e in _list_all_entries() if e.get("active", True)]
    if not entries:
        return None
    today_int = int(date.today().strftime("%Y%m%d"))
    return entries[(today_int + offset) % len(entries)]


def _today_key() -> str:
    from datetime import date

    return _REDIS_KEY_PREFIX + date.today().isoformat()


def _get_offset() -> int:
    val = cache.get(_today_key())
    return int(val) if val is not None else 0


def _increment_offset() -> int:
    offset = _get_offset() + 1
    # TTL until end of day (seconds remaining)
    from datetime import date, datetime

    now = datetime.now()
    end = datetime(now.year, now.month, now.day, 23, 59, 59)
    ttl = max(60, int((end - now).total_seconds()))
    cache.set(_today_key(), offset, ttl=ttl)
    return offset


@router.get("", response_class=HTMLResponse)
async def list_motd(request: Request, saved: str = "", skipped: str = "", duplicate: str = ""):
    entries = _list_all_entries()
    return templates.TemplateResponse(
        request,
        "modules/motd/list.html",
        {
            "entries": entries,
            "configured": bool(_get_all_storages()),
            "active_module": "motd",
            "saved": saved,
            "skipped": skipped,
            "duplicate": duplicate,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_motd_form(request: Request):
    return templates.TemplateResponse(
        request,
        "modules/motd/form.html",
        {"entry": None, "active_module": "motd"},
    )


@router.post("/new")
async def create_motd(text: str = Form(...)):
    ms = _get_storage()
    if not ms:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text required")
    _, is_dupe = ms.create_entry({"text": text})
    if is_dupe:
        return RedirectResponse("/motd?duplicate=1", status_code=303)
    return RedirectResponse("/motd?saved=1", status_code=303)


@router.get("/import", response_class=HTMLResponse)
async def import_form(request: Request):
    return templates.TemplateResponse(
        request,
        "modules/motd/import.html",
        {"active_module": "motd"},
    )


@router.post("/import")
async def import_motd(
    text: str = Form(""),
    file_content: str = Form(""),
):
    ms = _get_storage()
    if not ms:
        raise HTTPException(status_code=503, detail="Storage not configured")
    raw = file_content or text
    lines = raw.splitlines()
    created, skipped = ms.bulk_import(lines)
    qs = f"saved={created}" + (f"&skipped={skipped}" if skipped else "")
    return RedirectResponse(f"/motd?{qs}", status_code=303)


@router.post("/import-file")
async def import_motd_file(request: Request):
    ms = _get_storage()
    if not ms:
        raise HTTPException(status_code=503, detail="Storage not configured")
    form = await request.form()
    upload = form.get("file")
    if upload and hasattr(upload, "read"):
        content = (await upload.read()).decode("utf-8", errors="replace")
    else:
        content = ""
    lines = content.splitlines()
    created, skipped = ms.bulk_import(lines)
    qs = f"saved={created}" + (f"&skipped={skipped}" if skipped else "")
    return RedirectResponse(f"/motd?{qs}", status_code=303)


@router.get("/{motd_id}/edit", response_class=HTMLResponse)
async def edit_form(motd_id: str, request: Request):
    ms = _find_storage(motd_id)
    entry = ms.get_entry(motd_id) if ms else None
    if not entry:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "modules/motd/form.html",
        {"entry": entry, "active_module": "motd"},
    )


@router.post("/{motd_id}/edit")
async def update_motd(
    motd_id: str,
    text: str = Form(...),
    active: str = Form(""),
):
    ms = _find_storage(motd_id)
    if not ms:
        raise HTTPException(status_code=404)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text required")
    if not ms.update_entry(motd_id, {"text": text, "active": active == "on"}):
        raise HTTPException(status_code=404)
    return RedirectResponse("/motd?saved=1", status_code=303)


@router.post("/{motd_id}/delete")
async def delete_motd(motd_id: str):
    ms = _find_storage(motd_id)
    if not ms:
        raise HTTPException(status_code=404)
    ms.delete_entry(motd_id)
    return RedirectResponse("/motd", status_code=303)


@router.post("/next", response_class=HTMLResponse)
async def next_motd(request: Request):
    """Advance to the next message for today (HTMX)."""
    offset = _increment_offset()
    entry = get_daily_all(offset)
    return templates.TemplateResponse(
        request,
        "partials/motd_widget.html",
        {"motd": entry},
    )
