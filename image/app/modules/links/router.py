"""Links module — router."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import settings_store
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.links.migration import migrate_flat_to_section
from modules.links.storage import LinkStorage

router = APIRouter(prefix="/links", dependencies=[require_module("links")])

_ALLOWED_SCHEMES = {"http", "https", "ftp", "ftps", "mailto", "ssh", "git"}


def _validate_url(url: str) -> str:
    """Return stripped URL or raise 400 if the scheme is not allowed."""
    url = url.strip()
    scheme = url.split(":")[0].lower() if ":" in url else ""
    if scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail=f"URL scheme '{scheme}' not allowed")
    return url


def _ensure_default_section() -> list[dict]:
    """Return sections list, auto-creating a 'default' section if none exist."""
    sections = settings_store.get_link_sections()
    if not sections:
        default = {
            "id": "default",
            "name": "Default",
            "floccus_enabled": False,
            "floccus_username": "",
            "floccus_password": "",
        }
        settings_store.upsert_link_section(default)
        sections = [default]
    return sections


def _resolve_section(sections: list[dict], section_param: str) -> dict:
    """Pick the active section from the list. Falls back to first section."""
    if section_param:
        for s in sections:
            if s["id"] == section_param:
                return s
    return sections[0]


def _get_storage(section_id: str) -> LinkStorage | None:
    """Primary storage for the section — used for writes."""
    store = get_primary_store("links", get_storage())
    if not store:
        return None
    # Auto-migrate flat links/*.yaml on first access
    flat = store.list_committed("links")
    if any(n.endswith(".yaml") for n in flat):
        migrate_flat_to_section(store, section_id)
    return LinkStorage(store, section_id)


def _get_all_storages(section_id: str) -> list[LinkStorage]:
    """Return LinkStorage for every assigned repo for the given section."""
    return [LinkStorage(s, section_id) for s in get_module_stores("links", get_storage())]


def _find_link_storage(section_id: str, link_id: str) -> LinkStorage | None:
    for ls in _get_all_storages(section_id):
        if ls.get_link(link_id):
            return ls
    return None


@router.get("", response_class=HTMLResponse)
async def list_links(
    request: Request, q: str = "", category: str = "", section: str = "", saved: str = ""
):
    from core import favorites as _fav

    sections = _ensure_default_section()
    active = _resolve_section(sections, section)

    seen: set[str] = set()
    links: list[dict] = []
    all_categories: set[str] = set()
    for ls in _get_all_storages(active["id"]):
        for lnk in ls.list_links(query=q, category=category):
            if lnk["id"] not in seen:
                seen.add(lnk["id"])
                links.append(lnk)
        all_categories.update(ls.get_categories())
    categories = sorted(all_categories)

    fav_entries = _fav.list_favorites()
    favorite_ids = {e["id"] for e in fav_entries if e.get("module") == "links"}
    return templates.TemplateResponse(
        request,
        "modules/links/list.html",
        {
            "links": links,
            "categories": categories,
            "configured": bool(_get_all_storages(active["id"])),
            "active_module": "links",
            "q": q,
            "category": category,
            "saved": saved,
            "sections": sections,
            "active_section": active,
            "favorite_ids": favorite_ids,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_link_form(request: Request, category: str = "", section: str = ""):
    sections = _ensure_default_section()
    active = _resolve_section(sections, section)
    ls = _get_storage(active["id"])
    categories = ls.get_categories() if ls else []
    return templates.TemplateResponse(
        request,
        "modules/links/form.html",
        {
            "link": None,
            "categories": categories,
            "prefill_category": category,
            "active_module": "links",
            "sections": sections,
            "active_section": active,
        },
    )


@router.post("/new")
async def create_link(
    title: str = Form(...),
    url: str = Form(...),
    category: str = Form(""),
    description: str = Form(""),
    section: str = Form(""),
):
    sections = _ensure_default_section()
    active = _resolve_section(sections, section)
    ls = _get_storage(active["id"])
    if not ls:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")
    if not url.strip():
        raise HTTPException(status_code=400, detail="URL required")
    url = _validate_url(url)
    ls.create_link({"title": title, "url": url, "category": category, "description": description})
    return RedirectResponse(f"/links?section={active['id']}&saved=1", status_code=303)


@router.get("/{link_id}/edit", response_class=HTMLResponse)
async def edit_form(link_id: str, request: Request, section: str = ""):
    sections = _ensure_default_section()
    active = _resolve_section(sections, section)
    ls = _find_link_storage(active["id"], link_id)
    link = ls.get_link(link_id) if ls else None
    if not link:
        raise HTTPException(status_code=404)
    all_categories: set[str] = set()
    for s in _get_all_storages(active["id"]):
        all_categories.update(s.get_categories())
    return templates.TemplateResponse(
        request,
        "modules/links/form.html",
        {
            "link": link,
            "categories": sorted(all_categories),
            "prefill_category": "",
            "active_module": "links",
            "sections": sections,
            "active_section": active,
        },
    )


@router.post("/{link_id}/edit")
async def update_link(
    link_id: str,
    title: str = Form(...),
    url: str = Form(...),
    category: str = Form(""),
    description: str = Form(""),
    section: str = Form(""),
):
    sections = _ensure_default_section()
    active = _resolve_section(sections, section)
    ls = _find_link_storage(active["id"], link_id)
    if not ls:
        raise HTTPException(status_code=404)
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")
    if not url.strip():
        raise HTTPException(status_code=400, detail="URL required")
    url = _validate_url(url)
    if not ls.update_link(
        link_id, {"title": title, "url": url, "category": category, "description": description}
    ):
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/links?section={active['id']}&saved=1", status_code=303)


@router.post("/{link_id}/delete")
async def delete_link(link_id: str, section: str = Form("")):
    sections = _ensure_default_section()
    active = _resolve_section(sections, section)
    ls = _find_link_storage(active["id"], link_id)
    if not ls:
        raise HTTPException(status_code=404)
    ls.delete_link(link_id)
    return RedirectResponse(f"/links?section={active['id']}", status_code=303)


@router.post("/bulk-delete", response_class=RedirectResponse)
async def bulk_delete_links(ids: list[str] = Form(default=[]), section: str = Form(default="")):
    sections = _ensure_default_section()
    active = _resolve_section(sections, section)
    if not ids:
        return RedirectResponse(f"/links?section={active['id']}", status_code=303)
    by_storage: dict[int, tuple[LinkStorage, list[str]]] = {}
    for link_id in ids:
        ls = _find_link_storage(active["id"], link_id)
        if ls:
            key = id(ls._git)
            if key not in by_storage:
                by_storage[key] = (ls, [])
            by_storage[key][1].append(link_id)
    for ls, batch in by_storage.values():
        ls.bulk_delete_links(batch)
    return RedirectResponse(f"/links?section={active['id']}", status_code=303)
