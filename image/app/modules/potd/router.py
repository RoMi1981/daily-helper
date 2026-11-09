"""Picture of the Day module — ID-based collection, daily random selection.

All files are stored as images (jpg/jpeg/png/webp/gif).
PDFs are converted to PNG on upload; no PDF files are kept.
"""

import asyncio
import io
import threading
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
from core import cache
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.net_guard import UnsafeUrlError, assert_public_http_url, fetch_public_url
from core.state import get_storage
from core.templates import templates
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

router = APIRouter(prefix="/potd", dependencies=[require_module("potd")])

_OFFSET_KEY_PREFIX = "potd:offset:"

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
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
    "application/pdf": "pdf",
}


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
    return get_primary_store("potd", get_storage())


def _potd_dir(store) -> Path:
    return Path(store.local_path) / "potd"


def _pdf_to_pngs(pdf_data: bytes) -> list[bytes]:
    """Convert PDF bytes to a list of PNG bytes (one per page)."""
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(pdf_data, dpi=150, fmt="png")
    result = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, "PNG")
        result.append(buf.getvalue())
    return result


def _migrate_pdfs(store) -> None:
    """Convert any legacy PDFs + sidecar YAMLs to PNG files in-place."""
    try:
        names = store.list_committed("potd")
    except Exception:
        return

    pdfs = [n for n in names if n.lower().endswith(".pdf")]
    yamls = [n for n in names if n.lower().endswith(".yaml")]
    if not pdfs and not yamls:
        return

    with store.write_lock():
        potd_dir = _potd_dir(store)
        potd_dir.mkdir(exist_ok=True)
        changed = False

        for pdf_name in pdfs:
            try:
                data = store.read_committed(f"potd/{pdf_name}")
                if not data:
                    continue
                pages = _pdf_to_pngs(data if isinstance(data, bytes) else data.encode())
                for page_bytes in pages:
                    (potd_dir / f"{_new_id()}.png").write_bytes(page_bytes)
                (potd_dir / pdf_name).unlink(missing_ok=True)
                changed = True
            except Exception:
                pass

        for yaml_name in yamls:
            try:
                (potd_dir / yaml_name).unlink(missing_ok=True)
                changed = True
            except Exception:
                pass

        if changed:
            store._commit_and_push("potd: migrate PDFs to PNG")


# Track which stores have been migrated this process lifetime
_migrated_stores: set = set()
_migration_lock = threading.Lock()


def _ensure_migrated(store) -> None:
    """Run the legacy PDF migration once per store and process.

    The check and the mark have to be atomic: the widget dashboard loads its
    widgets in parallel threads, so two of them can reach this at the same time
    and both start the migration.
    """
    sid = id(store)
    with _migration_lock:
        if sid in _migrated_stores:
            return
        _migrated_stores.add(sid)
    _migrate_pdfs(store)


def _list_files(store) -> list[dict]:
    """Return sorted list of image entries from a single store."""
    try:
        names = store.list_committed("potd")
    except Exception:
        names = []

    entries = []
    for name in names:
        parts = name.rsplit(".", 1)
        if len(parts) != 2:
            continue
        stem, ext = parts[0], parts[1].lower()
        if ext in ALLOWED_IMAGE_EXTENSIONS:
            entries.append({"id": stem, "ext": ext, "filename": name})

    entries.sort(key=lambda e: e["id"])
    return entries


def _list_files_all() -> list[dict]:
    """Return entries from all assigned repos, each with _store reference."""
    seen: set[str] = set()
    entries: list[dict] = []
    for store in get_module_stores("potd", get_storage()):
        _ensure_migrated(store)
        for entry in _list_files(store):
            if entry["id"] not in seen:
                seen.add(entry["id"])
                entry = dict(entry)
                entry["_store"] = store
                entries.append(entry)
    return sorted(entries, key=lambda e: e["id"])


def get_daily(store, offset: int = 0) -> dict | None:
    """Return today's entry deterministically, shifted by offset (single store)."""
    entries = _list_files(store)
    if not entries:
        return None
    today_int = int(date.today().strftime("%Y%m%d"))
    return entries[(today_int + offset) % len(entries)]


def get_daily_all(offset: int = 0) -> dict | None:
    """Return today's entry from merged pool across all repos."""
    entries = _list_files_all()
    if not entries:
        return None
    today_int = int(date.today().strftime("%Y%m%d"))
    return entries[(today_int + offset) % len(entries)]


def _read_file(store, filename: str) -> bytes | None:
    cache_key = f"potd:file:{filename}"
    cached = cache.get_bytes(cache_key)
    if cached is not None:
        return cached
    try:
        data = store.read_committed(f"potd/{filename}")
    except Exception:
        return None
    if data:
        cache.set_bytes(cache_key, data, ttl=3600)
    return data


def _save_image(store, ext: str, data: bytes) -> str:
    """Write one image file and return its id."""
    entry_id = _new_id()
    potd_dir = _potd_dir(store)
    potd_dir.mkdir(exist_ok=True)
    (potd_dir / f"{entry_id}.{ext}").write_bytes(data)
    return entry_id


@router.get("", response_class=HTMLResponse)
async def list_potd(request: Request, saved: str = ""):
    entries = _list_files_all()
    daily = get_daily_all(get_offset()) if entries else None
    return templates.TemplateResponse(
        request,
        "modules/potd/list.html",
        {
            "entries": entries,
            "daily_potd": daily,
            "configured": bool(get_module_stores("potd", get_storage())),
            "saved": saved,
            "active_module": "potd",
        },
    )


@router.post("/upload")
async def upload_potd(file: UploadFile = File(...)):
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

    # Convert before taking the lock — the conversion runs in a thread and an
    # await inside the lock would hold it across a suspension point.
    pages = await asyncio.to_thread(_pdf_to_pngs, data) if ext == "pdf" else None

    def _write() -> None:
        with store.write_lock():
            store._pull()
            if pages is not None:
                for page_bytes in pages:
                    _save_image(store, "png", page_bytes)
                store._commit_and_push(f"potd: add {fname} ({len(pages)} page(s)) as PNG")
            else:
                entry_id = _save_image(store, ext, data)
                store._commit_and_push(f"potd: add {entry_id}.{ext}")

    await asyncio.to_thread(_write)

    return RedirectResponse("/potd?saved=1", status_code=303)


@router.get("/{entry_id}/raw")
async def serve_potd(entry_id: str):
    stores = get_module_stores("potd", get_storage())
    if not stores:
        raise HTTPException(status_code=503)
    entry = next((e for e in _list_files_all() if e["id"] == entry_id), None)
    if not entry:
        raise HTTPException(status_code=404)

    store = entry.get("_store") or _get_store()
    if not store:
        raise HTTPException(status_code=503)

    data = _read_file(store, entry["filename"])
    if data is None:
        raise HTTPException(status_code=404)

    return Response(content=data, media_type=MIME_MAP.get(entry["ext"], "image/png"))


@router.post("/fetch")
async def fetch_potd(url: str = Form(...)):
    store = _get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage not configured")

    parsed = urlparse(url)
    try:
        assert_public_http_url(url)
    except UnsafeUrlError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await fetch_public_url(client, url, headers={"User-Agent": "daily-helper/1.0"})
            resp.raise_for_status()
            data = resp.content
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"Download failed: HTTP {e.response.status_code}") from e
    except UnsafeUrlError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {e}") from e

    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB)")

    ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    ext = CONTENT_TYPE_EXT.get(ct)
    if not ext:
        url_path = parsed.path.rsplit(".", 1)
        ext = url_path[-1].lower() if len(url_path) == 2 else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ct or ext!r}")

    pages = await asyncio.to_thread(_pdf_to_pngs, data) if ext == "pdf" else None

    def _write() -> None:
        with store.write_lock():
            store._pull()
            if pages is not None:
                for page_bytes in pages:
                    _save_image(store, "png", page_bytes)
                store._commit_and_push(f"potd: fetch PDF ({len(pages)} page(s)) as PNG from URL")
            else:
                entry_id = _save_image(store, ext, data)
                store._commit_and_push(f"potd: fetch {entry_id}.{ext} from URL")

    await asyncio.to_thread(_write)

    return RedirectResponse("/potd?saved=1", status_code=303)


@router.post("/{entry_id}/delete")
async def delete_potd(entry_id: str):
    stores = get_module_stores("potd", get_storage())
    if not stores:
        raise HTTPException(status_code=503)
    entry = next((e for e in _list_files_all() if e["id"] == entry_id), None)
    if not entry:
        raise HTTPException(status_code=404)

    store = entry.get("_store") or _get_store()
    if not store:
        raise HTTPException(status_code=503)

    def _write() -> None:
        with store.write_lock():
            store._pull()
            target = _potd_dir(store) / entry["filename"]
            if target.exists():
                target.unlink()

            store._commit_and_push(f"potd: delete {entry_id}")

    await asyncio.to_thread(_write)
    return RedirectResponse("/potd", status_code=303)


@router.post("/next", response_class=HTMLResponse)
async def next_potd(request: Request):
    """Advance to the next picture for today (HTMX)."""
    offset = _increment_offset()
    potd = get_daily_all(offset)
    return templates.TemplateResponse(request, "partials/potd_widget.html", {"potd": potd})
