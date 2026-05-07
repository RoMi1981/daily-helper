"""Vacations module — router for vacation management."""

import html as _html
import logging
import re
from datetime import date, timedelta

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from core import settings_store
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.vacations.storage import VacationStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vacations", dependencies=[require_module("vacations")])

_TAG_RE = re.compile(r"\[/?[biu]\]", re.IGNORECASE)
_FORMAT_MAP = [
    (re.compile(r"\[b\](.*?)\[/b\]", re.DOTALL | re.IGNORECASE), r"<strong>\1</strong>"),
    (re.compile(r"\[i\](.*?)\[/i\]", re.DOTALL | re.IGNORECASE), r"<em>\1</em>"),
    (re.compile(r"\[u\](.*?)\[/u\]", re.DOTALL | re.IGNORECASE), r"<u>\1</u>"),
]


def _body_to_html(text: str) -> str:
    """Convert [b]/[i]/[u] tags to HTML, newlines to <br>. HTML-escaped."""
    text = _html.escape(text)
    for pattern, repl in _FORMAT_MAP:
        # unescape the tag markers after escaping (they don't contain HTML)
        text = pattern.sub(repl, text)
    return text.replace("\n", "<br>\n")


def _body_to_plain(text: str) -> str:
    """Strip [b]/[i]/[u] tags for plain text (mailto, clipboard)."""
    return _TAG_RE.sub("", text)


def _get_vacation_storage() -> VacationStorage | None:
    """Primary storage — used only for creating new entries."""
    store = get_primary_store("vacations", get_storage())
    return VacationStorage(store) if store else None


def _get_all_storages() -> list[VacationStorage]:
    return [VacationStorage(s) for s in get_module_stores("vacations", get_storage())]


def _find_storage(entry_id: str) -> VacationStorage | None:
    for vs in _get_all_storages():
        if vs.get_entry(entry_id):
            return vs
    return None


def _list_all_entries(year: int | None = None) -> list[dict]:
    seen: set[str] = set()
    entries: list[dict] = []
    for vs in _get_all_storages():
        for e in vs.list_entries(year):
            if e["id"] not in seen:
                seen.add(e["id"])
                entries.append(e)
    return entries


def _vacation_settings() -> tuple[str, float]:
    cfg = settings_store.load()
    total = int(cfg.get("vacation_days_per_year", 30)) + float(cfg.get("vacation_carryover", 0))
    # Use int when no fractional part (avoids displaying "30.0")
    if total == int(total):
        total = int(total)
    return cfg.get("vacation_state", "BY"), total


def _days_until_next_vacation(all_entries: list[dict], state: str, today: date) -> tuple:
    """Return (days_until_next, next_vacation_entry) or (None, None) if no future vacation."""
    from modules.vacations.holidays_helper import count_work_days

    future = [e for e in all_entries if e.get("start_date", "") >= today.isoformat()]
    if not future:
        return None, None
    next_vac = min(future, key=lambda e: e["start_date"])
    day_before = (date.fromisoformat(next_vac["start_date"]) - timedelta(days=1)).isoformat()
    days = (
        count_work_days(today.isoformat(), day_before, state)
        if day_before >= today.isoformat()
        else 0
    )
    return days, next_vac


@router.get("", response_class=HTMLResponse)
async def vacation_list(request: Request, year: int = 0):
    vs = _get_vacation_storage()
    storage = get_storage()
    categories = storage.get_categories() if storage else []
    state, total_days = _vacation_settings()
    today = date.today()
    if not year:
        year = today.year

    all_entries = _list_all_entries(year)
    if vs:
        account = vs.get_account(year, total_days, state, entries=all_entries)
    else:
        account = {
            "year": year,
            "total_days": total_days,
            "used_days": 0,
            "planned_days": 0,
            "remaining_days": total_days,
            "entries": [],
        }

    ics_profiles = settings_store.get_ics_profiles()
    cfg = settings_store.load()
    mail_configured = bool(cfg.get("vacation_mail_to") or cfg.get("vacation_mail_subject"))
    all_entries_no_year = _list_all_entries()
    days_until_next, next_vacation = (
        _days_until_next_vacation(all_entries_no_year, state, today)
        if _get_all_storages()
        else (None, None)
    )

    return templates.TemplateResponse(
        request,
        "modules/vacations/list.html",
        {
            "account": account,
            "categories": categories,
            "active_module": "vacations",
            "configured": vs is not None,
            "today": today.isoformat(),
            "ics_profiles": ics_profiles,
            "mail_configured": mail_configured,
            "days_until_next": days_until_next,
            "next_vacation": next_vacation,
        },
    )


@router.get("/calendar")
async def vacation_calendar(year: int = 0, month: int = 0):
    params = []
    if year:
        params.append(f"year={year}")
    if month:
        params.append(f"month={month}")
    qs = "?" + "&".join(params) if params else ""
    return RedirectResponse(f"/calendar{qs}", status_code=301)


@router.get("/{entry_id}/mail", response_class=HTMLResponse)
async def vacation_mail(request: Request, entry_id: str):
    vs = _find_storage(entry_id)
    if not vs:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = vs.get_entry(entry_id)

    cfg = settings_store.load()
    state, _ = _vacation_settings()

    from modules.vacations.holidays_helper import count_work_days

    try:
        working_days = count_work_days(entry["start_date"], entry["end_date"], state)
    except Exception:
        working_days = "?"

    def _fill(tmpl: str) -> str:
        return (
            tmpl.replace("{{from}}", entry["start_date"])
            .replace("{{to}}", entry["end_date"])
            .replace("{{working_days}}", str(working_days))
        )

    raw_body = _fill(cfg.get("vacation_mail_body", ""))
    return templates.TemplateResponse(
        request,
        "modules/vacations/mail.html",
        {
            "entry": entry,
            "mail_to": cfg.get("vacation_mail_to", ""),
            "mail_cc": cfg.get("vacation_mail_cc", ""),
            "mail_subject": _fill(cfg.get("vacation_mail_subject", "")),
            "mail_body_html": _body_to_html(raw_body),
            "mail_body_plain": _body_to_plain(raw_body),
            "working_days": working_days,
            "active_module": "vacations",
        },
    )


@router.get("/{entry_id}/mail.eml")
async def vacation_mail_eml(entry_id: str):
    from email.message import EmailMessage

    vs = _find_storage(entry_id)
    if not vs:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = vs.get_entry(entry_id)

    cfg = settings_store.load()
    state, _ = _vacation_settings()

    from modules.vacations.holidays_helper import count_work_days

    try:
        working_days = count_work_days(entry["start_date"], entry["end_date"], state)
    except Exception:
        working_days = "?"

    def _fill(tmpl: str) -> str:
        return (
            tmpl.replace("{{from}}", entry["start_date"])
            .replace("{{to}}", entry["end_date"])
            .replace("{{working_days}}", str(working_days))
        )

    msg = EmailMessage()
    mail_to = cfg.get("vacation_mail_to", "")
    mail_cc = cfg.get("vacation_mail_cc", "")
    if mail_to:
        msg["To"] = mail_to
    if mail_cc:
        msg["CC"] = mail_cc
    msg["Subject"] = _fill(cfg.get("vacation_mail_subject", ""))
    raw_body = _fill(cfg.get("vacation_mail_body", ""))
    html_body = f"<html><body>{_body_to_html(raw_body)}</body></html>"
    plain_body = _body_to_plain(raw_body)
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    filename = f"vacation-{entry['start_date']}-{entry['end_date']}.eml"
    from fastapi.responses import Response as FastAPIResponse

    return FastAPIResponse(
        content=msg.as_bytes(),
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{entry_id}/export.ics")
async def export_ics(entry_id: str, profile: str = ""):
    from datetime import datetime, timedelta, timezone
    from modules.vacations.ics_generator import generate_ics, profile_filename

    vs = _find_storage(entry_id)
    if not vs:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = vs.get_entry(entry_id)

    # With profile: use configured export profile
    if profile:
        profile_obj = settings_store.get_ics_profile(profile)
        if not profile_obj:
            raise HTTPException(status_code=404, detail="ICS profile not found")
        state, _ = _vacation_settings()
        content = generate_ics(entry, profile_obj, state)
        filename = profile_filename(profile_obj, entry)
        return Response(
            content=content,
            media_type="text/calendar",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # Fallback: generic single all-day event (original behavior)
    start = entry["start_date"]
    end_dt = date.fromisoformat(entry["end_date"]) + timedelta(days=1)
    end = end_dt.strftime("%Y-%m-%d")
    note = entry.get("note", "") or "Vacation"
    uid = f"{entry_id}@daily-helper"
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstart = start.replace("-", "")
    dtend = end.replace("-", "")

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Daily Helper//Vacation//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{now}\r\n"
        f"DTSTART;VALUE=DATE:{dtstart}\r\n"
        f"DTEND;VALUE=DATE:{dtend}\r\n"
        f"SUMMARY:Vacation – {note}\r\n"
        f"DESCRIPTION:{note}\r\n"
        "TRANSP:OPAQUE\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": f"attachment; filename=vacation-{entry_id}.ics"},
    )


@router.get("/export.csv")
async def export_csv(year: int = 0):
    from modules.vacations.holidays_helper import count_work_days
    import io, csv as csv_mod

    state, total_days = _vacation_settings()
    if not year:
        year = date.today().year
    entries = _list_all_entries(year)
    buf = io.StringIO()
    w = csv_mod.writer(buf)
    w.writerow(["id", "start_date", "end_date", "status", "work_days", "note"])
    for e in sorted(entries, key=lambda x: x.get("start_date", "")):
        try:
            work_days = count_work_days(e["start_date"], e["end_date"], state)
        except Exception:
            work_days = ""
        w.writerow(
            [
                e["id"],
                e["start_date"],
                e["end_date"],
                e.get("status", ""),
                work_days,
                e.get("note", ""),
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=vacations-{year}.csv"},
    )


@router.post("", response_class=RedirectResponse)
async def create_vacation(
    start_date: str = Form(...),
    end_date: str = Form(...),
    note: str = Form(""),
):
    vs = _get_vacation_storage()
    if not vs:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="Start and end date required")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    vs.create_entry({"start_date": start_date, "end_date": end_date, "note": note})
    return RedirectResponse("/vacations", status_code=303)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
async def edit_vacation_form(request: Request, entry_id: str):
    vs = _find_storage(entry_id)
    if not vs:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = vs.get_entry(entry_id)
    storage = get_storage()
    categories = storage.get_categories() if storage else []
    return templates.TemplateResponse(
        request,
        "modules/vacations/form.html",
        {
            "entry": entry,
            "categories": categories,
            "active_module": "vacations",
        },
    )


@router.post("/{entry_id}/edit", response_class=RedirectResponse)
async def update_vacation(
    entry_id: str,
    start_date: str = Form(...),
    end_date: str = Form(...),
    note: str = Form(""),
):
    vs = _find_storage(entry_id)
    if not vs:
        raise HTTPException(status_code=404, detail="Entry not found")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    entry = vs.update_entry(
        entry_id, {"start_date": start_date, "end_date": end_date, "note": note}
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse("/vacations", status_code=303)


@router.post("/{entry_id}/status", response_class=HTMLResponse)
async def update_vacation_status(request: Request, entry_id: str, status: str = Form(...)):
    vs = _find_storage(entry_id)
    if not vs:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = vs.update_status(entry_id, status)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    state, total_days = _vacation_settings()
    year = int(entry["start_date"][:4])
    all_entries = _list_all_entries(year)
    primary_vs = _get_vacation_storage() or vs
    account = primary_vs.get_account(year, total_days, state, entries=all_entries)
    storage_ref = get_storage()
    categories = storage_ref.get_categories() if storage_ref else []
    ics_profiles = settings_store.get_ics_profiles()
    today = date.today()
    all_entries_no_year = _list_all_entries()
    days_until_next, next_vacation = _days_until_next_vacation(all_entries_no_year, state, today)
    return templates.TemplateResponse(
        request,
        "modules/vacations/list.html",
        {
            "account": account,
            "categories": categories,
            "active_module": "vacations",
            "configured": True,
            "today": today.isoformat(),
            "ics_profiles": ics_profiles,
            "days_until_next": days_until_next,
            "next_vacation": next_vacation,
        },
    )


@router.post("/{entry_id}/delete", response_class=RedirectResponse)
async def delete_vacation(entry_id: str):
    vs = _find_storage(entry_id)
    if not vs:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not vs.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse("/vacations", status_code=303)
