"""History module — git-based activity log with filters."""

from datetime import datetime, timedelta, date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core import cache
from core.state import get_storage
from core.templates import templates

router = APIRouter(prefix="/history")

RANGES = {
    "today": "Today",
    "week": "This week",
    "month": "This month",
    "30d": "Last 30 days",
    "90d": "Last 3 months",
    "365d": "This year",
    "all": "All",
}
CACHE_TTL = {
    "today": 60,
    "week": 180,
    "month": 300,
    "30d": 300,
    "90d": 600,
    "365d": 600,
    "all": 600,
}

MODULE_LABELS = {
    "knowledge": "Knowledge",
    "tasks": "Tasks",
    "notes": "Notes",
    "links": "Links",
    "snippets": "Snippets",
    "runbooks": "Runbooks",
    "mail_templates": "Mail Templates",
    "ticket_templates": "Ticket Templates",
    "vacations": "Vacations",
    "appointments": "Appointments",
    "motd": "MOTD",
    "potd": "Picture of the Day",
    "memes": "Memes",
    "rss": "RSS",
}

ACTION_LABELS = {"A": "Added", "M": "Modified", "D": "Deleted"}


def _since_dt(range_key: str) -> "datetime | None":
    today = date.today()
    if range_key == "today":
        return datetime.combine(today, datetime.min.time())
    if range_key == "week":
        return datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    if range_key == "month":
        return datetime.combine(today.replace(day=1), datetime.min.time())
    if range_key == "30d":
        return datetime.combine(today - timedelta(days=30), datetime.min.time())
    if range_key == "90d":
        return datetime.combine(today - timedelta(days=90), datetime.min.time())
    if range_key == "365d":
        return datetime.combine(today.replace(month=1, day=1), datetime.min.time())
    return None  # all


def _load_commits(range_key: str) -> list[dict]:
    """Load grouped commits for range, cached in Redis."""
    cache_key = f"history_commits:{range_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    storage = get_storage()
    if not storage:
        return []
    since = _since_dt(range_key)
    limit = 500 if range_key == "all" else 200
    commits = storage.get_history(since_dt=since, limit=limit)
    cache.set(cache_key, commits, ttl=CACHE_TTL.get(range_key, 300))
    return commits


def _filter_commits(
    commits: list[dict],
    module: str,
    author: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    result = []
    for commit in commits:
        if author and author.lower() not in commit.get("author", "").lower():
            continue
        ts = commit["ts"]
        if date_from:
            try:
                cutoff = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
                if ts < cutoff:
                    continue
            except ValueError:
                pass
        if date_to:
            try:
                cutoff = int(datetime.strptime(date_to, "%Y-%m-%d").timestamp()) + 86400
                if ts > cutoff:
                    continue
            except ValueError:
                pass
        changes = commit["changes"]
        if module:
            changes = [ch for ch in changes if ch.get("module") == module]
        if not changes:
            continue
        result.append({**commit, "changes": changes})
    return result


@router.get("", response_class=HTMLResponse)
async def history_view(
    request: Request,
    range: str = "week",
    module: str = "",
    author: str = "",
    date_from: str = "",
    date_to: str = "",
):
    if range not in RANGES:
        range = "week"
    is_htmx = request.headers.get("HX-Request") == "true"

    commits = _load_commits(range)
    authors = sorted({c.get("author", "") for c in commits if c.get("author")})
    filtered = _filter_commits(commits, module, author, date_from, date_to)

    ctx = {
        "commits": filtered,
        "range": range,
        "ranges": RANGES,
        "module": module,
        "author": author,
        "date_from": date_from,
        "date_to": date_to,
        "authors": authors,
        "module_labels": MODULE_LABELS,
        "action_labels": ACTION_LABELS,
        "active_module": "history",
    }

    if is_htmx:
        return templates.TemplateResponse(request, "modules/history/_list.html", ctx)
    return templates.TemplateResponse(request, "modules/history/index.html", ctx)
