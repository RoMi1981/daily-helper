"""Daily Helper — FastAPI application."""

import asyncio
import logging
import os
import signal
import socket
import threading

logger = logging.getLogger(__name__)

APP_VERSION = os.environ.get("APP_VERSION", "dev")

from core import cache, permission_checker, settings_store
from core import tls as tls_mod
from core.global_search import run_global_search
from core.state import get_storage, reset_storage
from core.storage import GitStorage, GitStorageError
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from modules.appointments import router as appointments_router
from modules.calendar import router as calendar_router
from modules.eol import router as eol_router
from modules.history import router as history_router
from modules.knowledge import router as knowledge_router
from modules.links import router as links_router
from modules.links.floccus_api import (
    compat_router as floccus_compat_router,
)
from modules.links.floccus_api import (
    router as floccus_router,
)
from modules.mail_templates import router as mail_templates_router
from modules.memes import router as memes_router
from modules.motd import router as motd_router
from modules.notes import router as notes_router
from modules.operations import router as operations_router
from modules.potd import router as potd_router
from modules.rss import router as rss_router
from modules.runbooks import router as runbooks_router
from modules.snippets import router as snippets_router
from modules.tasks import router as tasks_router
from modules.ticket_templates import router as ticket_templates_router
from modules.vacations import router as vacations_router
from modules.widgets import router as widgets_router

app = FastAPI(title="Daily Helper")
app.mount("/static", StaticFiles(directory="static"), name="static")

from core.csrf_guard import CsrfOriginMiddleware

app.add_middleware(CsrfOriginMiddleware)


@app.exception_handler(GitStorageError)
async def git_storage_error_handler(request: Request, exc: GitStorageError):
    """Return 503 instead of crashing on unhandled push/pull failures."""
    from fastapi.responses import JSONResponse

    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        from fastapi.responses import HTMLResponse

        return HTMLResponse(
            f'<div class="flash-error">Git error: {exc}</div>',
            status_code=503,
        )
    return JSONResponse({"detail": str(exc)}, status_code=503)


from datetime import datetime as _datetime

from core.templates import templates


def _datetimeformat(ts: int) -> str:
    try:
        return _datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


templates.env.filters["datetimeformat"] = _datetimeformat

from core.i18n import get_current_lang, invalidate_lang_cache
from core.i18n import t as _i18n_t


def _t(key: str, **kwargs) -> str:
    return _i18n_t(key, get_current_lang(), **kwargs)


templates.env.globals["t"] = _t
templates.env.globals["get_lang"] = get_current_lang

app.include_router(knowledge_router.router)
app.include_router(tasks_router.router)
app.include_router(vacations_router.router)
app.include_router(operations_router.router)
app.include_router(mail_templates_router.router)
app.include_router(ticket_templates_router.router)
app.include_router(notes_router.router)
app.include_router(links_router.router)
app.include_router(runbooks_router.router)
app.include_router(appointments_router.router)
app.include_router(calendar_router.router)
app.include_router(snippets_router.router)
app.include_router(floccus_router)
app.include_router(floccus_compat_router)
app.include_router(history_router.router)
app.include_router(memes_router.router)
app.include_router(motd_router.router)
app.include_router(potd_router.router)
app.include_router(rss_router.router)
app.include_router(eol_router.router)
app.include_router(widgets_router.router)

# Apply cache limits from persisted settings on startup
_startup_cfg = settings_store.load()
cache.configure_limits(_startup_cfg.get("cache_max_file_mb", 10))
del _startup_cfg


async def _offline_retry_loop():
    """Background task: periodically retry queued offline pushes and repos
    that failed to init (e.g. network/VPN unreachable at startup) — so both
    self-heal without a manual sync/flush/restart once connectivity returns.
    """
    first = True
    while True:
        # First pass runs sooner than the steady-state interval so a repo
        # that's still unreachable right at boot recovers quickly once the
        # network comes up, instead of waiting a full minute.
        await asyncio.sleep(10 if first else 60)
        first = False
        try:
            storage = get_storage()
            if storage:
                storage.retry_all_pending()
                storage.retry_failed()
        except Exception as exc:
            logger.debug("Offline retry loop error: %s", exc)


@app.on_event("startup")
async def _start_background_tasks():
    asyncio.create_task(_offline_retry_loop())


# ───────────────────────────────────────── Home → Dashboard ──


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    from starlette.responses import RedirectResponse

    return RedirectResponse("/widgets", status_code=302)


# ───────────────────────────────────────── Global Search ──

_HELP_LABELS: dict[str, str] = {
    "knowledge": "Knowledge",
    "tasks": "Tasks",
    "notes": "Notes",
    "links": "Links",
    "runbooks": "Runbooks",
    "snippets": "Snippets",
    "mail-templates": "Mail Templates",
    "ticket-templates": "Ticket Templates",
    "vacations": "Vacations",
    "appointments": "Appointments",
    "motd": "MOTD",
    "potd": "Picture of the Day",
    "memes": "Memes",
    "rss": "RSS Reader",
    "eol": "EOL Tracker",
    "widgets": "Widget Dashboard",
    "calendar": "Calendar",
    "history": "History",
    "operations": "Operations",
}

_HELP_BACK: dict[str, str] = {
    "knowledge": "/knowledge",
    "tasks": "/tasks",
    "notes": "/notes",
    "links": "/links",
    "runbooks": "/runbooks",
    "snippets": "/snippets",
    "mail-templates": "/mail-templates",
    "ticket-templates": "/ticket-templates",
    "vacations": "/vacations",
    "appointments": "/appointments",
    "motd": "/motd",
    "potd": "/potd",
    "memes": "/memes",
    "rss": "/rss",
    "eol": "/eol",
    "widgets": "/widgets",
    "calendar": "/calendar",
    "history": "/history",
    "operations": "/operations",
}


# base.html's `?` shortcut reads this list; it used to carry its own copy with
# ten of the nineteen modules.
templates.env.globals["help_modules"] = sorted(_HELP_LABELS)


@app.get("/help/{module}", response_class=HTMLResponse)
async def module_help(request: Request, module: str):
    import pathlib

    from modules.knowledge.router import render_md

    if module not in _HELP_LABELS:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Help page not found")
    help_dir = pathlib.Path(__file__).parent / "help"
    cfg = settings_store.load()
    lang = cfg.get("language", "en")
    lang_code = "de" if lang == "de" else "en"
    help_file = help_dir / lang_code / f"{module}.md"
    if not help_file.exists():
        help_file = help_dir / "en" / f"{module}.md"
    if not help_file.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Help file not found")
    html = render_md(help_file.read_text(encoding="utf-8"))
    return templates.TemplateResponse(
        request,
        "help.html",
        {
            "html": html,
            "module_label": _HELP_LABELS[module],
            "back_url": _HELP_BACK.get(module, "/"),
            "active_module": module.replace("-", "_"),
        },
    )


@app.get("/search", response_class=HTMLResponse)
async def global_search(request: Request, q: str = "", date_from: str = "", date_to: str = ""):
    cfg = settings_store.load()
    q_stripped = q.strip()
    df = date_from.strip()
    dt = date_to.strip()
    groups = run_global_search(q_stripped, df, dt, cfg.get("modules_enabled", {}), get_storage())
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "q": q_stripped,
            "date_from": df,
            "date_to": dt,
            "groups": groups,
            "total": sum(len(g["results"]) for g in groups),
            "active_module": "search",
        },
    )


# ───────────────────────────────────────── API ──


@app.post("/api/preview", response_class=HTMLResponse)
async def preview_markdown(request: Request):
    import asyncio as _asyncio

    from modules.knowledge.router import _PREVIEW_MAX, _PREVIEW_WINDOW, _preview_rate, render_md

    client = request.client.host if request.client else "unknown"
    now = _asyncio.get_event_loop().time()
    hits = [t for t in _preview_rate.get(client, []) if now - t < _PREVIEW_WINDOW]
    if len(hits) >= _PREVIEW_MAX:
        raise HTTPException(status_code=429, detail="Too many preview requests")
    hits.append(now)
    _preview_rate[client] = hits
    body = await request.json()
    return HTMLResponse(render_md(body.get("content", "")))


# ───────────────────────────────────────── Settings ──


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: bool = False, error: str = ""):
    cfg = settings_store.load()
    storage = get_storage()
    categories = storage.get_categories() if storage else []
    if cfg.get("tls_san", "localhost, 127.0.0.1") == "localhost, 127.0.0.1":
        local_ip = _local_ip()
        if local_ip and local_ip != "127.0.0.1":
            cfg["tls_san"] = f"localhost, 127.0.0.1, {local_ip}"
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "cfg": cfg,
            "categories": categories,
            "saved": saved,
            "error": error,
            "new_key": settings_store.generate_new_key(),
            "tls_ca_pem": tls_mod.get_ca_cert_pem(),
            "tls_cert_expiry": tls_mod.get_cert_expiry(),
        },
    )


@app.post("/settings/appearance")
async def save_appearance_settings(
    theme_mode: str = Form("auto"),
    language: str = Form("en"),
):
    cfg = settings_store.load()
    cfg["theme_mode"] = theme_mode if theme_mode in ("dark", "light", "auto") else "auto"
    cfg["language"] = language if language in ("en", "de") else "en"
    settings_store.save(cfg)
    invalidate_lang_cache()
    return RedirectResponse("/settings?saved=1#appearance", status_code=303)


@app.post("/settings/git-identity")
async def save_git_identity(
    git_user_name: str = Form("Daily Helper"),
    git_user_email: str = Form("daily@helper.local"),
):
    cfg = settings_store.load()
    cfg["git_user_name"] = git_user_name.strip()
    cfg["git_user_email"] = git_user_email.strip()
    settings_store.save(cfg)
    reset_storage()
    return RedirectResponse("/settings?saved=1", status_code=303)


def _url_exists(url: str, exclude_id: str = "") -> bool:
    """Return True if any repo (other than exclude_id) already uses this URL."""
    cfg = settings_store.load()
    return any(r["url"].strip() == url.strip() for r in cfg.get("repos", []) if r.get("id") != exclude_id)


@app.post("/settings/repos")
async def add_repo(
    name: str = Form(...),
    url: str = Form(...),
    platform: str = Form("gitea"),
    auth_mode: str = Form("none"),
    ssh_key: str = Form(""),
    pat: str = Form(""),
    ca_cert: str = Form(""),
    basic_user: str = Form(""),
    basic_password: str = Form(""),
    gpg_key: str = Form(""),
    gpg_passphrase: str = Form(""),
    git_user_name: str = Form(""),
    git_user_email: str = Form(""),
):
    if _url_exists(url):
        return RedirectResponse("/settings?error=A+repo+with+this+URL+already+exists", status_code=303)
    repo = {
        "name": name.strip(),
        "url": url.strip(),
        "platform": platform,
        "auth_mode": auth_mode,
        "ssh_key": ssh_key.strip(),
        "pat": pat.strip(),
        "ca_cert": ca_cert.strip(),
        "basic_user": basic_user.strip(),
        "basic_password": basic_password.strip(),
        "gpg_key": gpg_key.strip(),
        "gpg_passphrase": gpg_passphrase.strip(),
        "git_user_name": git_user_name.strip(),
        "git_user_email": git_user_email.strip(),
        "permissions": {"read": False, "write": False},
        "last_checked": "",
    }
    settings_store.upsert_repo(repo)
    reset_storage()
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/repos/{repo_id}")
async def update_repo(
    repo_id: str,
    name: str = Form(...),
    url: str = Form(...),
    platform: str = Form("gitea"),
    auth_mode: str = Form("none"),
    ssh_key: str = Form(""),
    pat: str = Form(""),
    ca_cert: str = Form(""),
    basic_user: str = Form(""),
    basic_password: str = Form(""),
    gpg_key: str = Form(""),
    gpg_passphrase: str = Form(""),
    git_user_name: str = Form(""),
    git_user_email: str = Form(""),
    push_retry_count: int = Form(1),
):
    existing = settings_store.get_repo(repo_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Repo not found")
    if _url_exists(url, exclude_id=repo_id):
        return RedirectResponse("/settings?error=A+repo+with+this+URL+already+exists", status_code=303)
    repo = dict(existing)
    repo.update(
        {
            "name": name.strip(),
            "url": url.strip(),
            "platform": platform,
            "auth_mode": auth_mode,
            "ssh_key": ssh_key.strip() if ssh_key.strip() else existing.get("ssh_key", ""),
            "pat": pat.strip() if pat.strip() else existing.get("pat", ""),
            "ca_cert": ca_cert.strip() if ca_cert.strip() else existing.get("ca_cert", ""),
            "basic_user": basic_user.strip() if basic_user.strip() else existing.get("basic_user", ""),
            "basic_password": basic_password.strip() if basic_password.strip() else existing.get("basic_password", ""),
            "gpg_key": gpg_key.strip() if gpg_key.strip() else existing.get("gpg_key", ""),
            "gpg_passphrase": gpg_passphrase.strip() if gpg_passphrase.strip() else existing.get("gpg_passphrase", ""),
            "git_user_name": git_user_name.strip(),
            "git_user_email": git_user_email.strip(),
            "push_retry_count": max(0, min(10, push_retry_count)),
            "permissions": {"read": False, "write": False},
            "last_checked": "",
        }
    )
    settings_store.upsert_repo(repo)
    reset_storage()
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/repos/{repo_id}/delete")
async def delete_repo(repo_id: str):
    settings_store.delete_repo(repo_id)
    reset_storage()
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/repos/{repo_id}/copy")
async def copy_repo(
    repo_id: str,
    name: str = Form(...),
    url: str = Form(...),
):
    source = settings_store.get_repo(repo_id)
    if not source:
        raise HTTPException(status_code=404, detail="Repo not found")
    if _url_exists(url):
        return RedirectResponse("/settings?error=A+repo+with+this+URL+already+exists", status_code=303)
    new_repo = dict(source)
    new_repo.pop("id", None)
    new_repo["name"] = name.strip()
    new_repo["url"] = url.strip()
    new_repo["permissions"] = {"read": False, "write": False}
    new_repo["last_checked"] = ""
    settings_store.upsert_repo(new_repo)
    reset_storage()
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/repos/{repo_id}/toggle", response_class=HTMLResponse)
async def toggle_repo(repo_id: str):
    new_state = settings_store.toggle_repo_enabled(repo_id)
    reset_storage()
    label = "Disable" if new_state else "Enable"
    badge = "" if new_state else '<span class="perm-badge perm-none" style="margin-left:0.5rem">disabled</span>'
    return HTMLResponse(
        f'<span id="toggle-{repo_id}">'
        f'<button type="button" class="btn btn-secondary btn-sm" '
        f'hx-post="/settings/repos/{repo_id}/toggle" hx-target="#toggle-{repo_id}" hx-swap="outerHTML">'
        f"{label}</button>{badge}"
        f"</span>",
    )


def _make_probe(repo_id: str, url: str, repo_settings: dict) -> "GitStorage":
    """Create a GitStorage probe object without cloning (for connection tests)."""
    from pathlib import Path as _Path

    probe = GitStorage.__new__(GitStorage)
    probe.repo_id = repo_id
    probe.repo_url = url
    probe.local_path = _Path(f"/tmp/daily-helper/probe-{repo_id}")
    probe._settings = repo_settings
    probe._ssh_key_file = None
    probe._ca_cert_file = None
    probe._askpass_file = None
    probe._gpg_home = None
    probe._gpg_key_id = None
    probe._last_pull = 0.0
    probe._write_lock = threading.RLock()
    probe._setup_credentials()
    return probe


@app.post("/settings/repos/{repo_id}/check", response_class=HTMLResponse)
async def check_repo_permissions(repo_id: str):
    import html as _html

    try:
        repo = settings_store.get_repo(repo_id)
        if not repo:
            return HTMLResponse('<span class="perm-error">Repo not found</span>')

        url = repo.get("url", "")
        auth_mode = repo.get("auth_mode", "none")
        pat = repo.get("pat", "")
        platform = repo.get("platform", "gitea")

        if auth_mode == "pat" and pat:
            # Network-bound and up to 15s — off the event loop, or every other
            # request on the app waits for this one to come back.
            result = await asyncio.to_thread(
                permission_checker.check_permissions, url, platform, pat, repo.get("ca_cert", "")
            )
        elif auth_mode == "ssh" and repo.get("ssh_key"):
            cfg = settings_store.load()
            repo_settings = dict(repo)
            repo_settings["_global"] = {
                "git_user_name": cfg.get("git_user_name", "Daily Helper"),
                "git_user_email": cfg.get("git_user_email", "daily@helper.local"),
            }
            probe = _make_probe(repo_id, url, repo_settings)
            info = await asyncio.to_thread(probe.test_connection)
            probe.cleanup()
            result = {
                "read": info["ok"],
                "write": info["ok"],
                "error": None if info["ok"] else info["output"],
            }
        elif auth_mode == "basic" and repo.get("basic_password"):
            cfg = settings_store.load()
            repo_settings = dict(repo)
            repo_settings["_global"] = {
                "git_user_name": cfg.get("git_user_name", "Daily Helper"),
                "git_user_email": cfg.get("git_user_email", "daily@helper.local"),
            }
            probe = _make_probe(repo_id, url, repo_settings)
            info = await asyncio.to_thread(probe.test_connection)
            probe.cleanup()
            result = {
                "read": info["ok"],
                "write": info["ok"],
                "error": None if info["ok"] else info["output"],
            }
        elif auth_mode == "none":
            result = {"read": True, "write": False, "error": None}
        else:
            result = {"read": False, "write": False, "error": "No credentials configured"}
    except Exception:
        logger.exception("Permission check failed for repo %s", repo_id)
        return HTMLResponse('<span class="perm-error">Error: permission check failed, see server log</span>')

    settings_store.update_permissions(
        repo_id,
        {
            "read": result["read"],
            "write": result["write"],
        },
    )
    reset_storage()

    parts = []
    if result["read"]:
        parts.append('<span class="perm-badge perm-read">read</span>')
    if result["write"]:
        parts.append('<span class="perm-badge perm-write">write</span>')
    if not result["read"]:
        parts.append('<span class="perm-badge perm-none">no access</span>')
    if result.get("error"):
        parts.append(f'<span class="perm-error">{_html.escape(str(result["error"]))}</span>')

    return HTMLResponse(" ".join(parts))


@app.post("/settings/repos/{repo_id}/test", response_class=HTMLResponse)
async def test_repo_connection(repo_id: str):
    import html as _html

    try:
        repo = settings_store.get_repo(repo_id)
        if not repo:
            return HTMLResponse('<div class="diag-result diag-error"><b>Repo not found</b></div>')

        url = repo.get("url", "")
        platform = repo.get("platform", "gitea")
        cfg = settings_store.load()
        repo_settings = dict(repo)
        repo_settings["_global"] = {
            "git_user_name": cfg.get("git_user_name", "Daily Helper"),
            "git_user_email": cfg.get("git_user_email", "daily@helper.local"),
        }

        # Derive API check URL (informational only, no network call)
        api_base = permission_checker._api_base(url, platform) or "?"
        parsed = permission_checker._parse_owner_repo(url)
        if parsed:
            owner, repo_name = parsed
            if platform == "gitlab":
                import urllib.parse as _up

                api_url = f"{api_base}/projects/{_up.quote(f'{owner}/{repo_name}', safe='')}"
            else:
                api_url = f"{api_base}/repos/{owner}/{repo_name}"
        else:
            api_url = api_base

        probe = _make_probe(repo_id, url, repo_settings)
        try:
            info = probe.test_connection()
        finally:
            probe.cleanup()

        # API scope check (PAT only)
        api_ok = None
        api_error = ""
        if repo.get("auth_mode") == "pat" and repo.get("pat"):
            perm = permission_checker.check_permissions(url, platform, repo["pat"], repo.get("ca_cert", ""))
            api_ok = perm.get("read", False)
            api_error = perm.get("error") or ""

        read_cell = "✓ yes" if info["read_ok"] else "✗ no"
        if info["write_tested"]:
            write_cell = "✓ yes" if info["write_ok"] else f"✗ no — {info['write_output']}"
        else:
            write_cell = "not tested (read failed)"
        api_cell = (
            ("✓ yes" if api_ok else "✗ no" + (f" — {api_error}" if api_error else "")) if api_ok is not None else "n/a"
        )

        overall_ok = info["read_ok"] and (info["write_ok"] if info["write_tested"] else False)
        status_cls = "diag-ok" if overall_ok else ("diag-warn" if info["read_ok"] else "diag-error")
        if overall_ok:
            status_text = "✓ Connection successful — read and write verified"
        elif info["read_ok"]:
            status_text = "⚠ Read OK — write test failed"
        else:
            status_text = "✗ Connection failed"

        rows = [
            ("Auth mode", info["auth_mode"]),
            ("Platform", info["platform"]),
            ("PAT present", "yes" if info["pat_present"] else "no"),
            ("CA cert present", "yes" if info["ca_cert_present"] else "no"),
            ("SSH key present", "yes" if info["ssh_key_present"] else "no"),
            ("git read", read_cell),
            ("git write", write_cell),
            ("API access (read_api / repo scope)", api_cell),
            ("Effective URL", info["effective_url"]),
            ("API check URL", api_url),
        ]
        table = "".join(f'<dt>{k}</dt><dd class="monospace">{_html.escape(str(v))}</dd>' for k, v in rows)
        write_details = ""
        if info["write_tested"] and info["write_ok"]:
            write_details = (
                f'<div class="diag-output-label">Write test (branch <code>daily-helper/write-test</code>):</div>'
                f'<pre class="diag-output">{_html.escape(info["write_output"])}</pre>'
            )
        return HTMLResponse(
            f'<div class="diag-result {status_cls}">'
            f'<div class="diag-status">{status_text}</div>'
            f'<dl class="diag-table">{table}</dl>'
            f'<div class="diag-output-label">git ls-remote output:</div>'
            f'<pre class="diag-output">{_html.escape(info["output"])}</pre>'
            f"{write_details}"
            f"</div>"
        )
    except Exception as e:
        import html as _html

        return HTMLResponse(f'<div class="diag-result diag-error"><b>Error:</b> {_html.escape(str(e))}</div>')


@app.post("/settings/repos/{repo_id}/sync", response_class=HTMLResponse)
async def sync_repo(repo_id: str):
    import html as _html

    storage = get_storage()
    if not storage:
        return HTMLResponse('<div class="diag-result diag-error">No storage available.</div>')
    gs = storage._stores.get(repo_id)
    if not gs:
        return HTMLResponse('<div class="diag-result diag-error">Repo not found.</div>')
    try:
        gs._last_pull = 0.0
        await asyncio.to_thread(gs._pull)
        return HTMLResponse('<div class="diag-result diag-ok">✓ Synced with remote.</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="diag-result diag-error"><b>Sync failed:</b> {_html.escape(str(e))}</div>')


@app.get("/api/repos/{repo_id}/health", response_class=HTMLResponse)
async def repo_health(repo_id: str):
    import html as _html
    from datetime import datetime as _dt

    storage = get_storage()
    if not storage:
        return HTMLResponse('<div class="diag-result diag-error">No storage.</div>')
    h = await asyncio.to_thread(storage.repo_health, repo_id)
    if not h.get("ok"):
        err = _html.escape(h.get("error", "Unknown error"))
        return HTMLResponse(f'<div class="diag-result diag-error">Health check failed: {err}</div>')

    last_ts = h.get("last_commit_ts")
    if last_ts:
        last_str = _dt.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
        age_h = (_dt.now().timestamp() - last_ts) / 3600
        age_warn = age_h > 24
    else:
        last_str = "—"
        age_warn = False

    reachable = h.get("reachable", False)
    reach_cls = "diag-ok" if reachable else "diag-error"
    reach_txt = "✓ reachable" if reachable else "✗ unreachable"

    last_cls = "color:var(--danger)" if age_warn else ""
    return HTMLResponse(
        f'<div class="diag-result health-result">'
        f'<span class="{reach_cls}">{reach_txt}</span> &nbsp;·&nbsp; '
        f'Last commit: <span style="{last_cls}">{_html.escape(last_str)}</span> &nbsp;·&nbsp; '
        f"Files: {h.get('file_count', 0)} &nbsp;·&nbsp; "
        f"Commits (7d): {h.get('commits_7d', 0)}"
        f"</div>"
    )


@app.post("/settings/templates")
async def add_template(name: str = Form(...), content: str = Form(...)):
    settings_store.upsert_template({"name": name.strip(), "content": content})
    return RedirectResponse("/settings?saved=1#templates", status_code=303)


@app.post("/settings/templates/{template_id}")
async def update_template(template_id: str, name: str = Form(...), content: str = Form(...)):
    settings_store.upsert_template({"id": template_id, "name": name.strip(), "content": content})
    return RedirectResponse("/settings?saved=1#templates", status_code=303)


@app.post("/settings/templates/{template_id}/delete")
async def delete_template(template_id: str):
    settings_store.delete_template(template_id)
    return RedirectResponse("/settings#templates", status_code=303)


@app.get("/api/templates", response_class=JSONResponse)
async def list_templates():
    return settings_store.get_templates()


@app.post("/settings/generate-keypair")
async def generate_keypair():
    private_key, public_key = settings_store.generate_ssh_keypair()
    return {"private_key": private_key, "public_key": public_key}


@app.post("/settings/tls")
async def save_tls_settings(
    tls_mode: str = Form("http"),
    tls_san: str = Form("localhost, 127.0.0.1"),
    tls_custom_crt: str = Form(""),
    tls_custom_key: str = Form(""),
):
    cfg = settings_store.load()
    cfg["tls_mode"] = tls_mode
    cfg["tls_san"] = tls_san.strip()
    if tls_custom_crt.strip():
        cfg["tls_custom_crt"] = tls_custom_crt.strip()
    if tls_custom_key.strip():
        cfg["tls_custom_key"] = tls_custom_key.strip()
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/notes")
async def save_notes_settings(
    notes_scroll_position: str = Form("end"),
    notes_line_numbers: str = Form(""),
):
    cfg = settings_store.load()
    cfg["notes_scroll_position"] = "end" if notes_scroll_position == "end" else "start"
    cfg["notes_line_numbers"] = notes_line_numbers == "on"
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1#notes", status_code=303)


@app.post("/settings/vacation")
async def save_vacation_settings(
    vacation_state: str = Form("BY"),
    vacation_days_per_year: int = Form(30),
    vacation_carryover: float = Form(0.0),
    holiday_language: str = Form("de"),
    calendar_show_weekends: str = Form(""),
):
    cfg = settings_store.load()
    cfg["vacation_state"] = vacation_state.strip()
    cfg["vacation_days_per_year"] = max(1, vacation_days_per_year)
    cfg["vacation_carryover"] = vacation_carryover
    cfg["holiday_language"] = holiday_language if holiday_language in ("de", "en_US") else "de"
    cfg["calendar_show_weekends"] = calendar_show_weekends == "on"
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1#vacation", status_code=303)


@app.post("/settings/vacation-mail")
async def save_vacation_mail_settings(
    vacation_mail_to: str = Form(""),
    vacation_mail_cc: str = Form(""),
    vacation_mail_subject: str = Form(""),
    vacation_mail_body: str = Form(""),
):
    cfg = settings_store.load()
    cfg["vacation_mail_to"] = vacation_mail_to.strip()
    cfg["vacation_mail_cc"] = vacation_mail_cc.strip()
    cfg["vacation_mail_subject"] = vacation_mail_subject.strip()
    cfg["vacation_mail_body"] = vacation_mail_body
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1#vacation", status_code=303)


@app.post("/settings/sprints")
async def save_sprint_settings(
    request: Request,
    sprint_anchor_date: str = Form(""),
    sprint_name_prefix: str = Form("PFM Sprint"),
    sprint_duration_weeks: int = Form(3),
):
    form = await request.form()
    blocked_types = list(form.getlist("sprint_blocked_appointment_types"))
    cfg = settings_store.load()
    cfg["sprint_anchor_date"] = sprint_anchor_date.strip()
    cfg["sprint_name_prefix"] = sprint_name_prefix.strip() or "PFM Sprint"
    cfg["sprint_duration_weeks"] = max(1, sprint_duration_weeks)
    cfg["sprint_blocked_appointment_types"] = blocked_types
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1#sprints", status_code=303)


@app.post("/settings/link-sections/new")
async def add_link_section(
    name: str = Form(...),
    floccus_enabled: str = Form(""),
    floccus_username: str = Form(""),
    floccus_password: str = Form(""),
):
    section = {
        "name": name.strip(),
        "floccus_enabled": bool(floccus_enabled),
        "floccus_username": floccus_username.strip(),
        "floccus_password": floccus_password.strip() if floccus_password.strip() else "",
    }
    settings_store.upsert_link_section(section)
    return RedirectResponse("/settings?saved=1#link-sections", status_code=303)


@app.post("/settings/link-sections/{section_id}/edit")
async def edit_link_section(
    section_id: str,
    name: str = Form(...),
    floccus_enabled: str = Form(""),
    floccus_username: str = Form(""),
    floccus_password: str = Form(""),
):
    existing = next((s for s in settings_store.get_link_sections() if s["id"] == section_id), None)
    if not existing:
        raise HTTPException(status_code=404)
    existing["name"] = name.strip()
    existing["floccus_enabled"] = bool(floccus_enabled)
    existing["floccus_username"] = floccus_username.strip()
    if floccus_password.strip():
        existing["floccus_password"] = floccus_password.strip()
    settings_store.upsert_link_section(existing)
    return RedirectResponse("/settings?saved=1#link-sections", status_code=303)


@app.post("/settings/link-sections/{section_id}/delete")
async def delete_link_section(section_id: str):
    settings_store.delete_link_section(section_id)
    return RedirectResponse("/settings?saved=1#link-sections", status_code=303)


@app.post("/settings/ics-profiles")
async def add_ics_profile(
    name: str = Form(...),
    recipients_required: str = Form(""),
    recipients_optional: str = Form(""),
    no_online_meeting: str = Form(""),
    show_as: str = Form("oof"),
    all_day: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    category: str = Form(""),
    subject: str = Form("Vacation {start_date}–{end_date}"),
    body: str = Form("{note}"),
):
    profile = {
        "name": name.strip(),
        "recipients_required": [r.strip() for r in recipients_required.split(",") if r.strip()],
        "recipients_optional": [r.strip() for r in recipients_optional.split(",") if r.strip()],
        "no_online_meeting": no_online_meeting == "on",
        "show_as": show_as,
        "all_day": all_day == "on",
        "start_time": start_time.strip() or None,
        "end_time": end_time.strip() or None,
        "category": category.strip() or None,
        "subject": subject,
        "body": body,
    }
    settings_store.upsert_ics_profile(profile)
    return RedirectResponse("/settings?saved=1#ics-profiles", status_code=303)


@app.post("/settings/ics-profiles/{profile_id}/edit")
async def update_ics_profile(
    profile_id: str,
    name: str = Form(...),
    recipients_required: str = Form(""),
    recipients_optional: str = Form(""),
    no_online_meeting: str = Form(""),
    show_as: str = Form("oof"),
    all_day: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    category: str = Form(""),
    subject: str = Form("Vacation {start_date}–{end_date}"),
    body: str = Form("{note}"),
):
    profile = {
        "id": profile_id,
        "name": name.strip(),
        "recipients_required": [r.strip() for r in recipients_required.split(",") if r.strip()],
        "recipients_optional": [r.strip() for r in recipients_optional.split(",") if r.strip()],
        "no_online_meeting": no_online_meeting == "on",
        "show_as": show_as,
        "all_day": all_day == "on",
        "start_time": start_time.strip() or None,
        "end_time": end_time.strip() or None,
        "category": category.strip() or None,
        "subject": subject,
        "body": body,
    }
    settings_store.upsert_ics_profile(profile)
    return RedirectResponse("/settings?saved=1#ics-profiles", status_code=303)


@app.post("/settings/ics-profiles/{profile_id}/delete")
async def delete_ics_profile(profile_id: str):
    settings_store.delete_ics_profile(profile_id)
    return RedirectResponse("/settings#ics-profiles", status_code=303)


@app.post("/settings/appointment-ics-profiles")
async def add_appointment_ics_profile(
    name: str = Form(...),
    recipients_required: str = Form(""),
    recipients_optional: str = Form(""),
    no_online_meeting: str = Form(""),
    show_as: str = Form("busy"),
    all_day: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    category: str = Form(""),
    subject: str = Form("{title} {start_date}–{end_date}"),
    body: str = Form("{note}"),
):
    profile = {
        "name": name.strip(),
        "recipients_required": [r.strip() for r in recipients_required.split(",") if r.strip()],
        "recipients_optional": [r.strip() for r in recipients_optional.split(",") if r.strip()],
        "no_online_meeting": no_online_meeting == "on",
        "show_as": show_as,
        "all_day": all_day == "on",
        "start_time": start_time.strip() or None,
        "end_time": end_time.strip() or None,
        "category": category.strip() or None,
        "subject": subject,
        "body": body,
    }
    settings_store.upsert_appointment_ics_profile(profile)
    return RedirectResponse("/settings?saved=1#appointment-ics-profiles", status_code=303)


@app.post("/settings/appointment-ics-profiles/{profile_id}/edit")
async def update_appointment_ics_profile(
    profile_id: str,
    name: str = Form(...),
    recipients_required: str = Form(""),
    recipients_optional: str = Form(""),
    no_online_meeting: str = Form(""),
    show_as: str = Form("busy"),
    all_day: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    category: str = Form(""),
    subject: str = Form("{title} {start_date}–{end_date}"),
    body: str = Form("{note}"),
):
    profile = {
        "id": profile_id,
        "name": name.strip(),
        "recipients_required": [r.strip() for r in recipients_required.split(",") if r.strip()],
        "recipients_optional": [r.strip() for r in recipients_optional.split(",") if r.strip()],
        "no_online_meeting": no_online_meeting == "on",
        "show_as": show_as,
        "all_day": all_day == "on",
        "start_time": start_time.strip() or None,
        "end_time": end_time.strip() or None,
        "category": category.strip() or None,
        "subject": subject,
        "body": body,
    }
    settings_store.upsert_appointment_ics_profile(profile)
    return RedirectResponse("/settings?saved=1#appointment-ics-profiles", status_code=303)


@app.post("/settings/appointment-ics-profiles/{profile_id}/delete")
async def delete_appointment_ics_profile(profile_id: str):
    settings_store.delete_appointment_ics_profile(profile_id)
    return RedirectResponse("/settings#appointment-ics-profiles", status_code=303)


@app.post("/settings/holiday-ics-profiles")
async def add_holiday_ics_profile(
    name: str = Form(...),
    recipients_required: str = Form(""),
    recipients_optional: str = Form(""),
    no_online_meeting: str = Form(""),
    all_day: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    show_as: str = Form("free"),
    category: str = Form(""),
    subject: str = Form("{name}"),
    body: str = Form(""),
):
    profile = {
        "name": name.strip(),
        "recipients_required": [r.strip() for r in recipients_required.split(",") if r.strip()],
        "recipients_optional": [r.strip() for r in recipients_optional.split(",") if r.strip()],
        "no_online_meeting": no_online_meeting == "on",
        "all_day": all_day == "on",
        "start_time": start_time.strip() or None,
        "end_time": end_time.strip() or None,
        "show_as": show_as,
        "category": category.strip() or None,
        "subject": subject,
        "body": body,
    }
    settings_store.upsert_holiday_ics_profile(profile)
    return RedirectResponse("/settings?saved=1#holiday-ics-profiles", status_code=303)


@app.post("/settings/holiday-ics-profiles/{profile_id}/edit")
async def update_holiday_ics_profile(
    profile_id: str,
    name: str = Form(...),
    recipients_required: str = Form(""),
    recipients_optional: str = Form(""),
    no_online_meeting: str = Form(""),
    all_day: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    show_as: str = Form("free"),
    category: str = Form(""),
    subject: str = Form("{name}"),
    body: str = Form(""),
):
    profile = {
        "id": profile_id,
        "name": name.strip(),
        "recipients_required": [r.strip() for r in recipients_required.split(",") if r.strip()],
        "recipients_optional": [r.strip() for r in recipients_optional.split(",") if r.strip()],
        "no_online_meeting": no_online_meeting == "on",
        "all_day": all_day == "on",
        "start_time": start_time.strip() or None,
        "end_time": end_time.strip() or None,
        "show_as": show_as,
        "category": category.strip() or None,
        "subject": subject,
        "body": body,
    }
    settings_store.upsert_holiday_ics_profile(profile)
    return RedirectResponse("/settings?saved=1#holiday-ics-profiles", status_code=303)


@app.post("/settings/holiday-ics-profiles/{profile_id}/delete")
async def delete_holiday_ics_profile(profile_id: str):
    settings_store.delete_holiday_ics_profile(profile_id)
    return RedirectResponse("/settings#holiday-ics-profiles", status_code=303)


@app.post("/settings/module-repos")
async def save_module_repos(request: Request):
    form = await request.form()
    module_repos: dict = {}
    all_modules = (
        "knowledge",
        "tasks",
        "vacations",
        "mail_templates",
        "ticket_templates",
        "notes",
        "links",
        "runbooks",
        "appointments",
        "snippets",
        "motd",
        "potd",
        "memes",
        "rss",
        "eol",
    )
    for module in all_modules:
        repos = form.getlist(f"{module}_repos")
        primary = form.get(f"{module}_primary", "")
        module_repos[module] = {"repos": repos, "primary": primary}
    settings_store.set_module_repos(module_repos)
    return RedirectResponse("/settings?saved=1#module-repos", status_code=303)


@app.post("/settings/modules")
async def save_modules_settings(
    knowledge: str = Form("off"),
    tasks: str = Form("off"),
    vacations: str = Form("off"),
    mail_templates: str = Form("off"),
    ticket_templates: str = Form("off"),
    notes: str = Form("off"),
    links: str = Form("off"),
    runbooks: str = Form("off"),
    appointments: str = Form("off"),
    snippets: str = Form("off"),
    motd: str = Form("off"),
    potd: str = Form("off"),
    memes: str = Form("off"),
    rss: str = Form("off"),
    eol: str = Form("off"),
):
    settings_store.set_modules_enabled(
        {
            "knowledge": knowledge == "on",
            "tasks": tasks == "on",
            "vacations": vacations == "on",
            "mail_templates": mail_templates == "on",
            "ticket_templates": ticket_templates == "on",
            "notes": notes == "on",
            "links": links == "on",
            "runbooks": runbooks == "on",
            "appointments": appointments == "on",
            "snippets": snippets == "on",
            "motd": motd == "on",
            "potd": potd == "on",
            "memes": memes == "on",
            "rss": rss == "on",
            "eol": eol == "on",
        }
    )
    return RedirectResponse("/settings?saved=1#modules", status_code=303)


@app.post("/settings/metrics")
async def save_metrics_settings(metrics_enabled: str = Form("off")):
    cfg = settings_store.load()
    cfg["metrics_enabled"] = metrics_enabled == "on"
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/ticket-templates")
async def save_ticket_template_settings(ticket_template_desc_maxlength: int = Form(0)):
    cfg = settings_store.load()
    cfg["ticket_template_desc_maxlength"] = max(0, ticket_template_desc_maxlength)
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1#ticket-templates", status_code=303)


@app.post("/settings/cache")
async def save_cache_settings(cache_max_file_mb: int = Form(10)):
    cfg = settings_store.load()
    cfg["cache_max_file_mb"] = max(1, cache_max_file_mb)
    settings_store.save(cfg)
    cache.configure_limits(cfg["cache_max_file_mb"])
    return RedirectResponse("/settings?saved=1#system", status_code=303)


@app.post("/settings/tls/generate", response_class=HTMLResponse)
async def generate_tls_cert(request: Request, tls_san: str = Form("localhost, 127.0.0.1")):
    cfg = settings_store.load()
    cfg["tls_san"] = tls_san.strip()
    settings_store.save(cfg)
    try:
        info = tls_mod.generate_ca_and_server_cert(tls_san)
    except Exception as e:
        return HTMLResponse(f'<span class="perm-error">Error: {e}</span>')
    ca_pem = tls_mod.get_ca_cert_pem()
    return templates.TemplateResponse(
        request,
        "partials/tls_ca_info.html",
        {
            "ca_pem": ca_pem,
            "expiry": info["expiry"],
            "cn": info["cn"],
            "sans": info["sans"],
        },
    )


@app.post("/settings/export")
async def export_settings(request: Request):
    import json as _json

    from core.crypto import encrypt_export
    from fastapi.responses import Response

    form = await request.form()
    password = (form.get("password") or "").strip()
    if not password:
        return RedirectResponse("/settings?error=Export+requires+a+password", status_code=303)
    cfg = settings_store.load()
    json_str = _json.dumps(cfg, indent=2, ensure_ascii=False)
    encrypted = encrypt_export(json_str, password)
    return Response(
        content=encrypted,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=daily-helper-settings.dhbak"},
    )


@app.post("/settings/import", response_class=RedirectResponse)
async def import_settings(request: Request):
    import json as _json

    from core.crypto import decrypt_export, is_encrypted

    form = await request.form()
    file = form.get("file")
    password = (form.get("import_password") or "").strip()
    if not file or not hasattr(file, "read"):
        return RedirectResponse("/settings?error=No+file+uploaded", status_code=303)
    try:
        raw = await file.read()
        if is_encrypted(raw):
            if not password:
                return RedirectResponse(
                    "/settings?error=This+backup+is+encrypted+%E2%80%94+please+enter+the+password",
                    status_code=303,
                )
            json_str = decrypt_export(raw, password)
            data = _json.loads(json_str)
        else:
            data = _json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid format")
        # Only keys the app actually knows about may be persisted — an import
        # is otherwise a way to smuggle in arbitrary top-level state (CORE-04).
        unknown_keys = set(data) - set(settings_store.DEFAULTS)
        if unknown_keys:
            logger.warning("Settings import: dropping unknown key(s): %s", sorted(unknown_keys))
            data = {k: v for k, v in data.items() if k in settings_store.DEFAULTS}
        settings_store.save(data)
        reset_storage()
    except Exception:
        logger.exception("Settings import failed")
        return RedirectResponse("/settings?error=Import+failed+%E2%80%94+see+server+log", status_code=303)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/backup-to-repo")
async def backup_to_repo(request: Request):
    import html as _html
    import json as _json

    from core.crypto import encrypt_export

    form = await request.form()
    password = (form.get("backup_password") or "").strip()
    repo_id = (form.get("backup_repo_id") or "").strip()
    backup_path = (form.get("backup_path") or "settings-backup/settings.dhbak").strip()
    if not password:
        return HTMLResponse('<div class="flash-error">Password required for backup.</div>', status_code=400)
    if not repo_id:
        return HTMLResponse('<div class="flash-error">Please select a repository.</div>', status_code=400)
    storage = get_storage()
    if not storage:
        return HTMLResponse('<div class="flash-error">No storage configured.</div>', status_code=400)
    store = storage._stores.get(repo_id)
    if not store:
        return HTMLResponse('<div class="flash-error">Repository not found.</div>', status_code=400)
    try:
        GitStorage._reject_traversal(backup_path, "Backup path")
    except GitStorageError as e:
        return HTMLResponse(f'<div class="flash-error">{_html.escape(str(e))}</div>', status_code=400)
    try:
        cfg = settings_store.load()
        json_str = _json.dumps(cfg, indent=2, ensure_ascii=False)
        encrypted = encrypt_export(json_str, password)
        from pathlib import Path

        dest = Path(store.local_path) / backup_path

        def _write() -> None:
            with store.write_lock():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(encrypted)
                store._commit_and_push("backup: update encrypted settings backup")

        await asyncio.to_thread(_write)
        return HTMLResponse('<div class="flash-success">Settings backed up successfully.</div>')
    except Exception as e:
        logger.warning("Settings backup failed: %s", e)
        return HTMLResponse(f'<div class="flash-error">Backup failed: {_html.escape(str(e))}</div>', status_code=500)


@app.get("/settings/tls/ca.crt")
async def download_ca_cert():
    ca_path = tls_mod.CA_CERT_PATH
    if not ca_path.exists():
        raise HTTPException(status_code=404, detail="No CA certificate generated yet")
    return FileResponse(str(ca_path), media_type="application/x-pem-file", filename="daily-helper-ca.crt")


# ───────────────────────────────────────── Health & System ──


@app.get("/health")
async def health():
    result: dict = {"status": "ok", "version": APP_VERSION, "cache": cache.is_connected()}
    stats = cache.get_stats()
    if stats:
        result["cache_keys"] = stats["key_count"]
        result["cache_hit_rate_pct"] = stats["hit_rate"]
    return result


@app.get("/api/repos-status-banner", response_class=HTMLResponse)
async def repos_status_banner():
    from core.storage import REPO_RETRY_INTERVAL_SECONDS

    storage = get_storage()
    pending: list[str] = []
    degraded: list[str] = []
    if storage:
        cfg = settings_store.load()
        repo_map = {r["id"]: r.get("name", r["id"]) for r in cfg.get("repos", [])}
        for rid, store in storage._stores.items():
            if store.has_pending_push:
                pending.append(repo_map.get(rid, rid))
        degraded = [d["name"] for d in storage.degraded_repos()]
    if not pending and not degraded:
        return HTMLResponse("")
    lang = get_current_lang()
    parts = []
    if degraded:
        msg = _i18n_t(
            "repo.degraded_banner",
            lang,
            repos=", ".join(degraded),
            interval=REPO_RETRY_INTERVAL_SECONDS,
        )
        parts.append(f'<i data-lucide="wifi-off" class="icon-xs"></i> {msg}')
    if pending:
        msg = _i18n_t("offline.banner", lang, repos=", ".join(pending))
        parts.append(f'<i data-lucide="wifi-off" class="icon-xs"></i> {msg}')
    body = "<br>".join(parts)
    return HTMLResponse(f'<div class="offline-banner" hx-swap-oob="true">{body}</div>')


@app.get("/api/redis-status", response_class=HTMLResponse)
async def redis_status():
    _REFRESH = 'hx-get="/api/redis-status" hx-trigger="every 30s" hx-swap="outerHTML"'
    if cache.is_connected():
        stats = cache.get_stats()
        if stats:
            parts = [f"{stats['key_count']} keys"]
            if stats["hit_rate"] is not None:
                parts.append(f"{stats['hit_rate']}% hits")
            label = " · ".join(parts)
            title = f"Redis: connected · {label}"
            return HTMLResponse(
                f'<span class="cache-icon cache-ok cache-stats" title="{title}" {_REFRESH}>'
                f'⚡ <span class="cache-stats-label">{label}</span></span>'
            )
        return HTMLResponse(f'<span class="cache-icon cache-ok" title="Redis: connected" {_REFRESH}>⚡</span>')
    return HTMLResponse(f'<span class="cache-icon cache-off" title="Redis: unavailable" {_REFRESH}>⚡</span>')


@app.post("/api/restart")
async def restart_app():
    async def _shutdown():
        await asyncio.sleep(0.3)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_shutdown())
    return JSONResponse({"status": "restarting"})


@app.post("/api/cache/flush", response_class=HTMLResponse)
async def flush_cache():
    cache.flush()
    return HTMLResponse('<span class="perm-ok">✓ Cache flushed</span>')


@app.post("/api/favorites/toggle", response_class=HTMLResponse)
async def toggle_favorite(
    module: str = Form(...),
    entry_id: str = Form(...),
    title: str = Form(...),
    url: str = Form(...),
):
    import html as _html
    import json as _json

    from core import favorites as _fav

    try:
        is_fav = await asyncio.to_thread(_fav.toggle_favorite, module, entry_id, title, url)
    except _fav.FavoritesUnreadable as exc:
        logger.error("Favorite not toggled, file left untouched: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    cls = "fav-btn fav-active" if is_fav else "fav-btn"
    title_attr = _html.escape(_t("action.remove_favorite" if is_fav else "action.add_favorite"))
    # Serialise first, then escape the whole JSON for the attribute: escaping the
    # values one by one left quotes that the browser decodes back into the JSON.
    vals = _html.escape(_json.dumps({"module": module, "entry_id": entry_id, "title": title, "url": url}))
    return HTMLResponse(
        f'<button type="button" class="btn btn-sm {cls}" title="{title_attr}"'
        f' hx-post="/api/favorites/toggle" hx-target="this" hx-swap="outerHTML"'
        f' hx-vals="{vals}"'
        f'><i data-lucide="star" class="icon-xs"></i></button>'
    )


@app.post("/api/sync", response_class=HTMLResponse)
async def force_sync():
    """Reset pull throttle for all repos + flush cache — picks up external changes immediately."""
    from core.state import get_storage

    storage = get_storage()
    if storage:
        for store in storage._stores.values():
            store._last_pull = 0.0
    cache.flush()
    return HTMLResponse('<span class="perm-ok">✓ Sync triggered — next request will pull from remote</span>')


# ───────────────────────────────────────── Metrics ──


def _build_metrics_data() -> dict:
    cfg = settings_store.load()
    storage = get_storage()
    repo_map = {r["id"]: r for r in cfg.get("repos", [])}
    repo_stats = []

    if storage:
        for rid, store in storage._stores.items():
            repo_cfg = repo_map.get(rid, {})
            try:
                categories = store.get_categories()
                entries = store.get_entries()
            except Exception:
                categories, entries = [], []
            repo_stats.append(
                {
                    "id": rid,
                    "name": repo_cfg.get("name", rid),
                    "entries": len(entries),
                    "categories": len(categories),
                    "writable": repo_cfg.get("permissions", {}).get("write", False),
                }
            )

    return {
        "version": APP_VERSION,
        "total": {
            "entries": sum(r["entries"] for r in repo_stats),
            "categories": sum(r["categories"] for r in repo_stats),
            "repos": len(repo_stats),
        },
        "repos": repo_stats,
        "cache": {"connected": cache.is_connected()},
    }


def _metrics_prometheus(data: dict) -> str:
    lines = []

    def metric(name, help_text, mtype, samples):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        for labels, value in samples:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{label_str}}} {value}")
        lines.append("")

    metric(
        "daily_helper_entries_total",
        "Total number of entries per repository",
        "gauge",
        [
            (
                {"repo": r["name"], "repo_id": r["id"], "writable": str(r["writable"]).lower()},
                r["entries"],
            )
            for r in data["repos"]
        ],
    )
    metric(
        "daily_helper_categories_total",
        "Total number of categories per repository",
        "gauge",
        [({"repo": r["name"], "repo_id": r["id"]}, r["categories"]) for r in data["repos"]],
    )
    metric(
        "daily_helper_repos_total",
        "Total number of configured repositories",
        "gauge",
        [({}, data["total"]["repos"])],
    )
    metric(
        "daily_helper_cache_connected",
        "Redis cache connection status (1=connected, 0=disconnected)",
        "gauge",
        [({}, 1 if data["cache"]["connected"] else 0)],
    )

    return "\n".join(lines)


@app.get("/metrics")
async def metrics(request: Request):
    cfg = settings_store.load()
    if not cfg.get("metrics_enabled"):
        raise HTTPException(status_code=404, detail="Metrics endpoint disabled")

    # Walks every repo (get_entries per store) — scrapers poll this regularly.
    data = await asyncio.to_thread(_build_metrics_data)

    accept = request.headers.get("accept", "")
    if "text/plain" in accept or "openmetrics" in accept:
        return HTMLResponse(
            content=_metrics_prometheus(data),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
    return data
