"""MCP server: Daily Helper data as tools for MCP clients such as Claude Code.

Served at /mcp as an exact route (Streamable HTTP). Off unless a token is set in
Settings → MCP server;
every request must then send it as ``Authorization: Bearer <token>``.

Tools call the same storage classes as the web routes. Storage calls run in a
worker thread: reads touch git, writes pull, commit and push under the repo lock.
"""

import asyncio
import contextlib
import hmac
import re
from datetime import date
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from core import settings_store
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage

server = MCPServer(
    "daily-helper",
    instructions=(
        "Daily Helper: personal knowledge base, tasks, notes, links, snippets, runbooks, "
        "mail and ticket templates, vacations, appointments and a calendar with public "
        "holidays and sprints. List tools accept a query and return ids; use the get "
        "tools for full content."
    ),
)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


def tool(annotations: ToolAnnotations):
    """Register a tool with structured output, so clients get the dict as data."""
    return server.tool(annotations=annotations, structured_output=True)


def _require(module: str) -> None:
    if not settings_store.is_module_enabled(module):
        raise ToolError(f"Module '{module}' is disabled in Settings")


def _storage():
    storage = get_storage()
    if storage is None:
        raise ToolError("No repository configured")
    return storage


def _stores(module: str) -> list:
    _require(module)
    return get_module_stores(module, _storage())


def _primary(module: str):
    _require(module)
    store = get_primary_store(module, _storage())
    if store is None:
        raise ToolError(f"No writable repository assigned to '{module}'")
    return store


def _find(items, item_id: str, what: str):
    for item in items:
        if item.get("id") == item_id:
            return item
    raise ToolError(f"{what} '{item_id}' not found")


def _matches(item: dict, query: str, *fields: str) -> bool:
    q = query.lower()
    return any(q in str(item.get(f, "")).lower() for f in fields)


# ── Search ──────────────────────────────────────────────────────────────────


@tool(READ)
async def search(query: str) -> dict[str, Any]:
    """Search all enabled modules at once. Returns titles grouped by module;
    use the module's list tool with the same query to get ids."""
    from core.global_search import run_global_search

    cfg = settings_store.load()
    groups = await asyncio.to_thread(
        run_global_search, query.strip(), "", "", cfg.get("modules_enabled", {}), _storage()
    )
    return {
        "groups": [
            {
                "module": g["module"],
                "results": [
                    {
                        "title": r.get("title", ""),
                        "subtitle": r.get("subtitle", ""),
                        "snippet": re.sub(r"<[^>]+>", "", r.get("snippet", "")),
                    }
                    for r in g["results"]
                ],
            }
            for g in groups
        ]
    }


# ── Tasks ───────────────────────────────────────────────────────────────────


def _all_tasks() -> list[dict]:
    from modules.tasks.storage import TaskStorage

    return [t for s in _stores("tasks") for t in TaskStorage(s).list_tasks()]


@tool(READ)
async def list_tasks(query: str = "", include_done: bool = False) -> dict[str, Any]:
    """List tasks (open only unless include_done), sorted by priority and due date."""
    tasks = await asyncio.to_thread(_all_tasks)
    tasks = [t for t in tasks if include_done or not t.get("done")]
    if query:
        tasks = [t for t in tasks if _matches(t, query, "title", "description")]
    return {"tasks": tasks}


@tool(READ)
async def get_task(task_id: str) -> dict[str, Any]:
    """Get one task by id."""
    return _find(await asyncio.to_thread(_all_tasks), task_id, "Task")


# ── Notes ───────────────────────────────────────────────────────────────────


def _note_storages() -> list:
    from modules.notes.storage import NoteStorage

    return [NoteStorage(s) for s in _stores("notes")]


@tool(READ)
async def list_notes(query: str = "") -> dict[str, Any]:
    """List notes (id, subject, dates) matching query in subject or body."""

    def run():
        return [n for ns in _note_storages() for n in ns.list_notes(query)]

    notes = await asyncio.to_thread(run)
    return {"notes": [{k: v for k, v in n.items() if k != "body"} for n in notes]}


@tool(READ)
async def get_note(note_id: str) -> dict[str, Any]:
    """Get one note with its full body (decrypted if it is stored encrypted)."""

    def run():
        for ns in _note_storages():
            note = ns.get_note(note_id)
            if note:
                return note
        raise ToolError(f"Note '{note_id}' not found")

    return await asyncio.to_thread(run)


# ── Knowledge ───────────────────────────────────────────────────────────────


@tool(READ)
async def list_knowledge(query: str = "", category: str = "") -> dict[str, Any]:
    """List knowledge entries (repo_id, category, slug, title). With a query, a
    full-text search; otherwise all entries, optionally of one category."""
    _require("knowledge")
    storage = _storage()

    def run():
        entries = storage.search(query, category) if query else storage.get_entries(category=category or None)
        return [
            {k: e.get(k, "") for k in ("repo_id", "category", "slug", "title", "created", "pinned")} for e in entries
        ]

    return {"entries": await asyncio.to_thread(run)}


@tool(READ)
async def get_knowledge(repo_id: str, category: str, slug: str) -> dict[str, Any]:
    """Get one knowledge entry with its Markdown content."""
    _require("knowledge")
    entry = await asyncio.to_thread(_storage().get_entry, repo_id, category, slug)
    if not entry:
        raise ToolError(f"Knowledge entry '{repo_id}/{category}/{slug}' not found")
    return entry


# ── Links, snippets, runbooks, templates ────────────────────────────────────


@tool(READ)
async def list_links(query: str = "", category: str = "") -> dict[str, Any]:
    """List links of all link sections, optionally filtered."""
    _require("links")
    from modules.links.router import _get_all_storages

    def run():
        # Read-only: the configured sections, without the router's helper that
        # creates a default section; all assigned repos, like the web list.
        sections = settings_store.get_link_sections() or [{"id": "default"}]
        return [
            dict(link, section=section["id"])
            for section in sections
            for ls in _get_all_storages(section["id"])
            for link in ls.list_links(query, category)
        ]

    return {"links": await asyncio.to_thread(run)}


def _yaml_list(module: str, storage_cls, method: str, query: str | None = "") -> list[dict]:
    """query=None for list methods that take no query argument."""
    items = []
    for s in _stores(module):
        st = storage_cls(s)
        items += getattr(st, method)(query) if query is not None else getattr(st, method)()
    return items


@tool(READ)
async def list_snippets(query: str = "") -> dict[str, Any]:
    """List command snippets (title, description, steps with commands)."""
    from modules.snippets.storage import SnippetStorage

    return {"snippets": await asyncio.to_thread(_yaml_list, "snippets", SnippetStorage, "list_snippets", query)}


@tool(READ)
async def list_runbooks(query: str = "") -> dict[str, Any]:
    """List runbooks (id, title, description); use get_runbook for the steps."""
    from modules.runbooks.storage import RunbookStorage

    runbooks = await asyncio.to_thread(_yaml_list, "runbooks", RunbookStorage, "list_runbooks", query)
    return {"runbooks": [{k: r.get(k, "") for k in ("id", "title", "description")} for r in runbooks]}


@tool(READ)
async def get_runbook(runbook_id: str) -> dict[str, Any]:
    """Get one runbook with all steps."""
    from modules.runbooks.storage import RunbookStorage

    runbooks = await asyncio.to_thread(_yaml_list, "runbooks", RunbookStorage, "list_runbooks", "")
    return _find(runbooks, runbook_id, "Runbook")


_TEMPLATE_MODULES = {"mail": "mail_templates", "ticket": "ticket_templates"}


def _template_storage_cls(kind: str):
    if kind == "mail":
        from modules.mail_templates.storage import MailTemplateStorage

        return MailTemplateStorage
    from modules.ticket_templates.storage import TicketTemplateStorage

    return TicketTemplateStorage


@tool(READ)
async def list_templates(kind: str, query: str = "") -> dict[str, Any]:
    """List mail or ticket templates; kind is "mail" or "ticket"."""
    if kind not in _TEMPLATE_MODULES:
        raise ToolError('kind must be "mail" or "ticket"')
    items = await asyncio.to_thread(
        _yaml_list, _TEMPLATE_MODULES[kind], _template_storage_cls(kind), "list_templates", None
    )
    if query:
        items = [t for t in items if _matches(t, query, "name", "title", "subject", "body")]
    return {"templates": items}


# ── Vacations, appointments, calendar ───────────────────────────────────────


def _vacation_entries(year: int | None) -> list[dict]:
    from modules.vacations.storage import VacationStorage

    seen, entries = set(), []
    for s in _stores("vacations"):
        for e in VacationStorage(s).list_entries(year):
            if e["id"] not in seen:
                seen.add(e["id"])
                entries.append(e)
    return entries


@tool(READ)
async def list_vacations(year: int = 0) -> dict[str, Any]:
    """List vacation entries of a year (default: current year) with their status."""
    return {"vacations": await asyncio.to_thread(_vacation_entries, year or date.today().year)}


@tool(READ)
async def vacation_account(year: int = 0) -> dict[str, Any]:
    """Vacation account of a year: total, used, planned and remaining days."""
    from modules.vacations.router import _vacation_settings
    from modules.vacations.storage import VacationStorage

    year = year or date.today().year
    state, total_days = _vacation_settings()

    def run():
        account = VacationStorage(_primary("vacations")).get_account(
            year, total_days, state, entries=_vacation_entries(year)
        )
        return {k: v for k, v in account.items() if k != "entries"}

    return await asyncio.to_thread(run)


@tool(READ)
async def list_appointments(year: int = 0) -> dict[str, Any]:
    """List appointments of a year (default: current year)."""
    from modules.appointments.storage import AppointmentStorage

    def run():
        return [
            e for s in _stores("appointments") for e in AppointmentStorage(s).list_entries(year or date.today().year)
        ]

    return {"appointments": await asyncio.to_thread(run)}


def _calendar_entries(year: int) -> tuple[list, list, list]:
    """Vacations, appointments and open tasks of a year for calendar and capacity.

    Unlike the calendar page's loader, a module that cannot be read raises: a
    silently empty vacation list would make every sprint look fully staffed.
    Switched-off modules contribute nothing, as on the calendar page.
    """
    from modules.appointments.storage import AppointmentStorage

    def load(module: str, fn):
        if not settings_store.is_module_enabled(module):
            return []
        try:
            return fn()
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Could not read {module}: {e}") from None

    vac = load("vacations", lambda: _vacation_entries(year))
    appt = load(
        "appointments", lambda: [e for s in _stores("appointments") for e in AppointmentStorage(s).list_entries(year)]
    )
    tasks = load("tasks", lambda: [t for t in _all_tasks() if not t.get("done")])
    return vac, appt, tasks


def _anchor(cfg: dict):
    from modules.calendar.router import _sprint_anchor

    anchor = _sprint_anchor(cfg)
    if anchor is None and cfg.get("sprint_anchor_date"):
        raise ToolError(f"Sprint anchor date in Settings is not a valid date: {cfg['sprint_anchor_date']!r}")
    return anchor


@tool(READ)
async def calendar_month(year: int = 0, month: int = 0) -> dict[str, Any]:
    """Days of a month that carry something: public holidays, vacation,
    appointments, task deadlines and sprint starts. Default: current month."""
    from modules.vacations.holidays_helper import get_calendar_data

    today = date.today()
    year, month = year or today.year, month or today.month
    if not 1 <= month <= 12:
        raise ToolError("month must be 1-12")
    cfg = settings_store.load()

    def run():
        vac, appt, tasks = _calendar_entries(year)
        cal = get_calendar_data(
            year,
            month,
            cfg.get("vacation_state", "BY"),
            vac,
            language=cfg.get("holiday_language", "de"),
            appointment_entries=appt,
            task_entries=tasks,
            sprint_anchor=_anchor(cfg),
            sprint_prefix=cfg.get("sprint_name_prefix", "PFM Sprint"),
            sprint_duration_weeks=int(cfg.get("sprint_duration_weeks", 3)),
        )
        days = []
        for week in cal["weeks"]:
            for d in week:
                if not d:
                    continue
                entry = {
                    "date": d["date"].isoformat(),
                    "holiday": d["holiday_name"] if d["is_holiday"] else "",
                    "vacation": "approved" if d["is_vacation"] else ("pending" if d["is_vacation_pending"] else ""),
                    "appointments": [a.get("title", "") for a in d["appointments"]],
                    "tasks_due": [t.get("title", "") for t in d["tasks"]],
                    "sprint_start": d["sprint_name"] or "",
                }
                if any(v for k, v in entry.items() if k != "date"):
                    days.append(entry)
        return days

    return {"year": year, "month": month, "days": await asyncio.to_thread(run)}


@tool(READ)
async def sprint_capacity(year: int = 0) -> dict[str, Any]:
    """Per-sprint capacity of a year: work days, holidays, vacation and blocked
    appointment days, remaining days. Needs a sprint anchor date in Settings."""
    from modules.calendar.sprint_helper import capacity_for_sprint, get_sprints_in_year

    year = year or date.today().year
    cfg = settings_store.load()
    anchor = _anchor(cfg)
    if not anchor:
        raise ToolError("No sprint anchor date set in Settings → Sprints")

    def run():
        vac, appt = [], []
        # Sprints can straddle the year boundary.
        for y in (year - 1, year, year + 1):
            v, a, _ = _calendar_entries(y)
            vac += v
            appt += a
        sprints = get_sprints_in_year(
            year, anchor, cfg.get("sprint_name_prefix", "PFM Sprint"), int(cfg.get("sprint_duration_weeks", 3))
        )
        blocked = cfg.get("sprint_blocked_appointment_types", [])
        state = cfg.get("vacation_state", "BY")
        return [capacity_for_sprint(sp, vac, appt, blocked, state) for sp in sprints]

    sprints = await asyncio.to_thread(run)
    return {"year": year, "sprints": [{k: str(v) if isinstance(v, date) else v for k, v in s.items()} for s in sprints]}


# ── Write tools ─────────────────────────────────────────────────────────────
# Each call is one git commit in the module's repo, like a save in the web UI.
# There is deliberately no delete tool.


def _iso_date(value: str, field: str, required: bool = True) -> str:
    value = value.strip()
    if not value and not required:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ToolError(f"{field} must be a date in YYYY-MM-DD format") from None


def _not_blank(value: str, field: str) -> str:
    if not value.strip():
        raise ToolError(f"{field} must not be empty")
    return value


def _found(result: dict | None, what: str, item_id: str) -> dict:
    """Storage updates return None when the item vanished in the meantime."""
    if result is None:
        raise ToolError(f"{what} '{item_id}' not found")
    return result


def _given(**fields) -> dict:
    """Only the fields the caller set, so an update keeps everything else."""
    return {k: v for k, v in fields.items() if v is not None}


async def _save_off_loop(run) -> dict[str, Any]:
    """Run a storage write in a worker thread. run() returns (git store, result).

    The result tells the client where it went and whether the push succeeded:
    after a network error the commit stays local and is retried, which the web
    UI shows as a banner and MCP must report as well.
    """
    from core.storage import GitStorageError

    try:
        git, result = await asyncio.to_thread(run)
    except GitStorageError as e:
        raise ToolError(f"Saving failed: {e}") from None
    return dict(result, repo_id=getattr(git, "repo_id", ""), pushed=not getattr(git, "has_pending_push", False))


def _without_body(note: dict) -> dict:
    return {k: v for k, v in note.items() if k != "body"}


Priority = Literal["high", "medium", "low"]
TaskRecurring = Literal["none", "daily", "weekly", "monthly"]


def _task_storage_for(task_id: str):
    from modules.tasks.storage import TaskStorage

    for s in _stores("tasks"):
        ts = TaskStorage(s)
        if ts.get_task(task_id):
            return ts
    raise ToolError(f"Task '{task_id}' not found")


@tool(WRITE)
async def create_task(
    title: str,
    description: str = "",
    due_date: str = "",
    priority: Priority = "medium",
    recurring: TaskRecurring = "none",
) -> dict[str, Any]:
    """Create a task. due_date is YYYY-MM-DD or empty."""
    from modules.tasks.storage import TaskStorage

    data = {
        "title": _not_blank(title, "title"),
        "description": description,
        "due_date": _iso_date(due_date, "due_date", required=False),
        "priority": priority,
        "recurring": recurring,
    }

    def run():
        git = _primary("tasks")
        return git, TaskStorage(git).create_task(data)

    return await _save_off_loop(run)


@tool(WRITE)
async def update_task(
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    due_date: str | None = None,
    priority: Priority | None = None,
    recurring: TaskRecurring | None = None,
) -> dict[str, Any]:
    """Change fields of a task; fields left out stay as they are. due_date "" clears it."""
    data = _given(
        title=_not_blank(title, "title") if title is not None else None,
        description=description,
        due_date=_iso_date(due_date, "due_date", required=False) if due_date is not None else None,
        priority=priority,
        recurring=recurring,
    )

    def run():
        ts = _task_storage_for(task_id)
        return ts._git, _found(ts.update_task(task_id, data), "Task", task_id)

    return await _save_off_loop(run)


@tool(WRITE)
async def complete_task(task_id: str) -> dict[str, Any]:
    """Mark a task done (a recurring task gets its next occurrence). A task that
    is already done stays done."""

    def run():
        ts = _task_storage_for(task_id)
        task = _found(ts.get_task(task_id), "Task", task_id)
        return ts._git, task if task.get("done") else _found(ts.toggle_done(task_id), "Task", task_id)

    return await _save_off_loop(run)


@tool(WRITE)
async def create_note(subject: str, body: str = "", encrypt: bool = False) -> dict[str, Any]:
    """Create a note. encrypt stores the body encrypted in the repository."""
    from modules.notes.storage import NoteStorage

    data = {"subject": _not_blank(subject, "subject"), "body": body, "encrypt": encrypt}

    def run():
        git = _primary("notes")
        return git, _without_body(NoteStorage(git).create_note(data))

    return await _save_off_loop(run)


@tool(WRITE)
async def update_note(note_id: str, subject: str | None = None, body: str | None = None) -> dict[str, Any]:
    """Change subject and/or body of a note. An encrypted note stays encrypted."""
    new_subject = _not_blank(subject, "subject") if subject is not None else None

    def run():
        for ns in _note_storages():
            note = ns.get_note(note_id)
            if note:
                encrypted = bool(note.get("encrypted"))
                # The storage drops encryption unless told to keep it, and it reads
                # a missing body raw (still encrypted) and would encrypt it again.
                # The web form always sends both; a tool must do the same.
                data = _given(subject=new_subject)
                data["body"] = body if body is not None else note.get("body", "")
                data["encrypt"] = encrypted
                return ns._git, _without_body(_found(ns.update_note(note_id, data), "Note", note_id))
        raise ToolError(f"Note '{note_id}' not found")

    return await _save_off_loop(run)


def _writable_knowledge_repo(repo_id: str) -> str:
    _require("knowledge")
    if not repo_id:
        store = get_primary_store("knowledge", _storage())
        if store is None:
            raise ToolError("No repository assigned to 'knowledge'")
        repo_id = store.repo_id
    repo = settings_store.get_repo(repo_id) or {}
    if not repo.get("permissions", {}).get("write", False):
        raise ToolError(f"Repository '{repo_id}' is read-only or unknown")
    return repo_id


def _knowledge_store(storage, repo_id: str):
    """The single-repo store behind the multi-repo storage, for the push state."""
    get_store = getattr(storage, "get_store", None)
    return get_store(repo_id) if get_store else None


@tool(WRITE)
async def create_knowledge(category: str, title: str, content: str, repo_id: str = "") -> dict[str, Any]:
    """Create a knowledge entry (Markdown). repo_id defaults to the knowledge
    module's primary repository; a new category is created as needed."""
    category = _not_blank(category, "category").strip()
    if "/" in category:
        raise ToolError('category must not contain "/"')
    _not_blank(title, "title")
    _not_blank(content, "content")
    repo_id = _writable_knowledge_repo(repo_id)
    storage = _storage()

    def run():
        entry = storage.save_entry(repo_id, category, title.strip(), content.strip())
        return _knowledge_store(storage, repo_id), {k: entry.get(k, "") for k in ("category", "slug", "title")}

    return dict(await _save_off_loop(run), repo_id=repo_id)


@tool(WRITE)
async def update_knowledge(
    repo_id: str, category: str, slug: str, title: str | None = None, content: str | None = None
) -> dict[str, Any]:
    """Change title and/or content of a knowledge entry."""
    repo_id = _writable_knowledge_repo(repo_id)
    storage = _storage()
    new_title = _not_blank(title, "title").strip() if title is not None else None
    new_content = _not_blank(content, "content").strip() if content is not None else None

    def run():
        entry = storage.get_entry(repo_id, category, slug)
        if not entry:
            raise ToolError(f"Knowledge entry '{repo_id}/{category}/{slug}' not found")
        result = storage.update_entry(
            repo_id, category, slug, new_title or entry["title"], new_content or entry["content"]
        )
        return _knowledge_store(storage, repo_id), {k: result.get(k, "") for k in ("category", "slug", "title")}

    return dict(await _save_off_loop(run), repo_id=repo_id)


@tool(WRITE)
async def save_link(
    title: str, url: str, category: str = "", description: str = "", section: str = ""
) -> dict[str, Any]:
    """Save a bookmark. section is a link section id (default: the first section)."""
    from fastapi import HTTPException
    from modules.links.router import _ensure_default_section, _get_storage, _resolve_section, _validate_url

    _require("links")
    _not_blank(title, "title")
    try:
        url = _validate_url(_not_blank(url, "url"))
    except HTTPException as e:
        raise ToolError(str(e.detail)) from None

    def run():
        sections = _ensure_default_section()
        # The web form only offers existing sections; _resolve_section falls back
        # to the first one, which would file the link somewhere else unasked.
        if section and section not in {s["id"] for s in sections}:
            raise ToolError(f"Link section '{section}' not found")
        active = _resolve_section(sections, section)
        ls = _get_storage(active["id"])
        if ls is None:
            raise ToolError("No repository assigned to 'links'")
        link = ls.create_link({"title": title, "url": url, "category": category, "description": description})
        return ls._git, dict(link, section=active["id"])

    return await _save_off_loop(run)


@tool(WRITE)
async def create_snippet(
    title: str, description: str = "", steps: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    """Create a command snippet. steps: [{"description": "...", "command": "..."}],
    steps without a command are dropped (as in the web form)."""
    from modules.snippets.storage import SnippetStorage

    # The storage drops steps without a command and strips both fields.
    data = {"title": _not_blank(title, "title"), "description": description, "steps": steps or []}

    def run():
        git = _primary("snippets")
        return git, SnippetStorage(git).create_snippet(data)

    return await _save_off_loop(run)


def _date_range(start_date: str, end_date: str) -> tuple[str, str]:
    start, end = _iso_date(start_date, "start_date"), _iso_date(end_date, "end_date")
    if end < start:
        raise ToolError("end_date must be on or after start_date")
    return start, end


@tool(WRITE)
async def create_vacation(start_date: str, end_date: str, note: str = "") -> dict[str, Any]:
    """Create a vacation entry (status: planned). Dates YYYY-MM-DD, end inclusive."""
    from modules.vacations.storage import VacationStorage

    start, end = _date_range(start_date, end_date)
    data = {"start_date": start, "end_date": end, "note": note}

    def run():
        git = _primary("vacations")
        return git, VacationStorage(git).create_entry(data)

    return await _save_off_loop(run)


VacationStatus = Literal["planned", "requested", "approved", "documented", "rejected"]


@tool(WRITE)
async def set_vacation_status(entry_id: str, status: VacationStatus) -> dict[str, Any]:
    """Set the status of a vacation entry. approved and documented count as used days."""
    from modules.vacations.storage import VacationStorage

    def run():
        for s in _stores("vacations"):
            vs = VacationStorage(s)
            if vs.get_entry(entry_id):
                return s, _found(vs.update_status(entry_id, status), "Vacation entry", entry_id)
        raise ToolError(f"Vacation entry '{entry_id}' not found")

    return await _save_off_loop(run)


@tool(WRITE)
async def create_appointment(
    title: str,
    start_date: str,
    end_date: str,
    type: Literal["training", "conference", "team_event", "business_trip", "other"] = "other",
    note: str = "",
    recurring: Literal["none", "weekly", "monthly", "yearly"] = "none",
) -> dict[str, Any]:
    """Create an appointment. Dates YYYY-MM-DD, end inclusive."""
    from modules.appointments.storage import AppointmentStorage

    start, end = _date_range(start_date, end_date)
    data = {
        "title": _not_blank(title, "title"),
        "start_date": start,
        "end_date": end,
        "type": type,
        "note": note,
        "recurring": recurring,
    }

    def run():
        git = _primary("appointments")
        return git, AppointmentStorage(git).create_entry(data)

    return await _save_off_loop(run)


# ── HTTP mounting ───────────────────────────────────────────────────────────

_http_app = None
_lifespan: contextlib.AsyncExitStack | None = None


async def start() -> None:
    """Build the HTTP app and start its session manager; a session manager runs
    only once, so every start (app startup, each test client) needs a new one."""
    global _http_app, _lifespan
    # The bearer token is the access control; the SDK's Host-header check would
    # reject every non-localhost host the app is reached under.
    _http_app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    _lifespan = contextlib.AsyncExitStack()
    await _lifespan.enter_async_context(server.session_manager.run())


async def stop() -> None:
    global _http_app
    if _lifespan is not None:
        await _lifespan.aclose()
    _http_app = None


async def _plain(send, status: int, body: bytes, headers: list | None = None) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain")] + (headers or []),
        }
    )
    await send({"type": "http.response.body", "body": body})


class GuardedMCPApp:
    """ASGI app for /mcp: 404 while no token is set, 401 on a wrong one."""

    async def __call__(self, scope, receive, send):
        token = settings_store.load().get("mcp_token", "")
        if not token:
            await _plain(send, 404, b"MCP is disabled: set a token in Settings -> MCP server")
            return
        auth = dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin-1")
        if not hmac.compare_digest(auth.encode(), f"Bearer {token}".encode()):
            await _plain(send, 401, b"Unauthorized", [(b"www-authenticate", b'Bearer realm="daily-helper"')])
            return
        if _http_app is None:
            await _plain(send, 503, b"MCP server not started")
            return
        await _http_app(scope, receive, send)
