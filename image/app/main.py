"""Daily Helper — FastAPI application."""

import asyncio
import logging
import os
import signal
import socket

logger = logging.getLogger(__name__)

APP_VERSION = os.environ.get("APP_VERSION", "dev")

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from core import cache
from core import permission_checker
from core import settings_store
from core import tls as tls_mod
from core.state import get_storage, reset_storage
from core.storage import GitStorage, GitStorageError, MultiRepoStorage

from modules.knowledge import router as knowledge_router
from modules.tasks import router as tasks_router
from modules.vacations import router as vacations_router
from modules.operations import router as operations_router
from modules.mail_templates import router as mail_templates_router
from modules.ticket_templates import router as ticket_templates_router
from modules.notes import router as notes_router
from modules.links import router as links_router
from modules.runbooks import router as runbooks_router
from modules.appointments import router as appointments_router
from modules.calendar import router as calendar_router
from modules.snippets import router as snippets_router
from modules.links.floccus_api import (
    router as floccus_router,
    compat_router as floccus_compat_router,
)
from modules.history import router as history_router
from modules.memes import router as memes_router
from modules.motd import router as motd_router
from modules.potd import router as potd_router
from modules.rss import router as rss_router

app = FastAPI(title="Daily Helper")
app.mount("/static", StaticFiles(directory="static"), name="static")


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


from core.templates import templates

from datetime import datetime as _datetime


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

# Apply cache limits from persisted settings on startup
_startup_cfg = settings_store.load()
cache.configure_limits(_startup_cfg.get("cache_max_file_mb", 10))
del _startup_cfg


async def _offline_retry_loop():
    """Background task: every 60 s retry push for repos with queued offline changes."""
    while True:
        await asyncio.sleep(60)
        try:
            storage = get_storage()
            if storage:
                storage.retry_all_pending()
        except Exception as exc:
            logger.debug("Offline retry loop error: %s", exc)


@app.on_event("startup")
async def _start_background_tasks():
    asyncio.create_task(_offline_retry_loop())


# ───────────────────────────────────────── Home ──


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    cfg = settings_store.load()
    repos = cfg.get("repos", [])
    storage = get_storage()
    configured = bool(repos)

    entry_count = 0
    categories = []
    if storage:
        all_entries = storage.get_entries()
        entry_count = len(all_entries)
        cat_map: dict[str, int] = {}
        for e in all_entries:
            cat_map[e.get("category", "")] = cat_map.get(e.get("category", ""), 0) + 1
        categories = [{"name": k, "count": v} for k, v in sorted(cat_map.items())]

    modules = cfg.get("modules_enabled", {"knowledge": True, "tasks": True, "vacations": True})

    task_count = 0
    vacation_count = 0
    next_vacation = None
    days_until_next_vacation = None
    appointment_count = 0
    mail_template_count = 0
    ticket_template_count = 0
    note_count = 0
    link_count = 0
    runbook_count = 0
    snippet_count = 0
    if storage and storage._stores:
        from core.module_repos import get_module_stores

        def _count_yaml(store, prefix: str) -> int:
            return sum(1 for n in store.list_committed(prefix) if n.endswith(".yaml"))

        def _count_yaml_recursive(store, prefix: str) -> int:
            return sum(1 for n in store.list_committed_recursive(prefix) if n.endswith(".yaml"))

        def _count_all(module: str, prefix: str) -> int:
            return sum(_count_yaml(s, prefix) for s in get_module_stores(module, storage))

        def _count_all_recursive(module: str, prefix: str) -> int:
            return sum(_count_yaml_recursive(s, prefix) for s in get_module_stores(module, storage))

        if modules.get("tasks", True):
            task_count = _count_all("tasks", "tasks")
        if modules.get("vacations", True):
            vacation_count = _count_all("vacations", "vacations/entries")
            from modules.vacations.router import (
                _days_until_next_vacation,
                _list_all_entries as _list_vac_entries,
                _vacation_settings,
            )
            from datetime import date as _date

            _vac_state, _ = _vacation_settings()
            _all_vac = _list_vac_entries()
            _days_until, _next_vac = _days_until_next_vacation(_all_vac, _vac_state, _date.today())
            next_vacation = _next_vac
            days_until_next_vacation = _days_until
        if modules.get("mail_templates", True):
            mail_template_count = _count_all("mail_templates", "mail_templates")
        if modules.get("ticket_templates", True):
            ticket_template_count = _count_all("ticket_templates", "ticket_templates")
        if modules.get("notes", True):
            note_count = _count_all("notes", "notes")
        if modules.get("links", True):
            link_count = _count_all_recursive("links", "links")
        if modules.get("runbooks", True):
            runbook_count = _count_all("runbooks", "runbooks")
        if modules.get("appointments", True):
            appointment_count = _count_all("appointments", "appointments/entries")
        if modules.get("snippets", True):
            snippet_count = _count_all("snippets", "snippets")

    motd_count = 0
    potd_count = 0
    meme_count = 0
    rss_feed_count = 0
    if storage and storage._stores:
        from core.module_repos import get_module_stores

        if modules.get("motd", True):
            motd_count = sum(_count_yaml(s, "motd") for s in get_module_stores("motd", storage))
        if modules.get("potd", True):
            from modules.potd.router import _list_files_all

            potd_count = len(_list_files_all())
        if modules.get("memes", True):
            from modules.memes.router import _list_files_all as _list_memes_all

            meme_count = len(_list_memes_all())
        if modules.get("rss", True):
            from modules.rss.storage import RssStorage

            seen_rss: set[str] = set()
            for s in get_module_stores("rss", storage):
                for f in RssStorage(s).list_feeds():
                    seen_rss.add(f["id"])
            rss_feed_count = len(seen_rss)

    # Repo disk usage (local clone sizes in /tmp)
    import shutil as _shutil
    import subprocess as _subprocess
    from pathlib import Path as _Path

    repo_sizes: dict[str, int] = {}
    if storage:
        repos_root = _Path("/tmp/daily-helper/repos")
        for rid in storage._stores:
            repo_path = repos_root / rid
            if repo_path.is_dir():
                try:
                    r = _subprocess.run(
                        ["du", "-sb", str(repo_path)],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if r.returncode == 0:
                        repo_sizes[rid] = int(r.stdout.split()[0])
                except Exception:
                    pass

    # tmpfs usage
    tmpfs_info: dict | None = None
    try:
        _du = _shutil.disk_usage("/tmp")
        tmpfs_info = {"total": _du.total, "used": _du.used, "free": _du.free}
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "configured": configured,
            "repo_count": len(repos),
            "repos": repos,
            "entry_count": entry_count,
            "categories": categories,
            "task_count": task_count,
            "vacation_count": vacation_count,
            "appointment_count": appointment_count,
            "mail_template_count": mail_template_count,
            "ticket_template_count": ticket_template_count,
            "note_count": note_count,
            "link_count": link_count,
            "runbook_count": runbook_count,
            "snippet_count": snippet_count,
            "motd_count": motd_count,
            "potd_count": potd_count,
            "meme_count": meme_count,
            "rss_feed_count": rss_feed_count,
            "redis_connected": cache.is_connected(),
            "cache_stats": cache.get_stats(),
            "repo_sizes": repo_sizes,
            "tmpfs_info": tmpfs_info,
            "next_vacation": next_vacation,
            "days_until_next_vacation": days_until_next_vacation,
            "active_module": "home",
            "modules": modules,
        },
    )


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
    "calendar": "/calendar",
    "history": "/history",
    "operations": "/operations",
}


@app.get("/help/{module}", response_class=HTMLResponse)
async def module_help(request: Request, module: str):
    import pathlib
    from modules.knowledge.router import render_md

    if module not in _HELP_LABELS:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Help page not found")
    help_file = pathlib.Path(__file__).parent / "help" / f"{module}.md"
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


def _highlight(text: str, q: str, context: int = 60) -> str:
    """Return a short snippet of *text* with *q* highlighted using <mark> tags.

    Finds the first occurrence of q (case-insensitive), extracts ±context chars
    around it, escapes HTML, then wraps the match in <mark>.
    Returns empty string if q is not found or text is empty.
    """
    import html as _html

    if not text or not q:
        return ""
    ql = q.lower()
    tl = text.lower()
    idx = tl.find(ql)
    if idx == -1:
        return ""
    start = max(0, idx - context)
    end = min(len(text), idx + len(q) + context)
    snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    # Escape HTML then re-insert <mark> around the match (adjusted positions)
    pre_len = idx - start
    match_text = text[idx : idx + len(q)]
    snippet_raw = (
        ("…" if start > 0 else "")
        + text[start:idx]
        + "\x00"
        + match_text
        + "\x01"
        + text[idx + len(q) : end]
        + ("…" if end < len(text) else "")
    )
    escaped = _html.escape(snippet_raw)
    return escaped.replace("\x00", "<mark>").replace("\x01", "</mark>")


def _date_in_range(date_str: str, date_from: str, date_to: str) -> bool:
    """Return True if date_str falls within [date_from, date_to] (both optional, YYYY-MM-DD)."""
    if not date_str:
        return True
    if date_from and date_str < date_from:
        return False
    if date_to and date_str > date_to:
        return False
    return True


@app.get("/search", response_class=HTMLResponse)
async def global_search(request: Request, q: str = "", date_from: str = "", date_to: str = ""):
    import hashlib as _hashlib

    from core.module_repos import get_primary_store
    from core.storage import MultiRepoStorage

    cfg = settings_store.load()
    modules = cfg.get("modules_enabled", {})
    storage = get_storage()
    q_stripped = q.strip()
    df = date_from.strip()
    dt = date_to.strip()

    groups: list[dict] = []  # [{module, icon, label, url, items: [{title, subtitle, url}]}]
    _search_cache_key: str | None = None

    if q_stripped and storage:
        _search_cache_key = (
            "search:global:" + _hashlib.md5(f"{q_stripped}|{df}|{dt}".encode()).hexdigest()[:16]
        )
        _cached = cache.get(_search_cache_key)
        if _cached is not None:
            groups = _cached
            _search_cache_key = None  # cache hit — skip write at end

    if q_stripped and storage and _search_cache_key is not None:
        ql = q_stripped.lower()

        # Knowledge
        if modules.get("knowledge", True):
            try:
                results = storage.search(q_stripped)
                if results:
                    filtered = [r for r in results if _date_in_range(r.get("created", ""), df, dt)]
                    if filtered:
                        groups.append(
                            {
                                "module": "knowledge",
                                "icon": "book-open",
                                "label": "Knowledge",
                                "url": f"/knowledge/?q={q_stripped}",
                                "results": [
                                    {
                                        "title": r.get("title", r.get("slug", "")),
                                        "subtitle": r.get("category", ""),
                                        "snippet": _highlight(r.get("body", ""), q_stripped),
                                        "url": f"/knowledge/entries/{r['repo_id']}/{r.get('category', '')}/{r.get('slug', '')}",
                                    }
                                    for r in filtered[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Tasks
        if modules.get("tasks", True):
            try:
                from modules.tasks.storage import TaskStorage

                ts = get_primary_store("tasks", storage)
                if ts:
                    hits = [
                        t
                        for t in TaskStorage(ts).search_tasks(q_stripped)
                        if _date_in_range(t.get("created", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "tasks",
                                "icon": "check-square-2",
                                "label": "Tasks",
                                "url": f"/tasks?q={q_stripped}",
                                "results": [
                                    {
                                        "title": t["title"],
                                        "subtitle": ("Due " + t["due_date"])
                                        if t.get("due_date")
                                        else "",
                                        "snippet": _highlight(t.get("description", ""), q_stripped),
                                        "url": f"/tasks?q={q_stripped}",
                                    }
                                    for t in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Notes
        if modules.get("notes", True):
            try:
                from modules.notes.storage import NoteStorage

                ns = get_primary_store("notes", storage)
                if ns:
                    hits = [
                        n
                        for n in NoteStorage(ns).list_notes(query=q_stripped)
                        if _date_in_range(n.get("created", n.get("updated", "")), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "notes",
                                "icon": "file-text",
                                "label": "Notes",
                                "url": f"/notes?q={q_stripped}",
                                "results": [
                                    {
                                        "title": n["subject"],
                                        "subtitle": "",
                                        "snippet": _highlight(n.get("body", ""), q_stripped),
                                        "url": f"/notes/{n['id']}",
                                    }
                                    for n in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Links
        if modules.get("links", True):
            try:
                from modules.links.storage import LinkStorage

                ls = get_primary_store("links", storage)
                if ls:
                    hits = [
                        lk
                        for lk in LinkStorage(ls).list_links(query=q_stripped)
                        if _date_in_range(lk.get("created", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "links",
                                "icon": "link-2",
                                "label": "Links",
                                "url": f"/links?q={q_stripped}",
                                "results": [
                                    {
                                        "title": lk["title"],
                                        "subtitle": lk.get("url", ""),
                                        "url": lk.get("url", f"/links?q={q_stripped}"),
                                        "external": bool(lk.get("url")),
                                    }
                                    for lk in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Runbooks
        if modules.get("runbooks", True):
            try:
                from modules.runbooks.storage import RunbookStorage

                rs = get_primary_store("runbooks", storage)
                if rs:
                    hits = [
                        rb
                        for rb in RunbookStorage(rs).list_runbooks(query=q_stripped)
                        if _date_in_range(rb.get("created", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "runbooks",
                                "icon": "list-checks",
                                "label": "Runbooks",
                                "url": f"/runbooks?q={q_stripped}",
                                "results": [
                                    {
                                        "title": rb["title"],
                                        "subtitle": rb.get("description", ""),
                                        "snippet": _highlight(
                                            rb.get("description", "")
                                            + " "
                                            + " ".join(
                                                s.get("body", "") for s in rb.get("steps", [])
                                            ),
                                            q_stripped,
                                        ),
                                        "url": f"/runbooks/{rb['id']}",
                                    }
                                    for rb in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Snippets
        if modules.get("snippets", True):
            try:
                from modules.snippets.storage import SnippetStorage

                ss = get_primary_store("snippets", storage)
                if ss:
                    hits = [
                        sn
                        for sn in SnippetStorage(ss).list_snippets(query=q_stripped)
                        if _date_in_range(sn.get("created", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "snippets",
                                "icon": "code-2",
                                "label": "Snippets",
                                "url": f"/snippets?q={q_stripped}",
                                "results": [
                                    {
                                        "title": sn["title"],
                                        "subtitle": sn.get("description", ""),
                                        "snippet": _highlight(
                                            sn.get("description", "")
                                            + " "
                                            + " ".join(
                                                s.get("command", "") for s in sn.get("steps", [])
                                            ),
                                            q_stripped,
                                        ),
                                        "url": f"/snippets/{sn['id']}",
                                    }
                                    for sn in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Mail Templates
        if modules.get("mail_templates", True):
            try:
                from modules.mail_templates.storage import MailTemplateStorage

                ms = get_primary_store("mail_templates", storage)
                if ms:
                    all_t = MailTemplateStorage(ms).list_templates()
                    hits = [
                        t
                        for t in all_t
                        if (
                            ql in t.get("name", "").lower()
                            or ql in t.get("subject", "").lower()
                            or ql in t.get("body", "").lower()
                        )
                        and _date_in_range(t.get("created", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "mail_templates",
                                "icon": "mail",
                                "label": "Mail Templates",
                                "url": "/mail-templates",
                                "results": [
                                    {
                                        "title": t["name"],
                                        "subtitle": t.get("subject", ""),
                                        "url": "/mail-templates",
                                    }
                                    for t in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Ticket Templates
        if modules.get("ticket_templates", True):
            try:
                from modules.ticket_templates.storage import TicketTemplateStorage

                tt = get_primary_store("ticket_templates", storage)
                if tt:
                    all_t = TicketTemplateStorage(tt).list_templates()
                    hits = [
                        t
                        for t in all_t
                        if (
                            ql in t.get("name", "").lower()
                            or ql in t.get("description", "").lower()
                            or ql in t.get("body", "").lower()
                        )
                        and _date_in_range(t.get("created", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "ticket_templates",
                                "icon": "ticket",
                                "label": "Ticket Templates",
                                "url": "/ticket-templates",
                                "results": [
                                    {
                                        "title": t["name"],
                                        "subtitle": t.get("description", ""),
                                        "url": "/ticket-templates",
                                    }
                                    for t in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Vacations (search note field; date filter on start_date)
        if modules.get("vacations", True):
            try:
                from modules.vacations.storage import VacationStorage

                vs = get_primary_store("vacations", storage)
                if vs:
                    all_v = VacationStorage(vs).list_entries()
                    hits = [
                        v
                        for v in all_v
                        if (
                            ql in v.get("note", "").lower()
                            or ql in v.get("start_date", "").lower()
                            or ql in v.get("end_date", "").lower()
                        )
                        and _date_in_range(v.get("start_date", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "vacations",
                                "icon": "palmtree",
                                "label": "Vacations",
                                "url": "/vacations",
                                "results": [
                                    {
                                        "title": f"{v.get('start_date', '')} – {v.get('end_date', '')}",
                                        "subtitle": v.get("note", "") or v.get("status", ""),
                                        "url": "/vacations",
                                    }
                                    for v in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        # Appointments (date filter on start_date)
        if modules.get("appointments", True):
            try:
                from modules.appointments.storage import AppointmentStorage

                ap = get_primary_store("appointments", storage)
                if ap:
                    all_a = AppointmentStorage(ap).list_entries()
                    hits = [
                        a
                        for a in all_a
                        if (ql in a.get("title", "").lower() or ql in a.get("note", "").lower())
                        and _date_in_range(a.get("start_date", ""), df, dt)
                    ]
                    if hits:
                        groups.append(
                            {
                                "module": "appointments",
                                "icon": "calendar-days",
                                "label": "Appointments",
                                "url": "/appointments",
                                "results": [
                                    {
                                        "title": a["title"],
                                        "subtitle": a.get("start_date", ""),
                                        "url": "/appointments",
                                    }
                                    for a in hits[:10]
                                ],
                            }
                        )
            except Exception:
                pass

        if _search_cache_key is not None and groups:
            cache.set(_search_cache_key, groups, ttl=60)

    total = sum(len(g["results"]) for g in groups)
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "q": q_stripped,
            "date_from": df,
            "date_to": dt,
            "groups": groups,
            "total": total,
            "active_module": "search",
        },
    )


# ───────────────────────────────────────── API ──


@app.post("/api/preview", response_class=HTMLResponse)
async def preview_markdown(request: Request):
    import asyncio as _asyncio
    from modules.knowledge.router import render_md, _preview_rate, _PREVIEW_WINDOW, _PREVIEW_MAX

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
    return any(
        r["url"].strip() == url.strip() for r in cfg.get("repos", []) if r.get("id") != exclude_id
    )


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
        return RedirectResponse(
            f"/settings?error=A+repo+with+this+URL+already+exists", status_code=303
        )
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
        return RedirectResponse(
            f"/settings?error=A+repo+with+this+URL+already+exists", status_code=303
        )
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
            "basic_user": basic_user.strip()
            if basic_user.strip()
            else existing.get("basic_user", ""),
            "basic_password": basic_password.strip()
            if basic_password.strip()
            else existing.get("basic_password", ""),
            "gpg_key": gpg_key.strip() if gpg_key.strip() else existing.get("gpg_key", ""),
            "gpg_passphrase": gpg_passphrase.strip()
            if gpg_passphrase.strip()
            else existing.get("gpg_passphrase", ""),
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
        return RedirectResponse(
            f"/settings?error=A+repo+with+this+URL+already+exists", status_code=303
        )
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
    badge = (
        ""
        if new_state
        else '<span class="perm-badge perm-none" style="margin-left:0.5rem">disabled</span>'
    )
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
    probe._setup_credentials()
    return probe


@app.post("/settings/repos/{repo_id}/check", response_class=HTMLResponse)
async def check_repo_permissions(repo_id: str):
    try:
        repo = settings_store.get_repo(repo_id)
        if not repo:
            return HTMLResponse('<span class="perm-error">Repo not found</span>')

        url = repo.get("url", "")
        auth_mode = repo.get("auth_mode", "none")
        pat = repo.get("pat", "")
        platform = repo.get("platform", "gitea")

        if auth_mode == "pat" and pat:
            result = permission_checker.check_permissions(
                url, platform, pat, repo.get("ca_cert", "")
            )
        elif auth_mode == "ssh" and repo.get("ssh_key"):
            cfg = settings_store.load()
            repo_settings = dict(repo)
            repo_settings["_global"] = {
                "git_user_name": cfg.get("git_user_name", "Daily Helper"),
                "git_user_email": cfg.get("git_user_email", "daily@helper.local"),
            }
            probe = _make_probe(repo_id, url, repo_settings)
            info = probe.test_connection()
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
            info = probe.test_connection()
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
    except Exception as e:
        return HTMLResponse(f'<span class="perm-error">Error: {e}</span>')

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
        parts.append(f'<span class="perm-error">{result["error"]}</span>')

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
            perm = permission_checker.check_permissions(
                url, platform, repo["pat"], repo.get("ca_cert", "")
            )
            api_ok = perm.get("read", False)
            api_error = perm.get("error") or ""

        read_cell = "✓ yes" if info["read_ok"] else "✗ no"
        if info["write_tested"]:
            write_cell = "✓ yes" if info["write_ok"] else f"✗ no — {info['write_output']}"
        else:
            write_cell = "not tested (read failed)"
        api_cell = (
            ("✓ yes" if api_ok else "✗ no" + (f" — {api_error}" if api_error else ""))
            if api_ok is not None
            else "n/a"
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
        table = "".join(
            f'<dt>{k}</dt><dd class="monospace">{_html.escape(str(v))}</dd>' for k, v in rows
        )
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

        return HTMLResponse(
            f'<div class="diag-result diag-error"><b>Error:</b> {_html.escape(str(e))}</div>'
        )


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
        gs._pull()
        return HTMLResponse('<div class="diag-result diag-ok">✓ Synced with remote.</div>')
    except Exception as e:
        return HTMLResponse(
            f'<div class="diag-result diag-error"><b>Sync failed:</b> {_html.escape(str(e))}</div>'
        )


@app.get("/api/repos/{repo_id}/health", response_class=HTMLResponse)
async def repo_health(repo_id: str):
    import html as _html
    from datetime import datetime as _dt

    storage = get_storage()
    if not storage:
        return HTMLResponse('<div class="diag-result diag-error">No storage.</div>')
    h = storage.repo_health(repo_id)
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
        }
    )
    return RedirectResponse("/settings?saved=1#modules", status_code=303)


@app.post("/settings/metrics")
async def save_metrics_settings(metrics_enabled: str = Form("off")):
    cfg = settings_store.load()
    cfg["metrics_enabled"] = metrics_enabled == "on"
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/rss-home")
async def save_rss_home_settings(rss_home_limit: int = Form(3)):
    cfg = settings_store.load()
    cfg["rss_home_limit"] = max(1, rss_home_limit)
    settings_store.save(cfg)
    return RedirectResponse("/settings?saved=1#rss", status_code=303)


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
    from fastapi.responses import Response
    from core.crypto import encrypt_export

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
    from core.crypto import is_encrypted, decrypt_export

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
        settings_store.save(data)
        reset_storage()
    except Exception as e:
        return RedirectResponse(f"/settings?error=Import+failed:+{e}", status_code=303)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/backup-to-repo")
async def backup_to_repo(request: Request):
    import json as _json
    from fastapi.responses import Response
    from core.crypto import encrypt_export
    from core.module_repos import get_primary_store

    form = await request.form()
    password = (form.get("backup_password") or "").strip()
    repo_id = (form.get("backup_repo_id") or "").strip()
    backup_path = (form.get("backup_path") or "settings-backup/settings.dhbak").strip()
    if not password:
        return HTMLResponse(
            '<div class="flash-error">Password required for backup.</div>', status_code=400
        )
    if not repo_id:
        return HTMLResponse(
            '<div class="flash-error">Please select a repository.</div>', status_code=400
        )
    storage = get_storage()
    if not storage:
        return HTMLResponse(
            '<div class="flash-error">No storage configured.</div>', status_code=400
        )
    store = storage._stores.get(repo_id)
    if not store:
        return HTMLResponse('<div class="flash-error">Repository not found.</div>', status_code=400)
    try:
        cfg = settings_store.load()
        json_str = _json.dumps(cfg, indent=2, ensure_ascii=False)
        encrypted = encrypt_export(json_str, password)
        from pathlib import Path

        dest = Path(store.local_path) / backup_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(encrypted)
        store._commit_and_push("backup: update encrypted settings backup")
        return HTMLResponse('<div class="flash-success">Settings backed up successfully.</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="flash-error">Backup failed: {e}</div>', status_code=500)


@app.get("/settings/tls/ca.crt")
async def download_ca_cert():
    ca_path = tls_mod.CA_CERT_PATH
    if not ca_path.exists():
        raise HTTPException(status_code=404, detail="No CA certificate generated yet")
    return FileResponse(
        str(ca_path), media_type="application/x-pem-file", filename="daily-helper-ca.crt"
    )


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
    storage = get_storage()
    pending: list[str] = []
    if storage:
        cfg = settings_store.load()
        repo_map = {r["id"]: r.get("name", r["id"]) for r in cfg.get("repos", [])}
        for rid, store in storage._stores.items():
            if store.has_pending_push:
                pending.append(repo_map.get(rid, rid))
    if not pending:
        return HTMLResponse("")
    lang = get_current_lang()
    repos_str = ", ".join(pending)
    msg = _i18n_t("offline.banner", lang, repos=repos_str)
    return HTMLResponse(
        f'<div class="offline-banner" hx-swap-oob="true">'
        f'<i data-lucide="wifi-off" class="icon-xs"></i> {msg}</div>'
    )


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
        return HTMLResponse(
            f'<span class="cache-icon cache-ok" title="Redis: connected" {_REFRESH}>⚡</span>'
        )
    return HTMLResponse(
        f'<span class="cache-icon cache-off" title="Redis: unavailable" {_REFRESH}>⚡</span>'
    )


@app.post("/api/restart")
async def restart_app():
    async def _shutdown():
        await asyncio.sleep(0.3)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_shutdown())
    return JSONResponse({"status": "restarting"})


@app.get("/api/home/recent", response_class=HTMLResponse)
async def home_recent(request: Request):
    """HTMX partial: last 10 modified + last 10 added knowledge entries."""
    storage = get_storage()
    activity = storage.get_recent_activity(limit=10) if storage else {"added": [], "modified": []}
    cached = cache.get("home:recent")
    if cached is None and storage:
        activity = storage.get_recent_activity(limit=10)
        cache.set("home:recent", activity, ttl=120)
    else:
        activity = cached or {"added": [], "modified": []}
    return templates.TemplateResponse(
        request,
        "partials/home_recent.html",
        {
            "added": activity["added"],
            "modified": activity["modified"],
        },
    )


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
    from core import favorites as _fav

    is_fav = _fav.toggle_favorite(module, entry_id, title, url)
    cls = "fav-btn fav-active" if is_fav else "fav-btn"
    title_attr = "Remove from favorites" if is_fav else "Add to favorites"
    m = _html.escape(module)
    eid = _html.escape(entry_id)
    t = _html.escape(title)
    u = _html.escape(url)
    return HTMLResponse(
        f'<button type="button" class="btn btn-sm {cls}" title="{title_attr}"'
        f' hx-post="/api/favorites/toggle" hx-target="this" hx-swap="outerHTML"'
        f' hx-vals=\'{{"module":"{m}","entry_id":"{eid}","title":"{t}","url":"{u}"}}\''
        f'><i data-lucide="star" class="icon-xs"></i></button>'
    )


@app.get("/api/home/favorites", response_class=HTMLResponse)
async def home_favorites(request: Request):
    from core import favorites as _fav

    entries = _fav.list_favorites()
    return templates.TemplateResponse(
        request, "partials/home_favorites.html", {"favorites": entries}
    )


@app.get("/api/home/motd", response_class=HTMLResponse)
async def home_motd(request: Request):
    from core import settings_store as _ss
    from modules.motd.router import _get_offset, get_daily_all as motd_daily_all

    cfg = _ss.load()
    if not cfg.get("modules_enabled", {}).get("motd", True):
        return HTMLResponse("")
    motd = motd_daily_all(_get_offset())
    return templates.TemplateResponse(request, "partials/motd_widget.html", {"motd": motd})


@app.get("/api/home/potd", response_class=HTMLResponse)
async def home_potd(request: Request):
    from core import settings_store as _ss
    from modules.potd.router import get_daily_all as potd_daily_all, get_offset

    cfg = _ss.load()
    if not cfg.get("modules_enabled", {}).get("potd", True):
        return HTMLResponse("")
    potd = potd_daily_all(get_offset())
    return templates.TemplateResponse(request, "partials/potd_widget.html", {"potd": potd})


@app.get("/api/home/meme", response_class=HTMLResponse)
async def home_meme(request: Request):
    from core import settings_store as _ss
    from modules.memes.router import get_daily_all as meme_daily_all, get_offset as meme_offset

    cfg = _ss.load()
    if not cfg.get("modules_enabled", {}).get("memes", True):
        return HTMLResponse("")
    meme = meme_daily_all(meme_offset())
    return templates.TemplateResponse(request, "partials/meme_widget.html", {"meme": meme})


@app.get("/api/home/rss", response_class=HTMLResponse)
async def home_rss(request: Request):
    from core import settings_store as _ss
    from modules.rss.router import _get_feed_cached, _list_all_feeds

    cfg = _ss.load()
    if not cfg.get("modules_enabled", {}).get("rss", True):
        return HTMLResponse("")
    all_feeds = _list_all_feeds()
    enabled = [f for f in all_feeds if f.get("enabled", True)]
    feed = next((f for f in enabled if f.get("default")), None) or (enabled[0] if enabled else None)
    if not feed:
        return HTMLResponse("")
    data = _get_feed_cached(feed)
    limit = max(1, int(cfg.get("rss_home_limit", 3)))
    return templates.TemplateResponse(
        request,
        "partials/rss_widget.html",
        {"feed": feed, "items": data["items"][:limit]},
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
    return HTMLResponse(
        '<span class="perm-ok">✓ Sync triggered — next request will pull from remote</span>'
    )


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

    data = _build_metrics_data()

    accept = request.headers.get("accept", "")
    if "text/plain" in accept or "openmetrics" in accept:
        return HTMLResponse(
            content=_metrics_prometheus(data),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
    return data
