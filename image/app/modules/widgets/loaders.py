"""Data loaders for the dashboard widgets.

Every loader is called once per request with the widget's own settings and a
shared _LoaderContext; the dispatch table at the bottom maps widget ids to
loaders. Loaders must stay side-effect free — the dashboard calls all of them
and a failure of one is caught and logged, not propagated.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from core import cache
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage

logger = logging.getLogger(__name__)


def _load_counts(cfg: dict, storage, needed: set[str] | None = None) -> dict[str, int]:
    """Compute per-module entry counts for stats_* widgets.

    `needed` restricts computation to the given module keys — with ~13
    possible modules and each requiring its own git listing call(s), a
    dashboard with only one stats widget enabled shouldn't pay for all 13.
    """
    modules = cfg.get("modules_enabled", {})
    counts: dict[str, int] = {}
    if not storage or not getattr(storage, "_stores", None):
        return counts

    def _wanted(mod: str) -> bool:
        return (needed is None or mod in needed) and modules.get(mod, True)

    def _count_yaml(store, prefix: str) -> int:
        return sum(1 for n in store.list_committed(prefix) if n.endswith(".yaml"))

    def _count_yaml_recursive(store, prefix: str) -> int:
        return sum(1 for n in store.list_committed_recursive(prefix) if n.endswith(".yaml"))

    def _count_md_recursive(store, prefix: str) -> int:
        return sum(1 for n in store.list_committed_recursive(prefix) if n.endswith(".md"))

    def _count_all(module: str, prefix: str) -> int:
        return sum(_count_yaml(s, prefix) for s in get_module_stores(module, storage))

    def _count_recursive(module: str, prefix: str) -> int:
        return sum(_count_yaml_recursive(s, prefix) for s in get_module_stores(module, storage))

    simple = {
        "knowledge": lambda: sum(_count_md_recursive(s, "knowledge") for s in get_module_stores("knowledge", storage)),
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
        "eol": lambda: _count_all("eol", "eol"),
    }
    for mod, fn in simple.items():
        if _wanted(mod):
            try:
                counts[mod] = fn()
            except Exception:
                # A tile showing 0 looks like "no entries", not like a failure,
                # so the reason has to end up in the log at least.
                logger.warning("Count failed for module %s", mod, exc_info=True)
                counts[mod] = 0

    if _wanted("potd"):
        try:
            from modules.potd.router import _list_files_all

            counts["potd"] = len(_list_files_all())
        except Exception:
            logger.warning("Count failed for module potd", exc_info=True)
            counts["potd"] = 0

    if _wanted("memes"):
        try:
            from modules.memes.router import _list_files_all as _memes_all

            counts["memes"] = len(_memes_all())
        except Exception:
            logger.warning("Count failed for module memes", exc_info=True)
            counts["memes"] = 0

    if _wanted("rss"):
        try:
            from modules.rss.storage import RssStorage

            seen: set[str] = set()
            for s in get_module_stores("rss", storage):
                for f in RssStorage(s).list_feeds():
                    seen.add(f["id"])
            counts["rss"] = len(seen)
        except Exception:
            logger.warning("Count failed for module rss", exc_info=True)
            counts["rss"] = 0

    return counts


def _vacation_entries_cached(storage, cache: dict | None, year: int | None = None) -> list[dict]:
    """Deduped vacation entries across multi-repo stores, memoized per `cache`
    dict for the lifetime of one request — several widgets (calendar mini,
    calendar widget, vacation balance) load the same entries independently."""
    if cache is not None and year in cache:
        return cache[year]
    from modules.vacations.storage import VacationStorage

    seen: set[str] = set()
    entries: list[dict] = []
    for s in get_module_stores("vacations", storage):
        for e in VacationStorage(s).list_entries(year):
            if e["id"] not in seen:
                seen.add(e["id"])
                entries.append(e)
    if cache is not None:
        cache[year] = entries
    return entries


def _tasks_cached(storage, cache: dict | None) -> list[dict]:
    """Deduped tasks across multi-repo stores, memoized per `cache` dict for
    the lifetime of one request — tasks_due, tasks_overdue, calendar mini and
    the full calendar widget otherwise each load the same tasks independently."""
    if cache is not None and "tasks" in cache:
        return cache["tasks"]
    from modules.tasks.storage import TaskStorage

    seen: set[str] = set()
    tasks: list[dict] = []
    for s in get_module_stores("tasks", storage):
        for t in TaskStorage(s).list_tasks():
            if t["id"] not in seen:
                seen.add(t["id"])
                tasks.append(t)
    if cache is not None:
        cache["tasks"] = tasks
    return tasks


def _appointments_cached(storage, cache: dict | None) -> list[dict]:
    """Deduped appointments across multi-repo stores, memoized per `cache`
    dict for the lifetime of one request — appointments_upcoming, calendar
    mini and the full calendar widget otherwise each load them independently."""
    if cache is not None and "appointments" in cache:
        return cache["appointments"]
    from modules.appointments.storage import AppointmentStorage

    seen: set[str] = set()
    appts: list[dict] = []
    for s in get_module_stores("appointments", storage):
        for a in AppointmentStorage(s).list_entries():
            if a["id"] not in seen:
                seen.add(a["id"])
                appts.append(a)
    if cache is not None:
        cache["appointments"] = appts
    return appts


def _load_tasks_due(settings: dict, storage, task_cache: dict | None = None) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        tasks = [t for t in _tasks_cached(storage, task_cache) if not t.get("done")]
        tasks.sort(key=lambda t: (t.get("due_date") or "9999-99-99", t.get("title", "")))
        return tasks[:max_items]
    except Exception:
        return []


def _load_tasks_overdue(settings: dict, storage, task_cache: dict | None = None) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        today = date.today().isoformat()
        tasks = [
            t
            for t in _tasks_cached(storage, task_cache)
            if not t.get("done") and t.get("due_date", "") and t.get("due_date", "") < today
        ]
        tasks.sort(key=lambda t: t.get("due_date", ""))
        return tasks[:max_items]
    except Exception:
        return []


def _load_motd(storage) -> str:
    if not storage or not getattr(storage, "_stores", None):
        return ""
    try:
        from core import cache as _cache

        from modules.motd.storage import MotdStorage

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


def _load_calendar_mini(
    settings: dict,
    cfg: dict,
    storage=None,
    vac_cache: dict | None = None,
    task_cache: dict | None = None,
    appt_cache: dict | None = None,
) -> list[dict]:
    days_ahead = int(settings.get("days_ahead", 14))
    storage = storage or get_storage()
    today = date.today()
    end = today + timedelta(days=days_ahead)
    events: list[dict] = []
    try:
        state = cfg.get("vacation_state", "BY")
        import holidays as hol_lib

        country_holidays = hol_lib.country_holidays("DE", subdiv=state, years=[today.year, end.year])
        for d, name in sorted(country_holidays.items()):
            if today <= d <= end:
                events.append({"date": d.isoformat(), "type": "holiday", "title": name})
    except Exception:
        pass
    if storage and getattr(storage, "_stores", None):
        modules = cfg.get("modules_enabled", {})
        try:
            if modules.get("appointments", True):
                for a in _appointments_cached(storage, appt_cache):
                    if today.isoformat() <= a.get("start_date", "") <= end.isoformat():
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
                for v in _vacation_entries_cached(storage, vac_cache):
                    if v.get("status") in ("approved", "requested", "planned"):
                        vstart = v.get("start_date", "")
                        if vstart and today.isoformat() <= vstart <= end.isoformat():
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
                for t in _tasks_cached(storage, task_cache):
                    due = t.get("due_date", "")
                    if not t.get("done") and due and today.isoformat() <= due <= end.isoformat():
                        events.append({"date": due, "type": "task", "title": t.get("title", "")})
        except Exception:
            pass
    events.sort(key=lambda e: e["date"])
    return events


def _load_calendar_widget(
    year: int | None,
    month: int | None,
    cfg: dict,
    storage,
    vac_cache: dict | None = None,
    task_cache: dict | None = None,
    appt_cache: dict | None = None,
) -> dict:
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
                vacation_entries.extend(_vacation_entries_cached(storage, vac_cache))
        except Exception:
            pass
        try:
            if modules.get("appointments", True):
                appointment_entries.extend(_appointments_cached(storage, appt_cache))
        except Exception:
            pass
        try:
            if modules.get("tasks", True):
                task_entries.extend(_tasks_cached(storage, task_cache))
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
        from modules.calendar.router import _load_entries
        from modules.calendar.sprint_helper import capacity_for_sprint, get_sprint_for_date

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

        return capacity_for_sprint(sprint, vac_entries, appt_entries, blocked_types, state, today=today)
    except Exception:
        return None


def _load_vacation_balance(cfg: dict, storage, vac_cache: dict | None = None) -> dict | None:
    if not storage or not getattr(storage, "_stores", None):
        return None
    try:
        from modules.vacations.storage import VacationStorage

        state = cfg.get("vacation_state", "BY")
        total_days = int(cfg.get("vacation_days_per_year", 30)) + float(cfg.get("vacation_carryover", 0))
        year = date.today().year
        vs = None
        for s in get_module_stores("vacations", storage):
            vs = VacationStorage(s)
            break
        if not vs:
            return None
        all_entries = _vacation_entries_cached(storage, vac_cache, year)
        account = vs.get_account(year, total_days, state, entries=all_entries)
        return account
    except Exception:
        return None


def _load_next_vacation(cfg: dict, storage, vac_cache: dict | None = None) -> tuple:
    if not storage or not getattr(storage, "_stores", None):
        return None, None
    try:
        from modules.vacations.router import _days_until_next_vacation, _vacation_settings

        state, _ = _vacation_settings()
        all_entries = _vacation_entries_cached(storage, vac_cache)
        return _days_until_next_vacation(all_entries, state, date.today())
    except Exception:
        return None, None


def _load_eol_expiring(settings: dict, storage) -> list[dict]:
    days_ahead = int(settings.get("days_ahead", 90))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        from modules.eol.api_client import _parse_date, get_product_cycles
        from modules.eol.storage import EolStorage

        store = get_primary_store("eol", storage)
        if not store:
            return []
        entries = EolStorage(store).list_entries()
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)
        result = []
        for e in entries:
            try:
                cycles = get_product_cycles(e["product"])
                cycle_data = next((c for c in cycles if str(c.get("cycle")) == str(e["cycle"])), None)
                if not cycle_data:
                    continue
                eol_val = cycle_data.get("eol")
                if eol_val is False or not eol_val:
                    continue
                eol_date = _parse_date(eol_val)
                if eol_date is None or eol_date > cutoff:
                    continue
                days_left = (eol_date - today).days
                result.append(
                    {
                        "id": e["id"],
                        "product": e["product"],
                        "cycle": e["cycle"],
                        "label": e.get("label") or f"{e['product']} {e['cycle']}",
                        "eol_date": eol_date.isoformat(),
                        "days_left": days_left,
                        "expired": days_left < 0,
                    }
                )
            except Exception:
                continue
        result.sort(key=lambda x: x["days_left"])
        return result
    except Exception:
        return []


def _load_appointments_upcoming(settings: dict, storage, appt_cache: dict | None = None) -> list[dict]:
    max_items = int(settings.get("max_items", 5))
    days_ahead = int(settings.get("days_ahead", 14))
    if not storage or not getattr(storage, "_stores", None):
        return []
    try:
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=days_ahead)).isoformat()
        appts = [a for a in _appointments_cached(storage, appt_cache) if today <= a.get("start_date", "") <= end]
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
        from modules.rss.router import _get_feed_cached
        from modules.rss.storage import RssStorage

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
        from modules.links.storage import link_storages

        links, seen = [], set()
        for s in get_module_stores("links", storage):
            for link_storage in link_storages(s):
                for lnk in link_storage.list_links(category=category):
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


_DU_CACHE_TTL = 300  # seconds — `du -sb` walks the whole repo tree incl. .git history


def _cached_du_sb(path) -> int | None:
    """du -sb a directory, cached — unlike every other widget data loader in
    this file, this used to run uncached on every dashboard load, which for
    a repo with long history/attachments is a real blocking disk-I/O cost."""
    import subprocess as _subprocess

    key = f"widgets:du:{path}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    size: int | None = None
    try:
        r = _subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            size = int(r.stdout.split()[0])
    except Exception:
        size = None
    cache.set(key, size, ttl=_DU_CACHE_TTL)
    return size


def _load_tmp_usage() -> dict | None:
    import shutil as _shutil

    try:
        du = _shutil.disk_usage("/tmp")
        info: dict = {"total": du.total, "used": du.used, "free": du.free}
        from core.storage import DATA_DIR as _DATA_DIR

        repos_root = _DATA_DIR / "repos"
        if repos_root.is_dir():
            repos_bytes = _cached_du_sb(repos_root)
            if repos_bytes is not None:
                info["repos_bytes"] = repos_bytes
        return info
    except Exception:
        return None


def _load_countdown(settings: dict) -> dict:
    from datetime import date as _date

    try:
        label = str(settings.get("label", "")).strip()
        raw = str(settings.get("target_date", "")).strip()
    except Exception:
        return {"configured": False}
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
    if not storage or not getattr(storage, "_stores", None):
        return []
    from core.storage import DATA_DIR as _DATA_DIR

    repos_root = _DATA_DIR / "repos"
    result = []
    for rid, store in storage._stores.items():
        cfg = store._settings if hasattr(store, "_settings") else {}
        size_bytes: int | None = None
        repo_path = repos_root / rid
        if repo_path.is_dir():
            try:
                size_bytes = _cached_du_sb(repo_path)
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
# Loader dispatch
# ---------------------------------------------------------------------------


@dataclass
class _LoaderContext:
    """Everything a widget loader may need beyond its own settings. The three
    caches are shared across loaders so that e.g. the calendar and the vacation
    balance read the vacation entries from git once per request, not twice."""

    cfg: dict
    storage: object
    vac_cache: dict
    task_cache: dict
    appt_cache: dict


def _load_next_vacation_data(cfg: dict, storage, vac_cache: dict) -> dict:
    days, vac = _load_next_vacation(cfg, storage, vac_cache)
    return {"next_vacation": vac, "next_vacation_days": days}


def _load_rss_data(s: dict, cfg: dict, storage) -> dict:
    feeds, articles = _load_rss(s, cfg, storage)
    return {"rss_feeds": feeds, "rss_articles": articles}


# Widget-ID -> Loader. Each loader gets the widget's own settings plus the
# shared context and returns the template variables it fills. Widgets without
# an entry render from the registry alone (quick_capture) or from `counts`
# (the stats_* family).
_WIDGET_LOADERS: dict[str, Callable[[dict, "_LoaderContext"], dict]] = {
    "tasks_due": lambda s, c: {"tasks_due": _load_tasks_due(s, c.storage, c.task_cache)},
    "tasks_overdue": lambda s, c: {"tasks_overdue": _load_tasks_overdue(s, c.storage, c.task_cache)},
    "motd": lambda s, c: {"motd_text": _load_motd(c.storage)},
    "calendar_mini": lambda s, c: {
        "calendar_events": _load_calendar_mini(s, c.cfg, c.storage, c.vac_cache, c.task_cache, c.appt_cache)
    },
    "calendar_widget": lambda s, c: {
        "cal_widget": _load_calendar_widget(None, None, c.cfg, c.storage, c.vac_cache, c.task_cache, c.appt_cache)
    },
    "sprint": lambda s, c: {"sprint": _load_sprint(c.cfg, c.storage)},
    "vacation_balance": lambda s, c: {"vacation_balance": _load_vacation_balance(c.cfg, c.storage, c.vac_cache)},
    "next_vacation": lambda s, c: _load_next_vacation_data(c.cfg, c.storage, c.vac_cache),
    "eol_expiring": lambda s, c: {"eol_expiring": _load_eol_expiring(s, c.storage)},
    "appointments_upcoming": lambda s, c: {
        "appointments_upcoming": _load_appointments_upcoming(s, c.storage, c.appt_cache)
    },
    "favorites": lambda s, c: {"favorites": _load_favorites(s)},
    "recent_activity": lambda s, c: {"recent_activity": _load_recent_activity(s)},
    "rss_feed": lambda s, c: _load_rss_data(s, c.cfg, c.storage),
    "runbook_overview": lambda s, c: {"runbooks": _load_runbooks(s, c.storage)},
    "bookmarks": lambda s, c: {"bookmarks": _load_bookmarks(s, c.storage)},
    "potd": lambda s, c: {"potd_entry": _load_potd()},
    "meme": lambda s, c: {"meme_entry": _load_meme()},
    "redis_status": lambda s, c: {"redis_status": _load_redis_status()},
    "tmp_usage": lambda s, c: {"tmp_usage": _load_tmp_usage()},
    "countdown": lambda s, c: {"countdown": _load_countdown(s)},
    "app_version": lambda s, c: {"app_version_info": _load_app_version()},
    "repos": lambda s, c: {"repos_widget": _load_repos_widget(c.storage)},
    "notes_recent": lambda s, c: {"notes_recent": _load_notes_recent(s, c.storage)},
}
