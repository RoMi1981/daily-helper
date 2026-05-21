"""Nextcloud Bookmarks REST API v2 — compatible with Floccus browser extension.

All paths use the full Nextcloud-compatible prefix so Floccus can point to the
Daily Helper base URL without any path prefix configuration.

Endpoints (compat_router — no URL prefix):
  GET    /ocs/v2.php/cloud/capabilities        — Nextcloud capabilities stub
  POST   /index.php/login/v2                   — Nextcloud Login Flow v2 init
  POST   /index.php/login/v2/poll              — Login Flow v2 poll (returns credentials)
  GET    /index.php/login/v2/grant             — Login confirmation page (HTML)

Endpoints (router — prefix /index.php/apps/bookmarks/public/rest/v2):
  GET    /bookmark                  — list bookmarks (paginated: page, limit; ?url= for exact match)
  POST   /bookmark                  — create bookmark
  GET    /bookmark/{id}             — get single bookmark
  PUT    /bookmark/{id}             — update bookmark
  DELETE /bookmark/{id}             — delete bookmark
  GET    /folder                    — root folder list
  GET    /folder/{id}/children      — folder children (real category folders for root, bookmarks for category)
  GET    /folder/{id}/hash          — change-detection hash (MD5 of sorted IDs in scope)
  POST   /folder                    — create folder → returns stable ID derived from title
  POST   /folder/{id}/import        — bulk import stub (Floccus falls back to individual creates)
  PUT    /folder/{id}               — folder update stub (no-op)
  DELETE /folder/{id}               — delete folder + all its bookmarks
  PATCH  /folder/{id}/childorder    — child order stub (no-op)
  POST   /lock                      — sync lock stub (always succeeds)
  DELETE /lock                      — sync unlock stub

Authentication: HTTP Basic Auth.
Each link section can optionally enable Floccus sync with its own username/password.
The incoming username is matched against all enabled sections; the matching section's
LinkStorage is used for all operations. If no section matches, 401 is returned.
If no sections have Floccus enabled, 503 is returned.

Password is Fernet-encrypted at rest (per-section floccus_password field).

Login Flow v2:
  Tokens are pre-approved immediately using the first enabled section's credentials.
  Floccus polls /login/v2/poll until credentials are returned, then uses Basic Auth.

Folder / Category mapping:
  Browser bookmark folders map to daily-helper categories (one level only).
  A stable folder ID is derived from the category name via MD5.
  When Floccus creates a bookmark it sends a floccus:/Category tag and/or a folders
  array — both are used to extract the target category.
  Sub-folder hierarchy beyond the first level is flattened to the first component.
"""

import hashlib
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from core import settings_store
from core.module_guard import require_module
from core.module_repos import get_primary_store
from core.state import get_storage
from modules.links.storage import LinkStorage

_NC_PREFIX = "/index.php/apps/bookmarks/public/rest/v2"

router = APIRouter(
    prefix=_NC_PREFIX,
    dependencies=[require_module("links")],
)

# Separate router without prefix for Nextcloud compatibility endpoints
compat_router = APIRouter()

# In-memory store for Login Flow v2 tokens: token -> credentials
# Tokens are pre-approved immediately and expire after 5 minutes.
_login_tokens: dict[str, dict] = {}
_TOKEN_TTL = 300  # seconds

# In-memory cache: folder_id → category name.
# Populated when Floccus calls POST /folder (before it creates bookmarks in that
# folder), so _nc_to_link can resolve the category even on first sync when no
# bookmarks with that category exist yet.
_folder_id_to_name: dict[str, str] = {}


def _cleanup_tokens() -> None:
    now = time.time()
    expired = [t for t, v in _login_tokens.items() if now - v["created"] > _TOKEN_TTL]
    for t in expired:
        _login_tokens.pop(t, None)


def _server_base(request: Request) -> str:
    """Return the public base URL, respecting X-Forwarded-Proto from reverse proxy."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{proto}://{host}"


# ── Folder / category helpers ─────────────────────────────────────────────────

def _category_folder_id(category: str) -> str:
    """Stable, deterministic folder ID derived from category name (no storage needed)."""
    return "f" + hashlib.md5(category.encode()).hexdigest()[:7]


def _category_from_folder_id(folder_id: str, categories: list[str]) -> str | None:
    """Reverse lookup: find category name for a given folder ID.

    Checks the in-memory cache first (populated by POST /folder), then falls
    back to computing the ID for every known category.
    """
    if folder_id in _folder_id_to_name:
        return _folder_id_to_name[folder_id]
    for cat in categories:
        if _category_folder_id(cat) == folder_id:
            return cat
    return None


def _category_from_floccus_tags(tags: list[str]) -> str:
    """Extract first folder level from floccus: path tags.

    Floccus encodes the bookmark's folder path as a tag, e.g.:
      floccus:/Privat         → category "Privat"
      floccus:/Work/Projects  → category "Work" (first level only)
    """
    for tag in tags:
        if tag.startswith("floccus:/"):
            path = tag[len("floccus:/"):]
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0]
    return ""


def _make_folder_item(category: str) -> dict:
    return {
        "id": _category_folder_id(category),
        "title": category,
        "parent_folder": -1,
        "userId": "user",
        "children": [],
    }


def _root_folder() -> dict:
    return {"id": -1, "title": "Root", "parent_folder": None, "userId": "user", "children": []}


# ── Data mapping ──────────────────────────────────────────────────────────────

def _link_to_nc(link: dict) -> dict:
    """Convert daily-helper link dict to Nextcloud Bookmarks format.

    Links with a category are placed in the matching category folder.
    Links without a category go to root (-1).
    """
    category = link.get("category", "")
    tags = [category] if category else []
    folder_id = _category_folder_id(category) if category else -1
    return {
        "id": link["id"],
        "url": link.get("url", ""),
        "title": link.get("title", ""),
        "description": link.get("description", ""),
        "tags": tags,
        "folders": [folder_id],
        "added": 0,
        "clickcount": 0,
        "available": True,
    }


def _nc_to_link(data: dict, categories: list[str] | None = None) -> dict:
    """Extract daily-helper link fields from Nextcloud Bookmarks request body.

    Category resolution order:
      1. folder ID in the `folders` array → reverse-lookup against known categories
      2. floccus: path tag → first path component
      3. first non-floccus: tag
    """
    tags = data.get("tags", [])
    real_tags = [t for t in tags if not t.startswith("floccus:")]

    # 1. folder ID lookup
    category = ""
    folders = data.get("folders", [])
    if folders and categories is not None:
        fid = str(folders[0])
        if fid not in ("-1", ""):
            category = _category_from_folder_id(fid, categories) or ""

    # 2. floccus: path tag
    if not category:
        category = _category_from_floccus_tags(tags)

    # 3. first real tag
    if not category and real_tags:
        category = real_tags[0]

    return {
        "url": data.get("url", "").strip(),
        "title": data.get("title", "").strip(),
        "description": data.get("description", "").strip(),
        "category": category,
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

_security = HTTPBasic()


def _get_section_storage(credentials: HTTPBasicCredentials = Depends(_security)) -> LinkStorage:
    """Authenticate via HTTP Basic Auth and return the matching section's LinkStorage.

    The username is matched against all enabled link sections. Returns a
    LinkStorage scoped to the matching section on success. Raises 503 if no
    sections have Floccus enabled, 401 if credentials don't match any section.
    """
    cfg = settings_store.load()
    sections = cfg.get("link_sections", [])

    any_enabled = False
    for section in sections:
        if not section.get("floccus_enabled"):
            continue
        api_user = section.get("floccus_username", "").strip()
        api_pass = section.get("floccus_password", "").strip()
        if not api_user or not api_pass:
            continue
        any_enabled = True
        user_ok = secrets.compare_digest(credentials.username.encode(), api_user.encode())
        pass_ok = secrets.compare_digest(credentials.password.encode(), api_pass.encode())
        if user_ok and pass_ok:
            store = get_primary_store("links", get_storage())
            if not store:
                raise HTTPException(status_code=503, detail="Storage not configured")
            return LinkStorage(store, section["id"])

    if not any_enabled:
        raise HTTPException(status_code=503, detail="API sync not configured")

    raise HTTPException(
        status_code=401,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


# ── Compat endpoints (no prefix) ─────────────────────────────────────────────

@compat_router.get("/ocs/v2.php/cloud/capabilities")
async def nextcloud_capabilities():
    """Minimal Nextcloud capabilities stub required by Floccus during login."""
    return JSONResponse({
        "ocs": {
            "meta": {"status": "ok", "statuscode": 200, "message": "OK"},
            "data": {
                "capabilities": {
                    "bookmarks": {"javascript-bookmarks": True}
                }
            }
        }
    })


@compat_router.post("/index.php/login/v2")
async def login_v2_init(request: Request):
    """Nextcloud Login Flow v2 — init. Issues a pending token; credentials entered on grant page."""
    cfg = settings_store.load()
    sections = cfg.get("link_sections", [])
    enabled = [
        s for s in sections
        if s.get("floccus_enabled")
        and s.get("floccus_username", "").strip()
        and s.get("floccus_password", "").strip()
    ]
    if not enabled:
        raise HTTPException(status_code=503, detail="API sync not configured")

    _cleanup_tokens()
    token = secrets.token_urlsafe(32)
    # Token starts as pending (no credentials yet); approved after user logs in on grant page
    _login_tokens[token] = {
        "created": time.time(),
        "approved": False,
    }
    base = _server_base(request)
    return JSONResponse({
        "poll": {
            "token": token,
            "endpoint": f"{base}/index.php/login/v2/poll",
        },
        "login": f"{base}/index.php/login/v2/grant?token={token}",
    })


@compat_router.post("/index.php/login/v2/poll")
async def login_v2_poll(request: Request):
    """Nextcloud Login Flow v2 — poll. Returns credentials once the user has logged in."""
    _cleanup_tokens()
    form = await request.form()
    token = form.get("token", "")
    entry = _login_tokens.get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="Token not found or expired")
    if not entry.get("approved"):
        # Still waiting for user to log in on the grant page
        raise HTTPException(status_code=404, detail="Waiting for user login")
    _login_tokens.pop(token, None)
    return JSONResponse({
        "server": _server_base(request),
        "loginName": entry["loginName"],
        "appPassword": entry["appPassword"],
    })


@compat_router.get("/index.php/login/v2/grant", response_class=HTMLResponse)
async def login_v2_grant(token: str = ""):
    """Login form shown when Floccus opens the grant URL. User must enter credentials."""
    if not token:
        return HTMLResponse("""
        <html><body style="font-family:sans-serif;text-align:center;padding:3rem">
        <h2>⚠️ Daily Helper — Invalid Link</h2>
        <p>Missing token. Please start the Floccus setup again.</p>
        </body></html>
        """, status_code=400)
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Daily Helper — Floccus Login</title>
      <style>
        body {{ font-family: sans-serif; display: flex; align-items: center; justify-content: center;
               min-height: 100vh; margin: 0; background: #f5f5f5; }}
        .box {{ background: white; padding: 2rem 2.5rem; border-radius: 8px;
                box-shadow: 0 2px 12px rgba(0,0,0,.12); width: 320px; }}
        h2 {{ margin: 0 0 1.5rem; font-size: 1.2rem; text-align: center; }}
        label {{ display: block; font-size: 0.85rem; margin-bottom: 0.25rem; font-weight: 600; }}
        input {{ width: 100%; box-sizing: border-box; padding: 0.5rem 0.6rem;
                 border: 1px solid #ccc; border-radius: 4px; font-size: 0.95rem; margin-bottom: 1rem; }}
        button {{ width: 100%; padding: 0.6rem; background: #2563eb; color: white;
                  border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
        button:hover {{ background: #1d4ed8; }}
        .error {{ color: #dc2626; font-size: 0.85rem; margin-bottom: 1rem; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="box">
        <h2>📅 Daily Helper<br><span style="font-weight:400;font-size:0.95rem">Floccus Login</span></h2>
        <form method="post" action="/index.php/login/v2/grant">
          <input type="hidden" name="token" value="{token}">
          <label>Username</label>
          <input type="text" name="username" autocomplete="username" autofocus>
          <label>Password</label>
          <input type="password" name="password" autocomplete="current-password">
          <button type="submit">Authorize</button>
        </form>
      </div>
    </body>
    </html>
    """)


@compat_router.post("/index.php/login/v2/grant", response_class=HTMLResponse)
async def login_v2_grant_submit(request: Request):
    """Handles the login form submission. Validates credentials and approves the token."""
    form = await request.form()
    token = form.get("token", "")
    username = form.get("username", "").strip()
    password = form.get("password", "").strip()

    entry = _login_tokens.get(token)
    if not entry or entry.get("approved"):
        return HTMLResponse("""
        <html><body style="font-family:sans-serif;text-align:center;padding:3rem">
        <h2>⚠️ Daily Helper — Invalid or expired token</h2>
        <p>Please start the Floccus setup again.</p>
        </body></html>
        """, status_code=400)

    cfg = settings_store.load()
    sections = cfg.get("link_sections", [])
    matched = False
    for section in sections:
        if not section.get("floccus_enabled"):
            continue
        api_user = section.get("floccus_username", "").strip()
        api_pass = section.get("floccus_password", "").strip()
        if not api_user or not api_pass:
            continue
        if (secrets.compare_digest(username.encode(), api_user.encode()) and
                secrets.compare_digest(password.encode(), api_pass.encode())):
            entry["loginName"] = api_user
            entry["appPassword"] = api_pass
            entry["approved"] = True
            matched = True
            break

    if not matched:
        # Show the form again with an error
        token_safe = token.replace('"', '')
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>Daily Helper — Floccus Login</title>
          <style>
            body {{ font-family: sans-serif; display: flex; align-items: center; justify-content: center;
                   min-height: 100vh; margin: 0; background: #f5f5f5; }}
            .box {{ background: white; padding: 2rem 2.5rem; border-radius: 8px;
                    box-shadow: 0 2px 12px rgba(0,0,0,.12); width: 320px; }}
            h2 {{ margin: 0 0 1.5rem; font-size: 1.2rem; text-align: center; }}
            label {{ display: block; font-size: 0.85rem; margin-bottom: 0.25rem; font-weight: 600; }}
            input {{ width: 100%; box-sizing: border-box; padding: 0.5rem 0.6rem;
                     border: 1px solid #ccc; border-radius: 4px; font-size: 0.95rem; margin-bottom: 1rem; }}
            button {{ width: 100%; padding: 0.6rem; background: #2563eb; color: white;
                      border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
            button:hover {{ background: #1d4ed8; }}
            .error {{ color: #dc2626; font-size: 0.85rem; margin-bottom: 1rem; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="box">
            <h2>📅 Daily Helper<br><span style="font-weight:400;font-size:0.95rem">Floccus Login</span></h2>
            <p class="error">Invalid credentials. Please try again.</p>
            <form method="post" action="/index.php/login/v2/grant">
              <input type="hidden" name="token" value="{token_safe}">
              <label>Username</label>
              <input type="text" name="username" value="{username.replace('"', '')}" autocomplete="username" autofocus>
              <label>Password</label>
              <input type="password" name="password" autocomplete="current-password">
              <button type="submit">Authorize</button>
            </form>
          </div>
        </body>
        </html>
        """, status_code=401)

    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>Daily Helper — Authorized</title></head>
    <body style="font-family:sans-serif;text-align:center;padding:3rem">
    <h2>✅ Daily Helper — Authorized</h2>
    <p>You can close this tab. Floccus will connect automatically.</p>
    </body>
    </html>
    """)


# ── Bookmark endpoints ────────────────────────────────────────────────────────

@router.get("/bookmark")
async def list_bookmarks(
    ls: LinkStorage = Depends(_get_section_storage),
    page: int = 0,
    limit: int = 300,
    url: str | None = None,
):
    all_links = ls.list_links()
    if url:
        all_links = [lk for lk in all_links if lk.get("url", "") == url]
    start = page * limit
    page_links = all_links[start : start + limit]
    return JSONResponse({"status": "success", "data": [_link_to_nc(lk) for lk in page_links]})


@router.post("/bookmark")
async def create_bookmark(request: Request, ls: LinkStorage = Depends(_get_section_storage)):
    body = await request.json()
    data = _nc_to_link(body, ls.get_categories())
    if not data["url"]:
        raise HTTPException(status_code=400, detail="url required")
    link = ls.create_link(data)
    return JSONResponse({"status": "success", "item": _link_to_nc(link)}, status_code=200)


@router.get("/bookmark/{link_id}")
async def get_bookmark(link_id: str, ls: LinkStorage = Depends(_get_section_storage)):
    link = ls.get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return JSONResponse({"status": "success", "item": _link_to_nc(link)})


@router.put("/bookmark/{link_id}")
async def update_bookmark(link_id: str, request: Request, ls: LinkStorage = Depends(_get_section_storage)):
    body = await request.json()
    data = _nc_to_link(body, ls.get_categories())
    link = ls.update_link(link_id, data)
    if not link:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return JSONResponse({"status": "success", "item": _link_to_nc(link)})


@router.delete("/bookmark/{link_id}")
async def delete_bookmark(link_id: str, ls: LinkStorage = Depends(_get_section_storage)):
    deleted = ls.delete_link(link_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return JSONResponse({"status": "success"})


# ── Folder endpoints ──────────────────────────────────────────────────────────

@router.get("/folder")
async def list_folders(_: LinkStorage = Depends(_get_section_storage)):
    """Root folder list — Floccus uses this to discover the folder tree."""
    return JSONResponse({"status": "success", "data": [_root_folder()]})


@router.get("/folder/{folder_id}/children")
async def folder_children(folder_id: str, ls: LinkStorage = Depends(_get_section_storage)):
    """Return folder children with full bookmark data (layers=-1 is the common call).

    Root (-1): one sub-folder per category + uncategorized bookmarks directly.
    Category folder: all bookmarks in that category.
    """
    all_links = ls.list_links()

    if folder_id == "-1":
        by_cat: dict[str, list[dict]] = {}
        root_links: list[dict] = []
        for link in all_links:
            cat = link.get("category", "")
            if cat:
                by_cat.setdefault(cat, []).append(link)
            else:
                root_links.append(link)

        data: list[dict] = []
        for cat in sorted(by_cat):
            folder = _make_folder_item(cat)
            folder["children"] = [{"type": "bookmark", **_link_to_nc(lk)} for lk in by_cat[cat]]
            data.append({"type": "folder", **folder})
        for link in root_links:
            data.append({"type": "bookmark", **_link_to_nc(link)})

        return JSONResponse({"status": "success", "data": data})

    categories = ls.get_categories()
    category = _category_from_folder_id(folder_id, categories)
    if not category:
        return JSONResponse({"status": "success", "data": []})

    cat_links = [lk for lk in all_links if lk.get("category", "") == category]
    return JSONResponse({
        "status": "success",
        "data": [{"type": "bookmark", **_link_to_nc(lk)} for lk in cat_links],
    })


@router.get("/folder/{folder_id}/hash")
async def folder_hash(folder_id: str, ls: LinkStorage = Depends(_get_section_storage)):
    """Hash for change detection — MD5 of sorted bookmark IDs in scope."""
    all_links = ls.list_links()

    if folder_id == "-1":
        links_in_scope = all_links
    else:
        categories = ls.get_categories()
        category = _category_from_folder_id(folder_id, categories)
        links_in_scope = [lk for lk in all_links if lk.get("category", "") == (category or "\x00")]

    h = hashlib.md5(",".join(sorted(lk["id"] for lk in links_in_scope)).encode()).hexdigest()
    return JSONResponse({"status": "success", "data": {"hash": h}})


@router.post("/folder")
async def create_folder(request: Request, _: LinkStorage = Depends(_get_section_storage)):
    """Create folder — returns a stable ID derived from the folder title.

    No storage is needed: the ID is deterministically computed from the name
    so it remains consistent across requests.
    """
    try:
        body = await request.json()
        title = body.get("title", "").strip()
    except Exception:
        title = ""

    if title:
        folder_id = _category_folder_id(title)
        _folder_id_to_name[folder_id] = title  # cache for reverse-lookup in _nc_to_link
        return JSONResponse({"status": "success", "item": _make_folder_item(title)})
    return JSONResponse({"status": "success", "item": _root_folder()})


@router.put("/folder/{folder_id}")
async def update_folder(folder_id: str, _: LinkStorage = Depends(_get_section_storage)):
    """Folder update stub."""
    return JSONResponse({"status": "success", "item": _root_folder()})


@router.delete("/folder/{folder_id}")
async def delete_folder(folder_id: str, ls: LinkStorage = Depends(_get_section_storage)):
    """Delete folder — removes all bookmarks with that category.

    In our model a folder = a category tag.  Deleting the folder means deleting
    every link whose category maps to this folder ID.  If the folder is unknown
    (already gone), return success silently.
    """
    categories = ls.get_categories()
    category = _category_from_folder_id(folder_id, categories)
    if not category:
        _folder_id_to_name.pop(folder_id, None)
        return JSONResponse({"status": "success"})

    for link in ls.list_links():
        if link.get("category", "") == category:
            ls.delete_link(link["id"])

    _folder_id_to_name.pop(folder_id, None)
    return JSONResponse({"status": "success"})


@router.delete("/folder/{folder_id}/bookmarks/{link_id}")
async def remove_bookmark_from_folder(
    folder_id: str, link_id: str, ls: LinkStorage = Depends(_get_section_storage)
):
    """Remove a bookmark from a folder.

    In our flat model each bookmark belongs to exactly one folder (= category),
    so removing it from its folder deletes it entirely.
    Removing from a folder it doesn't belong to is a no-op (200).
    """
    link = ls.get_link(link_id)
    if not link:
        return JSONResponse({"status": "success"})
    cat = link.get("category", "")
    link_folder_id = _category_folder_id(cat) if cat else "-1"
    if folder_id == link_folder_id or folder_id == "-1":
        ls.delete_link(link_id)
    return JSONResponse({"status": "success"})


@router.post("/folder/{folder_id}/import")
async def import_folder(folder_id: str, _: LinkStorage = Depends(_get_section_storage)):
    """Bulk import — not implemented.

    Returning 501 causes Floccus to fall back to individual POST /bookmark creates,
    which is the correct path for our implementation.
    """
    return JSONResponse({"status": "error", "data": []}, status_code=501)


@router.patch("/folder/{folder_id}/childorder")
async def reorder_folder(folder_id: str, _: LinkStorage = Depends(_get_section_storage)):
    """Child order stub — no-op."""
    return JSONResponse({"status": "success"})


# ── Lock endpoints ────────────────────────────────────────────────────────────

@router.post("/lock")
async def lock(_: LinkStorage = Depends(_get_section_storage)):
    """Sync lock stub — always succeeds (single-user, no real locking needed)."""
    return JSONResponse({"status": "success"})


@router.delete("/lock")
async def unlock(_: LinkStorage = Depends(_get_section_storage)):
    """Sync unlock stub."""
    return JSONResponse({"status": "success"})
