"""Picture of the Day module — ID-based collection, daily random selection."""

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

router = APIRouter(prefix="/potd", dependencies=[require_module("potd")])

_OFFSET_KEY_PREFIX = "potd:offset:"


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


ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB

MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "pdf": "application/pdf",
}


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _get_store():
    return get_primary_store("potd", get_storage())


def _list_files_all() -> list[dict]:
    """Return entries from all assigned repos, each with _store reference for binary serving."""
    seen: set[str] = set()
    entries: list[dict] = []
    for store in get_module_stores("potd", get_storage()):
        for entry in _list_files(store):
            if entry["id"] not in seen:
                seen.add(entry["id"])
                entry = dict(entry)
                entry["_store"] = store
                entries.append(entry)
    return sorted(entries, key=lambda e: e["id"])


def _potd_dir(store) -> Path:
    return Path(store.local_path) / "potd"


def _count_pdf_pages(data: bytes) -> int:
    """Return page count of a PDF. Falls back to 1 on any error."""
    try:
        import io
        from pypdf import PdfReader

        return max(1, len(PdfReader(io.BytesIO(data)).pages))
    except Exception:
        return 1


def _read_sidecar(store, stem: str) -> dict:
    """Return sidecar metadata {page, source} or empty dict."""
    try:
        raw = store.read_committed(f"potd/{stem}.yaml")
        if raw and isinstance(raw, (str, bytes)):
            meta = yaml.safe_load(raw)
            if isinstance(meta, dict):
                p = meta.get("page")
                return {
                    "page": int(p) if p and int(p) > 0 else None,
                    "source": meta.get("source"),
                }
    except Exception:
        pass
    return {"page": None, "source": None}


def _list_files(store) -> list[dict]:
    """Return sorted list of all collection entries.

    Two entry types:
    - Media files (image/PDF) → one entry per file
    - Sidecar-only YAMLs → one entry per PDF page (source PDF stored separately)
    """
    try:
        names = store.list_committed("potd")
    except Exception:
        names = []

    media: dict[str, str] = {}  # stem -> ext
    sidecar_stems: set[str] = set()

    for name in names:
        parts = name.rsplit(".", 1)
        if len(parts) != 2:
            continue
        stem, ext = parts[0], parts[1].lower()
        if ext == "yaml":
            sidecar_stems.add(stem)
        elif ext in ALLOWED_EXTENSIONS:
            media[stem] = ext

    entries = []

    for stem, ext in media.items():
        sc = _read_sidecar(store, stem) if stem in sidecar_stems else {"page": None, "source": None}
        entries.append(
            {
                "id": stem,
                "ext": ext,
                "filename": f"{stem}.{ext}",
                "page": sc["page"],
                "source": None,
            }
        )

    for stem in sidecar_stems:
        if stem in media:
            continue
        sc = _read_sidecar(store, stem)
        if not sc["source"] or not sc["page"]:
            continue
        src_ext = sc["source"].rsplit(".", 1)[-1].lower() if "." in sc["source"] else ""
        if src_ext not in ALLOWED_EXTENSIONS:
            continue
        entries.append(
            {
                "id": stem,
                "ext": src_ext,
                "filename": sc["source"],
                "page": sc["page"],
                "source": sc["source"],
            }
        )

    entries.sort(key=lambda e: e["id"])
    return entries


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


@router.get("", response_class=HTMLResponse)
async def list_potd(request: Request, saved: str = ""):
    entries = _list_files_all()
    return templates.TemplateResponse(
        request,
        "modules/potd/list.html",
        {
            "entries": entries,
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

    store._pull()
    potd_dir = _potd_dir(store)
    potd_dir.mkdir(exist_ok=True)

    if ext == "pdf":
        page_count = _count_pdf_pages(data)
        source_id = _new_id()
        source_filename = f"{source_id}.pdf"
        (potd_dir / source_filename).write_bytes(data)
        for i in range(page_count):
            page_id = _new_id()
            (potd_dir / f"{page_id}.yaml").write_text(
                yaml.dump({"source": source_filename, "page": i + 1}, allow_unicode=True)
            )
        store._commit_and_push(f"potd: add {source_filename} ({page_count} page(s))")
    else:
        entry_id = _new_id()
        (potd_dir / f"{entry_id}.{ext}").write_bytes(data)
        store._commit_and_push(f"potd: add {entry_id}.{ext}")

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

    return Response(content=data, media_type=MIME_MAP.get(entry["ext"], "application/octet-stream"))


CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "application/pdf": "pdf",
}


@router.post("/fetch")
async def fetch_potd(url: str = Form(...)):
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

    # Detect extension from Content-Type, fall back to URL path
    ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    ext = CONTENT_TYPE_EXT.get(ct)
    if not ext:
        url_path = parsed.path.rsplit(".", 1)
        ext = url_path[-1].lower() if len(url_path) == 2 else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ct or ext!r}")

    store._pull()
    potd_dir = _potd_dir(store)
    potd_dir.mkdir(exist_ok=True)

    if ext == "pdf":
        page_count = _count_pdf_pages(data)
        source_id = _new_id()
        source_filename = f"{source_id}.pdf"
        (potd_dir / source_filename).write_bytes(data)
        for i in range(page_count):
            page_id = _new_id()
            (potd_dir / f"{page_id}.yaml").write_text(
                yaml.dump({"source": source_filename, "page": i + 1}, allow_unicode=True)
            )
        store._commit_and_push(f"potd: fetch {source_filename} ({page_count} page(s)) from URL")
    else:
        entry_id = _new_id()
        (potd_dir / f"{entry_id}.{ext}").write_bytes(data)
        store._commit_and_push(f"potd: fetch {entry_id}.{ext} from URL")

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

    store._pull()
    potd_dir = _potd_dir(store)

    if entry.get("source"):
        sidecar = potd_dir / f"{entry_id}.yaml"
        if sidecar.exists():
            sidecar.unlink()
    else:
        target = potd_dir / entry["filename"]
        if target.exists():
            target.unlink()
        sidecar = potd_dir / f"{entry_id}.yaml"
        if sidecar.exists():
            sidecar.unlink()

    store._commit_and_push(f"potd: delete {entry_id}")
    return RedirectResponse("/potd", status_code=303)


@router.post("/next", response_class=HTMLResponse)
async def next_potd(request: Request):
    """Advance to the next picture for today (HTMX)."""
    offset = _increment_offset()
    potd = get_daily_all(offset)
    return templates.TemplateResponse(request, "partials/potd_widget.html", {"potd": potd})
