"""Cross-module search behind /search.

Each module contributes one provider: a function that turns a query into result
items. The surrounding work — module enabled?, storage present?, date filter,
error isolation, result cap, group envelope — is identical for all of them and
lives in run_global_search(), so a provider is only its own lookup.
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from core import cache
from core.module_repos import get_primary_store

logger = logging.getLogger(__name__)

MAX_RESULTS_PER_MODULE = 10
CACHE_TTL_SECONDS = 60


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
    # Escape HTML then re-insert <mark> around the match (adjusted positions)
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


@dataclass(frozen=True)
class Query:
    """The search request, as every provider needs it."""

    q: str
    date_from: str
    date_to: str
    storage: object

    @property
    def ql(self) -> str:
        return self.q.lower()

    def in_range(self, date_str: str) -> bool:
        return _date_in_range(date_str, self.date_from, self.date_to)

    def store(self, module: str):
        return get_primary_store(module, self.storage)

    def matches(self, entry: dict, *keys: str) -> bool:
        """Substring match over the given fields — used by the modules whose
        storage has no search of its own."""
        return any(self.ql in (entry.get(k) or "").lower() for k in keys)


@dataclass(frozen=True)
class Provider:
    module: str
    icon: str
    label: str
    url: str  # group link, {q} is filled in
    search: Callable[[Query], list[dict]]


def _search_knowledge(query: Query) -> list[dict]:
    results = query.storage.search(query.q)
    return [
        {
            "title": r.get("title", r.get("slug", "")),
            "subtitle": r.get("category", ""),
            # search() returns the matched excerpt as "snippet"; there is no
            # "body" key, so highlighting that one always produced an empty
            # string and the result rendered without any context.
            "snippet": _highlight(r.get("snippet", ""), query.q),
            "url": f"/knowledge/entries/{r['repo_id']}/{r.get('category', '')}/{r.get('slug', '')}",
        }
        for r in results
        if query.in_range(r.get("created", ""))
    ]


def _search_tasks(query: Query) -> list[dict]:
    from modules.tasks.storage import TaskStorage

    store = query.store("tasks")
    if not store:
        return []
    return [
        {
            "title": t["title"],
            "subtitle": ("Due " + t["due_date"]) if t.get("due_date") else "",
            "snippet": _highlight(t.get("description", ""), query.q),
            "url": f"/tasks?q={query.q}",
        }
        for t in TaskStorage(store).search_tasks(query.q)
        if query.in_range(t.get("created", ""))
    ]


def _search_notes(query: Query) -> list[dict]:
    from modules.notes.storage import NoteStorage

    store = query.store("notes")
    if not store:
        return []
    return [
        {
            "title": n["subject"],
            "subtitle": "",
            "snippet": _highlight(n.get("body", ""), query.q),
            "url": f"/notes/{n['id']}",
        }
        for n in NoteStorage(store).list_notes(query=query.q)
        if query.in_range(n.get("created", n.get("updated", "")))
    ]


def _search_links(query: Query) -> list[dict]:
    """Links are grouped into user-defined sections; link_storages() walks all
    of them. Searching the default section alone silently ignored every link
    the user had filed elsewhere."""
    from modules.links.storage import link_storages

    store = query.store("links")
    if not store:
        return []
    results = []
    seen: set[str] = set()
    for link_storage in link_storages(store):
        for lk in link_storage.list_links(query=query.q):
            if lk.get("id") in seen or not query.in_range(lk.get("created", "")):
                continue
            seen.add(lk.get("id"))
            results.append(
                {
                    "title": lk["title"],
                    "subtitle": lk.get("url", ""),
                    "url": lk.get("url", f"/links?q={query.q}"),
                    "external": bool(lk.get("url")),
                }
            )
    return results


def _search_runbooks(query: Query) -> list[dict]:
    from modules.runbooks.storage import RunbookStorage

    store = query.store("runbooks")
    if not store:
        return []
    return [
        {
            "title": rb["title"],
            "subtitle": rb.get("description", ""),
            "snippet": _highlight(
                rb.get("description", "") + " " + " ".join(s.get("body", "") for s in rb.get("steps", [])),
                query.q,
            ),
            "url": f"/runbooks/{rb['id']}",
        }
        for rb in RunbookStorage(store).list_runbooks(query=query.q)
        if query.in_range(rb.get("created", ""))
    ]


def _search_snippets(query: Query) -> list[dict]:
    from modules.snippets.storage import SnippetStorage

    store = query.store("snippets")
    if not store:
        return []
    return [
        {
            "title": sn["title"],
            "subtitle": sn.get("description", ""),
            "snippet": _highlight(
                sn.get("description", "") + " " + " ".join(s.get("command", "") for s in sn.get("steps", [])),
                query.q,
            ),
            "url": f"/snippets/{sn['id']}",
        }
        for sn in SnippetStorage(store).list_snippets(query=query.q)
        if query.in_range(sn.get("created", ""))
    ]


def _search_mail_templates(query: Query) -> list[dict]:
    from modules.mail_templates.storage import MailTemplateStorage

    store = query.store("mail_templates")
    if not store:
        return []
    return [
        {"title": t["name"], "subtitle": t.get("subject", ""), "url": "/mail-templates"}
        for t in MailTemplateStorage(store).list_templates()
        if query.matches(t, "name", "subject", "body") and query.in_range(t.get("created", ""))
    ]


def _search_ticket_templates(query: Query) -> list[dict]:
    from modules.ticket_templates.storage import TicketTemplateStorage

    store = query.store("ticket_templates")
    if not store:
        return []
    return [
        {"title": t["name"], "subtitle": t.get("description", ""), "url": "/ticket-templates"}
        for t in TicketTemplateStorage(store).list_templates()
        if query.matches(t, "name", "description", "body") and query.in_range(t.get("created", ""))
    ]


def _search_vacations(query: Query) -> list[dict]:
    """Searches the note field; the date filter applies to start_date."""
    from modules.vacations.storage import VacationStorage

    store = query.store("vacations")
    if not store:
        return []
    return [
        {
            "title": f"{v.get('start_date', '')} – {v.get('end_date', '')}",
            "subtitle": v.get("note", "") or v.get("status", ""),
            "url": "/vacations",
        }
        for v in VacationStorage(store).list_entries()
        if query.matches(v, "note", "start_date", "end_date") and query.in_range(v.get("start_date", ""))
    ]


def _search_appointments(query: Query) -> list[dict]:
    from modules.appointments.storage import AppointmentStorage

    store = query.store("appointments")
    if not store:
        return []
    return [
        {"title": a["title"], "subtitle": a.get("start_date", ""), "url": "/appointments"}
        for a in AppointmentStorage(store).list_entries()
        if query.matches(a, "title", "note") and query.in_range(a.get("start_date", ""))
    ]


def _search_eol(query: Query) -> list[dict]:
    """EOL entries carry no creation date, so the date filter does not apply."""
    from modules.eol.storage import EolStorage

    store = query.store("eol")
    if not store:
        return []
    return [
        {
            "title": e.get("label") or f"{e.get('product', '')} {e.get('cycle', '')}",
            "subtitle": e.get("cycle", ""),
            "url": f"/eol/product/{e.get('product', '')}",
        }
        for e in EolStorage(store).list_entries()
        if query.matches(e, "product", "cycle", "label", "notes")
    ]


PROVIDERS: tuple[Provider, ...] = (
    Provider("knowledge", "book-open", "Knowledge", "/knowledge/?q={q}", _search_knowledge),
    Provider("tasks", "check-square-2", "Tasks", "/tasks?q={q}", _search_tasks),
    Provider("notes", "file-text", "Notes", "/notes?q={q}", _search_notes),
    Provider("links", "link-2", "Links", "/links?q={q}", _search_links),
    Provider("runbooks", "list-checks", "Runbooks", "/runbooks?q={q}", _search_runbooks),
    Provider("snippets", "code-2", "Snippets", "/snippets?q={q}", _search_snippets),
    Provider("mail_templates", "mail", "Mail Templates", "/mail-templates", _search_mail_templates),
    Provider("ticket_templates", "ticket", "Ticket Templates", "/ticket-templates", _search_ticket_templates),
    Provider("vacations", "palmtree", "Vacations", "/vacations", _search_vacations),
    Provider("appointments", "calendar-days", "Appointments", "/appointments", _search_appointments),
    Provider("eol", "shield-check", "EOL Tracker", "/eol", _search_eol),
)


def run_global_search(q: str, date_from: str, date_to: str, modules_enabled: dict, storage) -> list[dict]:
    """Return result groups, newest cache first. One failing module logs and is
    left out; it must not take the whole search page down."""
    if not q or storage is None:
        return []

    cache_key = "search:global:" + hashlib.md5(f"{q}|{date_from}|{date_to}".encode()).hexdigest()[:16]
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    query = Query(q=q, date_from=date_from, date_to=date_to, storage=storage)
    groups: list[dict] = []
    for provider in PROVIDERS:
        if not modules_enabled.get(provider.module, True):
            continue
        try:
            results = provider.search(query)
        except Exception as e:
            logger.warning("Global search failed for module '%s': %s", provider.module, e)
            continue
        if not results:
            continue
        groups.append(
            {
                "module": provider.module,
                "icon": provider.icon,
                "label": provider.label,
                "url": provider.url.format(q=q),
                "results": results[:MAX_RESULTS_PER_MODULE],
            }
        )

    if groups:
        cache.set(cache_key, groups, ttl=CACHE_TTL_SECONDS)
    return groups
