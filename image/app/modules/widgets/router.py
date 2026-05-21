"""Widgets dashboard — customisable home screen with draggable widgets."""

import logging
import os
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core import settings_store
from core.module_repos import get_module_stores
from core.state import get_storage
from core.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/widgets")

# ---------------------------------------------------------------------------
# Widget registry
# ---------------------------------------------------------------------------

WIDGET_REGISTRY: dict[str, dict] = {
    # Stats widgets
    "stats_knowledge": {
        "label": "Knowledge",
        "size": "third",
        "icon": "book-open",
        "url": "/",
        "module": "knowledge",
    },
    "stats_tasks": {
        "label": "Tasks",
        "size": "third",
        "icon": "check-square-2",
        "url": "/tasks",
        "module": "tasks",
    },
    "stats_notes": {
        "label": "Notes",
        "size": "third",
        "icon": "file-text",
        "url": "/notes",
        "module": "notes",
    },
    "stats_links": {
        "label": "Links",
        "size": "third",
        "icon": "link-2",
        "url": "/links",
        "module": "links",
    },
    "stats_vacations": {
        "label": "Vacations",
        "size": "third",
        "icon": "umbrella",
        "url": "/vacations",
        "module": "vacations",
    },
    "stats_appointments": {
        "label": "Appointments",
        "size": "third",
        "icon": "calendar-days",
        "url": "/appointments",
        "module": "appointments",
    },
    "stats_runbooks": {
        "label": "Runbooks",
        "size": "third",
        "icon": "list-ordered",
        "url": "/runbooks",
        "module": "runbooks",
    },
    "stats_snippets": {
        "label": "Snippets",
        "size": "third",
        "icon": "terminal",
        "url": "/snippets",
        "module": "snippets",
    },
    "stats_mail_templates": {
        "label": "Mail Templates",
        "size": "third",
        "icon": "mail",
        "url": "/mail-templates",
        "module": "mail_templates",
    },
    "stats_ticket_templates": {
        "label": "Ticket Templates",
        "size": "third",
        "icon": "ticket",
        "url": "/ticket-templates",
        "module": "ticket_templates",
    },
    "stats_motd": {
        "label": "MOTD",
        "size": "third",
        "icon": "message-circle",
        "url": "/motd",
        "module": "motd",
    },
    "stats_potd": {
        "label": "Picture of the Day",
        "size": "third",
        "icon": "image",
        "url": "/potd",
        "module": "potd",
    },
    "stats_eol": {
        "label": "EOL Tracker",
        "size": "third",
        "icon": "shield-check",
        "url": "/eol",
        "module": "eol",
    },
    "stats_memes": {
        "label": "Memes",
        "size": "third",
        "icon": "smile",
        "url": "/memes",
        "module": "memes",
    },
    "stats_rss": {
        "label": "RSS Feeds",
        "size": "third",
        "icon": "rss",
        "url": "/rss",
        "module": "rss",
    },
    # Content widgets
    "tasks_due": {
        "label": "Due Soon",
        "size": "half",
        "icon": "clock",
        "url": "/tasks",
        "module": "tasks",
    },
    "tasks_overdue": {
        "label": "Overdue Tasks",
        "size": "half",
        "icon": "alert-circle",
        "url": "/tasks",
        "module": "tasks",
    },
    "motd": {
        "label": "Message of the Day",
        "size": "half",
        "icon": "message-circle",
        "url": "/motd",
        "module": "motd",
    },
    "calendar_mini": {
        "label": "Upcoming",
        "size": "half",
        "icon": "calendar",
        "url": "/calendar",
        "module": None,
    },
    "calendar_widget": {
        "label": "Kalender",
        "size": "full",
        "icon": "calendar-days",
        "url": "/calendar",
        "module": None,
    },
    "sprint": {
        "label": "Sprint",
        "size": "half",
        "icon": "timer",
        "url": "/calendar",
        "module": None,
    },
    "vacation_balance": {
        "label": "Vacation Balance",
        "size": "half",
        "icon": "umbrella",
        "url": "/vacations",
        "module": "vacations",
    },
    "next_vacation": {
        "label": "Next Vacation",
        "size": "third",
        "icon": "plane",
        "url": "/vacations",
        "module": "vacations",
    },
    "appointments_upcoming": {
        "label": "Upcoming Appointments",
        "size": "half",
        "icon": "calendar-check",
        "url": "/appointments",
        "module": "appointments",
    },
    "favorites": {"label": "Favorites", "size": "half", "icon": "star", "url": "/", "module": None},
    "recent_activity": {
        "label": "Recent Activity",
        "size": "half",
        "icon": "history",
        "url": "/history",
        "module": None,
    },
    "rss_feed": {"label": "RSS", "size": "half", "icon": "rss", "url": "/rss", "module": "rss"},
    "runbook_overview": {
        "label": "Runbooks",
        "size": "half",
        "icon": "list-ordered",
        "url": "/runbooks",
        "module": "runbooks",
    },
    "quick_capture": {
        "label": "Quick Add",
        "size": "half",
        "icon": "plus-circle",
        "url": "/tasks",
        "module": None,
    },
    "bookmarks": {
        "label": "Bookmarks",
        "size": "half",
        "icon": "bookmark",
        "url": "/links",
        "module": "links",
    },
    "potd": {
        "label": "Picture of the Day",
        "size": "half",
        "icon": "image",
        "url": "/potd",
        "module": "potd",
    },
    "meme": {
        "label": "Meme of the Day",
        "size": "half",
        "icon": "smile",
        "url": "/memes",
        "module": "memes",
    },
    "redis_status": {
        "label": "Redis Cache",
        "size": "half",
        "icon": "zap",
        "url": "/settings",
        "module": None,
    },
    "tmp_usage": {
        "label": "/tmp Usage",
        "size": "third",
        "icon": "hard-drive",
        "url": None,
        "module": None,
    },
    "countdown": {
        "label": "Countdown",
        "size": "third",
        "icon": "timer",
        "url": None,
        "module": None,
    },
    "app_version": {
        "label": "App Version",
        "size": "third",
        "icon": "git-commit",
        "url": None,
        "module": None,
    },
    "repos": {
        "label": "Repositories",
        "size": "half",
        "icon": "database",
        "url": "/settings",
        "module": None,
    },
    "notes_recent": {
        "label": "Recent Notes",
        "size": "half",
        "icon": "file-text",
        "url": "/notes",
        "module": "notes",
    },
}

_DEFAULT_LAYOUT = [
    {"id": "stats_knowledge", "enabled": True, "settings": {}},
    {"id": "stats_tasks", "enabled": True, "settings": {}},
    {"id": "stats_notes", "enabled": True, "settings": {}},
    {"id": "stats_links", "enabled": True, "settings": {}},
    {"id": "stats_vacations", "enabled": True, "settings": {}},
    {"id": "stats_appointments", "enabled": True, "settings": {}},
    {"id": "stats_runbooks", "enabled": True, "settings": {}},
    {"id": "stats_snippets", "enabled": True, "settings": {}},
    {"id": "stats_mail_templates", "enabled": False, "settings": {}},
    {"id": "stats_ticket_templates", "enabled": False, "settings": {}},
    {"id": "stats_motd", "enabled": False, "settings": {}},
    {"id": "stats_potd", "enabled": False, "settings": {}},
    {"id": "stats_memes", "enabled": False, "settings": {}},
    {"id": "stats_rss", "enabled": False, "settings": {}},
    {"id": "stats_eol", "enabled": False, "settings": {}},
    {"id": "tasks_due", "enabled": True, "settings": {"max_items": 5}},
    {"id": "tasks_overdue", "enabled": False, "settings": {"max_items": 5}},
    {"id": "motd", "enabled": True, "settings": {}},
    {"id": "calendar_mini", "enabled": True, "settings": {"days_ahead": 14}},
    {"id": "calendar_widget", "enabled": False, "settings": {}},
    {"id": "sprint", "enabled": False, "settings": {}},
    {"id": "vacation_balance", "enabled": False, "settings": {}},
    {"id": "next_vacation", "enabled": False, "settings": {}},
    {
        "id": "appointments_upcoming",
        "enabled": False,
        "settings": {"days_ahead": 14, "max_items": 5},
    },
    {"id": "favorites", "enabled": False, "settings": {"max_items": 8}},
    {"id": "recent_activity", "enabled": False, "settings": {"max_items": 8}},
    {"id": "rss_feed", "enabled": False, "settings": {"max_items": 5, "feed_id": ""}},
    {"id": "runbook_overview", "enabled": False, "settings": {"max_items": 5}},
    {"id": "quick_capture", "enabled": False, "settings": {}},
    {"id": "bookmarks", "enabled": False, "settings": {"category": "", "max_items": 8}},
    {"id": "potd", "enabled": False, "settings": {}},
    {"id": "meme", "enabled": False, "settings": {}},
    {"id": "redis_status", "enabled": False, "settings": {}},
    {"id": "tmp_usage", "enabled": False, "settings": {}},
    {"id": "countdown", "enabled": False, "settings": {"label": "", "target_date": ""}},
    {"id": "app_version", "enabled": False, "settings": {}},
    {"id": "repos", "enabled": False, "settings": {}},
    {"id": "notes_recent", "enabled": False, "settings": {"max_items": 5}},
]


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


def _get_layout() -> list[dict]:
    cfg = settings_store.load()
    stored = cfg.get("dashboard_widgets")
    # None = never configured → show defaults; otherwise use exactly what was saved
    if stored is None:
        return [dict(e) for e in _DEFAULT_LAYOUT]
    return list(stored)


def _save_layout(layout: list[dict]) -> None:
    cfg = settings_store.load()
    cfg["dashboard_widgets"] = layout
    settings_store.save(cfg)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def _load_counts(cfg: dict, storage) -> dict[str, int]:
    modules = cfg.get("modules_enabled", {})
    counts: dict[str, int] = {}
    if not storage or not getattr(storage, "_stores", None):
        return counts

    def _count_yaml(store, prefix: str) -> int:
        return sum(1 for n in store.list_committed(prefix) if n.endswith(".yaml"))

    def _count_yaml_recursive(store, prefix: str) -> int:
        return sum(1 for n in store.list_committed_recursive(prefix) if n.endswith(".yaml"))

    def _count_all(module: str, prefix: str) -> int:
        return sum(_count_yaml(s, prefix) for s in get_module_stores(module, storage))

    def _count_recursive(module: str, prefix: str) -> int:
        return sum(_count_yaml_recursive(s, prefix) for s in get_module_stores(module, storage))

    simple = {
        "knowledge": lambda: len(storage.get_entries()),
        "tasks": lambda: _count_all("tasks", "tasks"),
        "notes": lambda: _count_all("notes", "notes"),
        "links": lambda: _count_recursive("links", "links"),
        "vacations": lambda: _count_all("vacations", "vacations/entries"),
        "appointments": lambda: _count_all("appointments", "appointments/entries"),
        "runbooks": lambda: _count_all("runbooks", "runbooks"),
        "snippets": lambda: _count_all("snippets", "snippets"),
        "mail_templates": lambda: _count_all("mail_templates", "mail_templates"),
        "ticket_templates": lambda: _count_all("ticket_templates", "ticket_templates"),
        "motd": lambda: sum(_count_yaml(s, "motd") for s in get_module_stores("motd", storage)),
    }
    for mod, fn in simple.items():
        if modules.get(mod, True):
            try:
                counts[mod] = fn()
            except Exception:
                counts[mod] = 0

    if modules.get("potd", True):
        try:
            from modules.potd.router import _list_files_all

            counts["potd"] = len(_list_files_all())
        except Exception:
            counts["potd"] = 0

    if modules.get("memes", True):
        try:
            from modules.memes.router import _list_files_all as _memes_all

            counts["memes"] = len(_memes_all())
        except Exception:
            counts["memes"] = 0

    if modules.get("rss", True):
        try:
            from modules.rss.storage import RssStorage

            seen: set[str] = set()
            for s in get_module_stores("rss", storage):
                for f in RssStorage(s).list_feeds():
                    seen.add(f["id"])
            counts["rss"] = len(seen)
        except Exception:
            counts["rss"] = 0

    return counts


def _load_tasks_due(settings: dict, storage) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        from modules.tasks.storage import TaskStorage

        today = date.today().isoformat()
        tasks, seen = [], set()
        for s in get_module_stores("tasks", storage):
            for t in TaskStorage(s).list_tasks():
                if not t.get("done") and t["id"] not in seen:
                    seen.add(t["id"])
                    tasks.append(t)
        tasks.sort(key=lambda t: (t.get("due_date") or "9999-99-99", t.get("title", "")))
        return tasks[:max_items]
    except Exception:
        return []


def _load_tasks_overdue(settings: dict, storage) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        from modules.tasks.storage import TaskStorage

        today = date.today().isoformat()
        tasks, seen = [], set()
        for s in get_module_stores("tasks", storage):
            for t in TaskStorage(s).list_tasks():
                due = t.get("due_date", "")
                if not t.get("done") and due and due < today and t["id"] not in seen:
                    seen.add(t["id"])
                    tasks.append(t)
        tasks.sort(key=lambda t: t.get("due_date", ""))
        return tasks[:max_items]
    except Exception:
        return []


def _load_motd(storage) -> str:
    if not storage or not getattr(storage, "_stores", None):
        return ""
    try:
        from modules.motd.storage import MotdStorage
        from core import cache as _cache

        all_entries, seen = [], set()
        for s in get_module_stores("motd", storage):
            for e in MotdStorage(s).list_entries():
                if e.get("active", True) and e["id"] not in seen:
                    seen.add(e["id"])
                    all_entries.append(e)
        if not all_entries:
            return ""
        today = date.today()
        # Date-based seed so the same entry shows all day, different each day
        today_int = int(today.strftime("%Y%m%d"))
        offset = today_int
        try:
            r = _cache.get_redis()
            if r:
                val = r.get(f"motd:offset:{today.isoformat()}")
                if val is not None:
                    offset = today_int + int(val)
        except Exception:
            pass
        return all_entries[offset % len(all_entries)].get("text", "")
    except Exception:
        return ""


def _load_calendar_mini(settings: dict, cfg: dict) -> list[dict]:
    days_ahead = int(settings.get("days_ahead", 14))
    storage = get_storage()
    today = date.today()
    end = today + timedelta(days=days_ahead)
    events: list[dict] = []
    try:
        state = cfg.get("vacation_state", "BY")
        import holidays as hol_lib

        country_holidays = hol_lib.country_holidays(
            "DE", subdiv=state, years=[today.year, end.year]
        )
        for d, name in sorted(country_holidays.items()):
            if today <= d <= end:
                events.append({"date": d.isoformat(), "type": "holiday", "title": name})
    except Exception:
        pass
    if storage and getattr(storage, "_stores", None):
        modules = cfg.get("modules_enabled", {})
        try:
            if modules.get("appointments", True):
                from modules.appointments.storage import AppointmentStorage

                seen: set[str] = set()
                for s in get_module_stores("appointments", storage):
                    for a in AppointmentStorage(s).list_entries():
                        if (
                            a["id"] not in seen
                            and today.isoformat() <= a.get("start_date", "") <= end.isoformat()
                        ):
                            seen.add(a["id"])
                            events.append(
                                {
                                    "date": a["start_date"],
                                    "type": "appointment",
                                    "title": a.get("title", ""),
                                }
                            )
        except Exception:
            pass
        try:
            if modules.get("vacations", True):
                from modules.vacations.storage import VacationStorage

                seen_v: set[str] = set()
                for s in get_module_stores("vacations", storage):
                    for v in VacationStorage(s).list_entries():
                        if v["id"] not in seen_v and v.get("status") in (
                            "approved",
                            "requested",
                            "planned",
                        ):
                            vstart = v.get("start_date", "")
                            if vstart and today.isoformat() <= vstart <= end.isoformat():
                                seen_v.add(v["id"])
                                events.append(
                                    {
                                        "date": vstart,
                                        "type": "vacation",
                                        "title": f"Vacation ({v.get('status', '')})",
                                    }
                                )
        except Exception:
            pass
        try:
            if modules.get("tasks", True):
                from modules.tasks.storage import TaskStorage

                seen_t: set[str] = set()
                for s in get_module_stores("tasks", storage):
                    for t in TaskStorage(s).list_tasks():
                        due = t.get("due_date", "")
                        if (
                            t["id"] not in seen_t
                            and not t.get("done")
                            and due
                            and today.isoformat() <= due <= end.isoformat()
                        ):
                            seen_t.add(t["id"])
                            events.append(
                                {"date": due, "type": "task", "title": t.get("title", "")}
                            )
        except Exception:
            pass
    events.sort(key=lambda e: e["date"])
    return events


def _load_calendar_widget(year: int | None, month: int | None, cfg: dict, storage) -> dict:
    from modules.vacations.holidays_helper import get_calendar_data

    today = date.today()
    y = year or today.year
    m = month or today.month
    state = cfg.get("vacation_state", "BY")
    language = cfg.get("locale", "de")

    vacation_entries: list[dict] = []
    appointment_entries: list[dict] = []
    task_entries: list[dict] = []
    modules = cfg.get("modules_enabled", {})

    if storage and getattr(storage, "_stores", None):
        try:
            if modules.get("vacations", True):
                from modules.vacations.storage import VacationStorage

                for s in get_module_stores("vacations", storage):
                    vacation_entries.extend(VacationStorage(s).list_entries())
        except Exception:
            pass
        try:
            if modules.get("appointments", True):
                from modules.appointments.storage import AppointmentStorage

                for s in get_module_stores("appointments", storage):
                    appointment_entries.extend(AppointmentStorage(s).list_entries())
        except Exception:
            pass
        try:
            if modules.get("tasks", True):
                from modules.tasks.storage import TaskStorage

                for s in get_module_stores("tasks", storage):
                    task_entries.extend(TaskStorage(s).list_tasks())
        except Exception:
            pass

    sprint_anchor = None
    anchor_str = cfg.get("sprint_anchor_date", "")
    if anchor_str:
        try:
            sprint_anchor = date.fromisoformat(anchor_str)
        except ValueError:
            pass

    cal = get_calendar_data(
        y,
        m,
        state,
        vacation_entries,
        language=language,
        appointment_entries=appointment_entries,
        task_entries=task_entries,
        sprint_anchor=sprint_anchor,
        sprint_prefix=cfg.get("sprint_prefix", "Sprint"),
        sprint_duration_weeks=int(cfg.get("sprint_duration_weeks", 3)),
    )
    return cal


def _load_sprint(cfg: dict, storage=None) -> dict | None:
    anchor_str = cfg.get("sprint_anchor_date", "")
    if not anchor_str:
        return None
    try:
        from modules.calendar.sprint_helper import get_sprint_for_date, capacity_for_sprint
        from modules.calendar.router import _load_entries

        anchor = date.fromisoformat(anchor_str)
        duration_weeks = int(cfg.get("sprint_duration_weeks", 3))
        prefix = cfg.get("sprint_name_prefix", "Sprint")
        state = cfg.get("vacation_state", "BY")
        blocked_types = cfg.get("sprint_blocked_appt_types", [])
        today = date.today()

        sprint = get_sprint_for_date(today, anchor, prefix, duration_weeks)

        vac_entries: list[dict] = []
        appt_entries: list[dict] = []
        if storage:
            for yr in {sprint["start"].year, sprint["end"].year}:
                v, a, _ = _load_entries(cfg, storage, yr)
                vac_entries += v
                appt_entries += a

        return capacity_for_sprint(
            sprint, vac_entries, appt_entries, blocked_types, state, today=today
        )
    except Exception:
        return None


def _load_vacation_balance(cfg: dict, storage) -> dict | None:
    if not storage or not getattr(storage, "_stores", None):
        return None
    try:
        from modules.vacations.storage import VacationStorage

        state = cfg.get("vacation_state", "BY")
        total_days = int(cfg.get("vacation_days_per_year", 30)) + float(
            cfg.get("vacation_carryover", 0)
        )
        year = date.today().year
        vs = None
        for s in get_module_stores("vacations", storage):
            vs = VacationStorage(s)
            break
        if not vs:
            return None
        all_entries = []
        seen: set[str] = set()
        for s in get_module_stores("vacations", storage):
            for e in VacationStorage(s).list_entries(year):
                if e["id"] not in seen:
                    seen.add(e["id"])
                    all_entries.append(e)
        account = vs.get_account(year, total_days, state, entries=all_entries)
        return account
    except Exception:
        return None


def _load_next_vacation(cfg: dict, storage) -> tuple:
    if not storage or not getattr(storage, "_stores", None):
        return None, None
    try:
        from modules.vacations.router import (
            _days_until_next_vacation,
            _list_all_entries,
            _vacation_settings,
        )

        state, _ = _vacation_settings()
        all_entries = _list_all_entries()
        return _days_until_next_vacation(all_entries, state, date.today())
    except Exception:
        return None, None


def _load_appointments_upcoming(settings: dict, storage) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    days_ahead = int(settings.get("days_ahead", 14))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        from modules.appointments.storage import AppointmentStorage

        today = date.today().isoformat()
        end = (date.today() + timedelta(days=days_ahead)).isoformat()
        appts, seen = [], set()
        for s in get_module_stores("appointments", storage):
            for a in AppointmentStorage(s).list_entries():
                if a["id"] not in seen and today <= a.get("start_date", "") <= end:
                    seen.add(a["id"])
                    appts.append(a)
        appts.sort(key=lambda a: a.get("start_date", ""))
        return appts[:max_items]
    except Exception:
        return []


def _load_favorites(settings: dict) -> list[dict]:
    max_items = int(settings.get("max_items", 8))
    try:
        from core import favorites as _fav

        return _fav.list_favorites()[:max_items]
    except Exception:
        return []


def _load_recent_activity(settings: dict) -> list[dict]:
    max_items = int(settings.get("max_items", 8))
    storage = get_storage()
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        commits = storage.get_history(limit=max_items)
        return commits[:max_items]
    except Exception:
        return []


def _load_rss(settings: dict, cfg: dict, storage) -> tuple[list[dict], list[dict]]:
    """Returns (feeds, articles)."""
    max_items = int(settings.get("max_items", 5))
    feed_id = settings.get("feed_id", "")
    if not storage or not getattr(storage, "_stores", None):
        return [], []
    try:
        from modules.rss.storage import RssStorage
        from modules.rss.router import _get_feed_cached

        feeds_all: list[dict] = []
        seen: set[str] = set()
        for s in get_module_stores("rss", storage):
            for f in RssStorage(s).list_feeds():
                if f["id"] not in seen and f.get("enabled", True):
                    seen.add(f["id"])
                    feeds_all.append(f)
        if not feeds_all:
            return [], []
        target_feeds = [f for f in feeds_all if f["id"] == feed_id] if feed_id else feeds_all[:1]
        articles: list[dict] = []
        for feed in target_feeds:
            data = _get_feed_cached(feed)
            for item in data.get("items", [])[:max_items]:
                articles.append({**item, "feed_name": feed.get("name", "")})
        return feeds_all, articles[:max_items]
    except Exception:
        return [], []


def _load_runbooks(settings: dict, storage) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        from modules.runbooks.storage import RunbookStorage

        runbooks, seen = [], set()
        for s in get_module_stores("runbooks", storage):
            for r in RunbookStorage(s).list_runbooks():
                if r["id"] not in seen:
                    seen.add(r["id"])
                    runbooks.append(r)
        return runbooks[:max_items]
    except Exception:
        return []


def _load_bookmarks(settings: dict, storage) -> list[dict]:
    max_items = int(settings.get("max_items", 8))
    category = settings.get("category", "")
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        from modules.links.storage import LinkStorage

        links, seen = [], set()
        for s in get_module_stores("links", storage):
            for lnk in LinkStorage(s).list_links(category=category):
                if lnk["id"] not in seen:
                    seen.add(lnk["id"])
                    links.append(lnk)
        return links[:max_items]
    except Exception:
        return []


def _load_potd() -> dict | None:
    try:
        from modules.potd.router import get_daily_all

        return get_daily_all()
    except Exception:
        return None


def _load_meme() -> dict | None:
    try:
        from modules.memes.router import get_daily_all as get_meme_daily

        return get_meme_daily()
    except Exception:
        return None


def _load_redis_status() -> dict:
    from core import cache as _cache

    if not _cache.is_connected():
        return {"connected": False}
    stats = _cache.get_stats()
    if not stats:
        return {"connected": True, "key_count": 0, "hit_rate": None, "breakdown": {}}
    return {
        "connected": True,
        "key_count": stats["key_count"],
        "hit_rate": stats["hit_rate"],
        "breakdown": stats["breakdown"],
    }


def _load_tmp_usage() -> dict | None:
    import shutil as _shutil
    import subprocess as _subprocess
    from pathlib import Path as _Path

    try:
        du = _shutil.disk_usage("/tmp")
        info: dict = {"total": du.total, "used": du.used, "free": du.free}
        repos_root = _Path("/tmp/daily-helper/repos")
        if repos_root.is_dir():
            r = _subprocess.run(
                ["du", "-sb", str(repos_root)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                info["repos_bytes"] = int(r.stdout.split()[0])
        return info
    except Exception:
        return None


def _load_countdown(settings: dict) -> dict:
    from datetime import date as _date

    label = settings.get("label", "").strip()
    raw = settings.get("target_date", "").strip()
    if not raw:
        return {"configured": False}
    try:
        target = _date.fromisoformat(raw)
    except ValueError:
        return {"configured": False}
    today = _date.today()
    delta = (target - today).days
    return {
        "configured": True,
        "label": label or "Countdown",
        "target_date": raw,
        "days": delta,
    }


def _load_app_version() -> dict:
    version = os.environ.get("APP_VERSION", "dev")
    if len(version) == 40 and all(c in "0123456789abcdef" for c in version):
        version = version[:7]
    info: dict = {"version": version, "commit": None}
    if version == "dev":
        import subprocess as _subprocess

        try:
            r = _subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0:
                info["commit"] = r.stdout.strip()
        except Exception:
            pass
    return info


def _load_repos_widget(storage) -> list[dict]:
    import subprocess as _subprocess
    from pathlib import Path as _Path

    if not storage or not getattr(storage, "_stores", None):
        return []
    repos_root = _Path("/tmp/daily-helper/repos")
    result = []
    for rid, store in storage._stores.items():
        cfg = store._settings if hasattr(store, "_settings") else {}
        size_bytes: int | None = None
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
                    size_bytes = int(r.stdout.split()[0])
            except Exception:
                pass
        result.append(
            {
                "id": rid,
                "name": cfg.get("name", rid),
                "enabled": cfg.get("enabled", True),
                "write": bool(cfg.get("ssh_key") or cfg.get("push_token")),
                "size_bytes": size_bytes,
                "ca_cert": bool(cfg.get("ca_cert")),
                "gpg_key": bool(cfg.get("gpg_key")),
                "git_user_name": cfg.get("git_user_name", ""),
                "git_user_email": cfg.get("git_user_email", ""),
            }
        )
    return result


def _load_notes_recent(settings: dict, storage) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        from modules.notes.storage import NoteStorage

        notes, seen = [], set()
        for s in get_module_stores("notes", storage):
            for n in NoteStorage(s).list_notes():
                if n["id"] not in seen:
                    seen.add(n["id"])
                    notes.append(n)
        # Sort by modified/created desc
        notes.sort(key=lambda n: n.get("modified", n.get("created", "")), reverse=True)
        return notes[:max_items]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def widgets_dashboard(request: Request):
    cfg = settings_store.load()
    storage = get_storage()
    layout = _get_layout()
    modules_enabled = cfg.get("modules_enabled", {})

    active_widgets = []
    layout_by_id = {e["id"]: e for e in layout}
    for entry in layout:
        wid = entry["id"]
        if wid not in WIDGET_REGISTRY:
            continue
        meta = WIDGET_REGISTRY[wid]
        mod = meta.get("module")
        if mod and not modules_enabled.get(mod, True):
            continue
        if entry.get("enabled", True):
            active_widgets.append({**meta, "id": wid, "settings": entry.get("settings", {})})

    active_ids = {w["id"] for w in active_widgets}
    available_widgets = []
    for wid, meta in WIDGET_REGISTRY.items():
        if wid in active_ids:
            continue
        mod = meta.get("module")
        if mod and not modules_enabled.get(mod, True):
            continue
        entry = layout_by_id.get(wid, {})
        available_widgets.append({**meta, "id": wid, "settings": entry.get("settings", {})})

    # Load data for active widgets
    counts: dict = {}
    widget_data: dict = {}

    needs_counts = any(wid.startswith("stats_") for wid in active_ids)
    if needs_counts:
        counts = _load_counts(cfg, storage)

    for w in active_widgets:
        wid = w["id"]
        s = w["settings"]
        try:
            if wid == "tasks_due":
                widget_data["tasks_due"] = _load_tasks_due(s, storage)
            elif wid == "tasks_overdue":
                widget_data["tasks_overdue"] = _load_tasks_overdue(s, storage)
            elif wid == "motd":
                widget_data["motd_text"] = _load_motd(storage)
            elif wid == "calendar_mini":
                widget_data["calendar_events"] = _load_calendar_mini(s, cfg)
            elif wid == "calendar_widget":
                widget_data["cal_widget"] = _load_calendar_widget(None, None, cfg, storage)
            elif wid == "sprint":
                widget_data["sprint"] = _load_sprint(cfg, storage)
            elif wid == "vacation_balance":
                widget_data["vacation_balance"] = _load_vacation_balance(cfg, storage)
            elif wid == "next_vacation":
                days, vac = _load_next_vacation(cfg, storage)
                widget_data["next_vacation"] = vac
                widget_data["next_vacation_days"] = days
            elif wid == "appointments_upcoming":
                widget_data["appointments_upcoming"] = _load_appointments_upcoming(s, storage)
            elif wid == "favorites":
                widget_data["favorites"] = _load_favorites(s)
            elif wid == "recent_activity":
                widget_data["recent_activity"] = _load_recent_activity(s)
            elif wid == "rss_feed":
                feeds, articles = _load_rss(s, cfg, storage)
                widget_data["rss_feeds"] = feeds
                widget_data["rss_articles"] = articles
            elif wid == "runbook_overview":
                widget_data["runbooks"] = _load_runbooks(s, storage)
            elif wid == "bookmarks":
                widget_data["bookmarks"] = _load_bookmarks(s, storage)
            elif wid == "potd":
                widget_data["potd_entry"] = _load_potd()
            elif wid == "meme":
                widget_data["meme_entry"] = _load_meme()
            elif wid == "redis_status":
                widget_data["redis_status"] = _load_redis_status()
            elif wid == "tmp_usage":
                widget_data["tmp_usage"] = _load_tmp_usage()
            elif wid == "countdown":
                widget_data["countdown"] = _load_countdown(s)
            elif wid == "app_version":
                widget_data["app_version_info"] = _load_app_version()
            elif wid == "repos":
                widget_data["repos_widget"] = _load_repos_widget(storage)
            elif wid == "notes_recent":
                widget_data["notes_recent"] = _load_notes_recent(s, storage)
        except Exception:
            logger.exception("Error loading widget data for %s", wid)

    # Collect RSS feeds list for settings popover
    rss_feeds_for_settings: list[dict] = []
    try:
        if storage and getattr(storage, "_stores", None):
            from modules.rss.storage import RssStorage

            seen: set[str] = set()
            for s in get_module_stores("rss", storage):
                for f in RssStorage(s).list_feeds():
                    if f["id"] not in seen:
                        seen.add(f["id"])
                        rss_feeds_for_settings.append(f)
    except Exception:
        pass

    # Collect link categories for bookmarks settings
    link_categories: list[str] = []
    try:
        if storage and getattr(storage, "_stores", None):
            from modules.links.storage import LinkStorage

            cats: set[str] = set()
            for s in get_module_stores("links", storage):
                for lnk in LinkStorage(s).list_links():
                    if lnk.get("category"):
                        cats.add(lnk["category"])
            link_categories = sorted(cats)
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "widgets.html",
        {
            "active_widgets": active_widgets,
            "available_widgets": available_widgets,
            "counts": counts,
            **widget_data,
            "today": date.today().isoformat(),
            "rss_feeds_for_settings": rss_feeds_for_settings,
            "link_categories": link_categories,
            "active_module": "widgets",
        },
    )


@router.post("/layout")
async def save_layout(request: Request):
    try:
        data = await request.json()
        layout = _get_layout()
        layout_by_id = {e["id"]: e for e in layout}
        new_layout = []
        for item in data:
            wid = item.get("id")
            if wid not in WIDGET_REGISTRY:
                continue
            entry = layout_by_id.get(wid, {"id": wid, "settings": {}})
            entry["enabled"] = bool(item.get("enabled", True))
            if "settings" in item:
                entry["settings"] = item["settings"]
            new_layout.append(entry)
        _save_layout(new_layout)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("Error saving widget layout")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.get("/calendar-partial", response_class=HTMLResponse)
async def calendar_widget_partial(
    request: Request, year: int | None = None, month: int | None = None
):
    cfg = settings_store.load()
    storage = get_storage()
    cal = _load_calendar_widget(year, month, cfg, storage)
    return templates.TemplateResponse(
        request,
        "widgets/_calendar_widget_body.html",
        {"cal": cal},
    )


@router.post("/{widget_id}/settings")
async def save_widget_settings(widget_id: str, request: Request):
    if widget_id not in WIDGET_REGISTRY:
        return JSONResponse({"ok": False}, status_code=404)
    try:
        new_settings = await request.json()
        layout = _get_layout()
        for entry in layout:
            if entry["id"] == widget_id:
                entry["settings"] = new_settings
                break
        _save_layout(layout)
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
