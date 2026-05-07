"""Memes module — image collection, daily random selection."""

import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from core import cache
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates

router = APIRouter(prefix="/memes", dependencies=[require_module("memes")])

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB

MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

_OFFSET_KEY_PREFIX = "memes:offset:"


def _today_key() -> str:
    return _OFFSET_KEY_PREFIX + date.today().isoformat()


def get_offset() -> int:
    val = cache.get(_today_key())
    return int(val) if val is not None else 0


def _increment_offset() -> int:
    from datetime import datetime

    offset = get_offset() + 1
    now = datetime.now()
    end = datetime(now.year, now.month, now.day, 23, 59, 59)
    ttl = max(60, int((end - now).total_seconds()))
    cache.set(_today_key(), offset, ttl=ttl)
    return offset


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _get_store():
    return get_primary_store("memes", get_storage())


def _list_files_all() -> list[dict]:
    """Return entries from all assigned repos, each with _store reference."""
    seen: set[str] = set()
    entries: list[dict] = []
    for store in get_module_stores("memes", get_storage()):
        for entry in _list_files(store):
            if entry["id"] not in seen:
                seen.add(entry["id"])
                entry = dict(entry)
                entry["_store"] = store
                entries.append(entry)
    return sorted(entries, key=lambda e: e["id"])


def _memes_dir(store) -> Path:
    return Path(store.local_path) / "memes"


def _list_files(store) -> list[dict]:
    try:
        names = store.list_committed("memes")
    except Exception:
        names = []

    entries = []
    for name in names:
        parts = name.rsplit(".", 1)
        if len(parts) != 2:
            continue
        stem, ext = parts[0], parts[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            entries.append({"id": stem, "ext": ext, "filename": name})

    entries.sort(key=lambda e: e["id"])
    return entries


def get_daily(store, offset: int = 0) -> dict | None:
    entries = _list_files(store)
    if not entries:
        return None
    today_int = int(date.today().strftime("%Y%m%d"))
    return entries[(today_int + offset) % len(entries)]


def get_daily_all(offset: int = 0) -> dict | None:
    """Return today's meme from merged pool across all repos."""
    entries = _list_files_all()
    if not entries:
        return None
    today_int = int(date.today().strftime("%Y%m%d"))
    return entries[(today_int + offset) % len(entries)]


def _read_file(store, filename: str) -> bytes | None:
    cache_key = f"meme:file:{filename}"
    cached = cache.get_bytes(cache_key)
    if cached is not None:
        return cached
    try:
        data = store.read_committed(f"memes/{filename}")
    except Exception:
        return None
    if data:
        cache.set_bytes(cache_key, data, ttl=3600)
    return data


@router.get("", response_class=HTMLResponse)
async def list_memes(request: Request, saved: str = ""):
    entries = _list_files_all()
    return templates.TemplateResponse(
        request,
        "modules/memes/list.html",
        {
            "entries": entries,
            "configured": bool(get_module_stores("memes", get_storage())),
            "saved": saved,
            "active_module": "memes",
        },
    )


@router.post("/upload")
async def upload_meme(file: UploadFile = File(...)):
    store = _get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage not configured")

    fname = file.filename or ""
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB)")

    store._pull()
    memes_dir = _memes_dir(store)
    memes_dir.mkdir(exist_ok=True)

    entry_id = _new_id()
    (memes_dir / f"{entry_id}.{ext}").write_bytes(data)
    store._commit_and_push(f"memes: add {entry_id}.{ext}")

    return RedirectResponse("/memes?saved=1", status_code=303)


@router.post("/fetch")
async def fetch_meme(url: str = Form(...)):
    store = _get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage not configured")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http/https URLs allowed")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "daily-helper/1.0"})
            resp.raise_for_status()
            data = resp.content
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=400, detail=f"Download failed: HTTP {e.response.status_code}"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {e}")

    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB)")

    ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    ext = CONTENT_TYPE_EXT.get(ct)
    if not ext:
        url_path = parsed.path.rsplit(".", 1)
        ext = url_path[-1].lower() if len(url_path) == 2 else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ct or ext!r}")

    store._pull()
    memes_dir = _memes_dir(store)
    memes_dir.mkdir(exist_ok=True)

    entry_id = _new_id()
    (memes_dir / f"{entry_id}.{ext}").write_bytes(data)
    store._commit_and_push(f"memes: fetch {entry_id}.{ext} from URL")

    return RedirectResponse("/memes?saved=1", status_code=303)


@router.get("/{entry_id}/raw")
async def serve_meme(entry_id: str):
    if not get_module_stores("memes", get_storage()):
        raise HTTPException(status_code=503, detail="No repository configured")
    entry = next((e for e in _list_files_all() if e["id"] == entry_id), None)
    if not entry:
        raise HTTPException(status_code=404)

    store = entry.get("_store") or _get_store()
    if not store:
        raise HTTPException(status_code=503)

    data = _read_file(store, entry["filename"])
    if data is None:
        raise HTTPException(status_code=404)

    return Response(content=data, media_type=MIME_MAP.get(entry["ext"], "application/octet-stream"))


@router.post("/next", response_class=HTMLResponse)
async def next_meme(request: Request):
    """Advance to the next meme for today (HTMX)."""
    offset = _increment_offset()
    meme = get_daily_all(offset)
    return templates.TemplateResponse(request, "partials/meme_widget.html", {"meme": meme})


@router.post("/{entry_id}/delete")
async def delete_meme(entry_id: str):
    if not get_module_stores("memes", get_storage()):
        raise HTTPException(status_code=503, detail="No repository configured")
    entry = next((e for e in _list_files_all() if e["id"] == entry_id), None)
    if not entry:
        raise HTTPException(status_code=404)

    store = entry.get("_store") or _get_store()
    if not store:
        raise HTTPException(status_code=503)

    store._pull()
    memes_dir = _memes_dir(store)
    target = memes_dir / entry["filename"]
    if target.exists():
        target.unlink()

    store._commit_and_push(f"memes: delete {entry_id}")
    return RedirectResponse("/memes", status_code=303)
