"""Knowledge module — routes for entries, categories, search and markdown preview."""

import asyncio
import logging
import mimetypes
import re

import bleach
import bleach.linkifier
import markdown as md_lib

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # 25 MB


def _safe_filename(name: str) -> str:
    """Strip path separators and dangerous characters from a filename."""
    name = name.replace("/", "").replace("\\", "").strip(". ")
    name = re.sub(r"[^\w\-. ]", "_", name)
    return name[:200] or "attachment"
from core import settings_store
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_module_repo_list
from core.state import get_storage
from core.storage import GitStorageError
from core.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", dependencies=[require_module("knowledge")])

_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
    "img", "hr", "br", "del", "s", "sup", "sub",
    "ul", "ol", "li", "blockquote", "input",
}
_ALLOWED_ATTRS = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class"],
    "pre": ["class"],
    "td": ["align"],
    "th": ["align"],
    "input": ["type", "checked", "disabled"],
}

PAGE_SIZE = 20

_preview_rate: dict[str, list[float]] = {}
_PREVIEW_WINDOW = 10.0
_PREVIEW_MAX = 20


def render_md(text: str) -> str:
    raw_html = md_lib.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    return bleach.clean(raw_html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


def _sidebar(storage) -> list[dict]:
    if not storage:
        return []
    stores = get_module_stores("knowledge", storage)
    result = []
    repo_map = {r["id"]: r.get("name", r["id"]) for r in storage._cfg.get("repos", [])}
    for store in stores:
        try:
            for cat in store.get_categories():
                result.append({"repo_id": store.repo_id, "repo_name": repo_map.get(store.repo_id, store.repo_id), "category": cat})
        except Exception:
            pass
    return result


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = ""):
    storage = get_storage()
    categories = _sidebar(storage)
    stores = get_module_stores("knowledge", storage)
    all_entries = []
    for s in stores:
        try:
            all_entries.extend(s.get_entries())
        except Exception:
            pass
    pinned = [e for e in all_entries if e.get("pinned")]
    recent = [e for e in all_entries if not e.get("pinned")][:10]
    cfg = settings_store.load()
    return templates.TemplateResponse(request, "knowledge/index.html", {
        "categories": categories,
        "pinned": pinned,
        "recent": recent,
        "configured": bool(cfg.get("repos")),
        "active_module": "knowledge",
        "q": q,
    })


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "", category: str = ""):
    storage = get_storage()
    results = []
    if storage:
        if q:
            for store in get_module_stores("knowledge", storage):
                try:
                    r = store.search(q)
                    if category:
                        r = [x for x in r if x.get("category") == category]
                    results.extend(r)
                except Exception:
                    pass
        elif category:
            results = storage.get_entries(category=category)
    return templates.TemplateResponse(request, "partials/search_results.html", {
        "results": results,
        "query": q,
        "category": category,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_entry_form(request: Request, error: str = ""):
    storage = get_storage()
    categories = _sidebar(storage)
    cfg = settings_store.load()
    module_repo_list = get_module_repo_list("knowledge", storage)
    # Filter to writable repos only for writing
    writable_ids = {r["id"] for r in cfg.get("repos", []) if r.get("permissions", {}).get("write")}
    writable_repos = [r for r in module_repo_list if r["id"] in writable_ids] or module_repo_list
    primary_id = settings_store.get_module_repos("knowledge").get("primary", "")
    categories_by_repo: dict[str, list[str]] = {}
    for item in categories:
        categories_by_repo.setdefault(item["repo_id"], []).append(item["category"])
    return templates.TemplateResponse(request, "knowledge/new.html", {
        "categories": categories,
        "categories_by_repo": categories_by_repo,
        "writable_repos": writable_repos,
        "primary_repo_id": primary_id or (writable_repos[0]["id"] if writable_repos else ""),
        "entry_templates": settings_store.get_templates(),
        "error": error,
        "configured": bool(cfg.get("repos")),
        "active_module": "knowledge",
    })


@router.post("/entries")
async def create_entry(
    repo_id: str = Form(...),
    category: str = Form(...),
    new_category: str = Form(""),
    title: str = Form(...),
    content: str = Form(""),
):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    effective_category = new_category.strip() if new_category.strip() else category.strip()
    if not effective_category:
        raise HTTPException(status_code=400, detail="Category required")
    if "/" in effective_category:
        from urllib.parse import quote
        return RedirectResponse(f"/knowledge/new?error={quote('Category name must not contain \"/\".')}", status_code=303)
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")
    if not content.strip():
        from urllib.parse import quote
        return RedirectResponse(f"/knowledge/new?error={quote('Content must not be empty.')}", status_code=303)
    try:
        result = storage.save_entry(
            repo_id=repo_id,
            category=effective_category,
            title=title.strip(),
            content=content.strip(),
        )
    except GitStorageError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/knowledge/new?error={quote(str(e))}", status_code=303)
    return RedirectResponse(
        f"/knowledge/entries/{result['repo_id']}/{result['category']}/{result['slug']}",
        status_code=303,
    )


@router.get("/entries/{repo_id}/{category}/{slug}", response_class=HTMLResponse)
async def view_entry(request: Request, repo_id: str, category: str, slug: str):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    entry = storage.get_entry(repo_id, category, slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry["html"] = render_md(entry["content"])
    categories = _sidebar(storage)
    cfg = settings_store.load()
    repo_name = next(
        (r.get("name", repo_id) for r in cfg.get("repos", []) if r["id"] == repo_id),
        repo_id,
    )
    repo = settings_store.get_repo(repo_id) or {}
    writable = repo.get("permissions", {}).get("write", False)
    return templates.TemplateResponse(request, "knowledge/entry.html", {
        "entry": entry,
        "categories": categories,
        "repo_name": repo_name,
        "writable": writable,
        "configured": bool(cfg.get("repos")),
        "active_module": "knowledge",
    })


@router.get("/entries/{repo_id}/{category}/{slug}/edit", response_class=HTMLResponse)
async def edit_entry_form(request: Request, repo_id: str, category: str, slug: str, error: str = ""):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    entry = storage.get_entry(repo_id, category, slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    categories = _sidebar(storage)
    cfg = settings_store.load()
    return templates.TemplateResponse(request, "knowledge/edit.html", {
        "entry": entry,
        "categories": categories,
        "error": error,
        "configured": bool(cfg.get("repos")),
        "active_module": "knowledge",
    })


@router.post("/entries/{repo_id}/{category}/{slug}/edit")
async def update_entry(
    repo_id: str,
    category: str,
    slug: str,
    title: str = Form(...),
    content: str = Form(""),
):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    repo = settings_store.get_repo(repo_id) or {}
    if not repo.get("permissions", {}).get("write", False):
        raise HTTPException(status_code=403, detail="Repository is read-only")
    if not content.strip():
        from urllib.parse import quote
        return RedirectResponse(
            f"/knowledge/entries/{repo_id}/{category}/{slug}/edit?error={quote('Content must not be empty.')}",
            status_code=303,
        )
    try:
        result = storage.update_entry(
            repo_id=repo_id,
            category=category,
            slug=slug,
            title=title.strip(),
            content=content.strip(),
        )
    except GitStorageError as e:
        from urllib.parse import quote
        return RedirectResponse(
            f"/knowledge/entries/{repo_id}/{category}/{slug}/edit?error={quote(str(e))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/knowledge/entries/{result['repo_id']}/{result['category']}/{result['slug']}",
        status_code=303,
    )


@router.post("/entries/{repo_id}/{category}/{slug}/pin", response_class=HTMLResponse)
async def pin_entry(request: Request, repo_id: str, category: str, slug: str):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    repo = settings_store.get_repo(repo_id) or {}
    if not repo.get("permissions", {}).get("write", False):
        raise HTTPException(status_code=403, detail="Repository is read-only")
    try:
        result = storage.toggle_pin(repo_id, category, slug)
    except GitStorageError as e:
        raise HTTPException(status_code=500, detail=str(e))
    pinned = result["pinned"]
    return templates.TemplateResponse(request, "partials/pin_button.html", {
        "repo_id": repo_id,
        "category": category,
        "slug": slug,
        "pinned": pinned,
    })


@router.post("/entries/{repo_id}/{category}/{slug}/attachments")
async def upload_attachment(repo_id: str, category: str, slug: str,
                            file: UploadFile = File(...)):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    repo = settings_store.get_repo(repo_id) or {}
    if not repo.get("permissions", {}).get("write", False):
        raise HTTPException(status_code=403, detail="Repository is read-only")
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB)")
    filename = _safe_filename(file.filename or "attachment")
    try:
        storage.save_attachment(repo_id, category, slug, filename, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return RedirectResponse(f"/knowledge/entries/{repo_id}/{category}/{slug}", status_code=303)


@router.get("/entries/{repo_id}/{category}/{slug}/attachments/{filename}")
async def download_attachment(repo_id: str, category: str, slug: str, filename: str):
    filename = _safe_filename(filename)
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    data = storage.get_attachment(repo_id, category, slug, filename)
    if data is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    mime, _ = mimetypes.guess_type(filename)
    return Response(
        content=data,
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/entries/{repo_id}/{category}/{slug}/attachments/{filename}/delete")
async def delete_attachment(repo_id: str, category: str, slug: str, filename: str):
    filename = _safe_filename(filename)
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    repo = settings_store.get_repo(repo_id) or {}
    if not repo.get("permissions", {}).get("write", False):
        raise HTTPException(status_code=403, detail="Repository is read-only")
    storage.delete_attachment(repo_id, category, slug, filename)
    return RedirectResponse(f"/knowledge/entries/{repo_id}/{category}/{slug}", status_code=303)


@router.get("/entries/{repo_id}/{category}/{slug}/history", response_class=HTMLResponse)
async def entry_history(request: Request, repo_id: str, category: str, slug: str):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    entry = storage.get_entry(repo_id, category, slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    gs = storage.get_store(repo_id)
    if not gs:
        raise HTTPException(status_code=404, detail="Repo not found")
    path = f"knowledge/{category}/{slug}.md"
    commits = gs.get_file_history(path)
    sha = request.query_params.get("sha")
    diff = gs.get_file_diff(sha, path) if sha else None
    cfg = settings_store.load()
    repo_name = next(
        (r.get("name", repo_id) for r in cfg.get("repos", []) if r["id"] == repo_id),
        repo_id,
    )
    return templates.TemplateResponse(request, "knowledge/history.html", {
        "entry": entry,
        "commits": commits,
        "diff": diff,
        "selected_sha": sha,
        "repo_name": repo_name,
        "active_module": "knowledge",
    })


@router.post("/entries/{repo_id}/{category}/{slug}/delete")
async def delete_entry(repo_id: str, category: str, slug: str):
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    repo = settings_store.get_repo(repo_id) or {}
    if not repo.get("permissions", {}).get("write", False):
        raise HTTPException(status_code=403, detail="Repository is read-only")
    try:
        deleted = storage.delete_entry(repo_id, category, slug)
    except GitStorageError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse("/knowledge", status_code=303)


@router.get("/category/{category}", response_class=HTMLResponse)
async def category_view(request: Request, category: str, page: int = 1):
    storage = get_storage()
    all_entries = []
    for store in get_module_stores("knowledge", storage):
        try:
            all_entries.extend(store.get_entries(category=category))
        except Exception:
            pass
    total = len(all_entries)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))
    entries = all_entries[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    categories = _sidebar(storage)
    cfg = settings_store.load()
    return templates.TemplateResponse(request, "knowledge/category.html", {
        "category": category,
        "entries": entries,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "categories": categories,
        "configured": bool(cfg.get("repos")),
        "active_module": "knowledge",
    })
