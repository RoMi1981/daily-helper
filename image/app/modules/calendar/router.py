"""Central calendar module — aggregates vacations, appointments and public holidays."""

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from core import settings_store
from core.module_repos import get_primary_store
from core.state import get_storage
from core.templates import templates

router = APIRouter(prefix="/calendar")

_APPT_TYPE_ICONS = {
    "training": "book-open",
    "conference": "mic",
    "team_event": "users",
    "business_trip": "plane",
    "other": "calendar",
}
_APPT_TYPE_LABELS = {
    "training": "Training",
    "conference": "Conference",
    "team_event": "Team Event",
    "business_trip": "Business Trip",
    "other": "Other",
}
ALL_APPT_TYPES = list(_APPT_TYPE_ICONS.keys())


def _sprint_anchor(cfg: dict) -> "date | None":
    raw = cfg.get("sprint_anchor_date", "")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _load_entries(cfg: dict, storage, year: int) -> tuple[list, list, list]:
    """Load vac, appt and task entries. Returns (vac_entries, appt_entries, task_entries)."""
    modules = cfg.get("modules_enabled", {})
    vac_entries: list[dict] = []
    if modules.get("vacations", True) and storage:
        vac_store = get_primary_store("vacations", storage)
        if vac_store:
            try:
                from modules.vacations.storage import VacationStorage

                vac_entries = VacationStorage(vac_store).list_entries(year)
            except Exception:
                pass

    appt_entries: list[dict] = []
    if modules.get("appointments", True) and storage:
        appt_store = get_primary_store("appointments", storage)
        if appt_store:
            try:
                from modules.appointments.storage import AppointmentStorage

                appt_entries = AppointmentStorage(appt_store).list_entries(year)
            except Exception:
                pass

    task_entries: list[dict] = []
    if modules.get("tasks", True) and storage:
        for s in storage._stores.values():
            try:
                from modules.tasks.storage import TaskStorage

                task_entries.extend(TaskStorage(s).list_tasks())
            except Exception:
                pass

    return vac_entries, appt_entries, task_entries


@router.get("", response_class=HTMLResponse)
async def calendar_view(request: Request, year: int = 0, month: int = 0):
    from modules.vacations.holidays_helper import get_calendar_data

    today = date.today()
    if not year:
        year = today.year
    if not month:
        month = today.month

    cfg = settings_store.load()
    state = cfg.get("vacation_state", "BY")
    language = cfg.get("holiday_language", "de")
    modules = cfg.get("modules_enabled", {})
    storage = get_storage()

    vac_entries, appt_entries, task_entries = _load_entries(cfg, storage, year)

    anchor = _sprint_anchor(cfg)
    prefix = cfg.get("sprint_name_prefix", "PFM Sprint")
    duration_weeks = int(cfg.get("sprint_duration_weeks", 3))

    show_weekends = cfg.get("calendar_show_weekends", True)
    cal = get_calendar_data(
        year,
        month,
        state,
        vac_entries,
        language,
        appointment_entries=appt_entries,
        task_entries=task_entries,
        sprint_anchor=anchor,
        sprint_prefix=prefix,
        sprint_duration_weeks=duration_weeks,
    )

    # Current sprint info for header
    current_sprint = None
    if anchor:
        from modules.calendar.sprint_helper import get_sprint_for_date

        current_sprint = get_sprint_for_date(today, anchor, prefix, duration_weeks)

    categories = storage.get_categories() if storage else []

    return templates.TemplateResponse(
        request,
        "modules/calendar/index.html",
        {
            "cal": cal,
            "vac_entries": vac_entries,
            "appt_entries": appt_entries,
            "task_entries": task_entries,
            "categories": categories,
            "active_module": "calendar",
            "show_vacations": modules.get("vacations", True),
            "show_appointments": modules.get("appointments", True),
            "sprint_configured": anchor is not None,
            "current_sprint": current_sprint,
            "type_icons": _APPT_TYPE_ICONS,
            "show_weekends": show_weekends,
            "holiday_ics_profiles": settings_store.get_holiday_ics_profiles(),
        },
    )


@router.get("/capacity", response_class=HTMLResponse)
async def capacity_view(request: Request, year: int = 0):
    today = date.today()
    if not year:
        year = today.year

    cfg = settings_store.load()
    anchor = _sprint_anchor(cfg)
    if not anchor:
        return RedirectResponse("/settings?saved=0#sprints", status_code=303)

    prefix = cfg.get("sprint_name_prefix", "PFM Sprint")
    duration_weeks = int(cfg.get("sprint_duration_weeks", 3))
    state = cfg.get("vacation_state", "BY")
    blocked_types = cfg.get("sprint_blocked_appointment_types", [])
    modules = cfg.get("modules_enabled", {})
    storage = get_storage()

    vac_entries, appt_entries, _ = _load_entries(cfg, storage, year)
    # Also load adjacent year entries for sprints that straddle year boundaries
    vac_prev, appt_prev, _ = _load_entries(cfg, storage, year - 1)
    vac_next, appt_next, _ = _load_entries(cfg, storage, year + 1)
    all_vac = vac_prev + vac_entries + vac_next
    all_appt = appt_prev + appt_entries + appt_next

    from modules.calendar.sprint_helper import get_sprints_in_year, capacity_for_sprint

    sprints_raw = get_sprints_in_year(year, anchor, prefix, duration_weeks)
    sprints = [
        capacity_for_sprint(sp, all_vac, all_appt, blocked_types, state, today=today)
        for sp in sprints_raw
    ]

    categories = storage.get_categories() if storage else []

    return templates.TemplateResponse(
        request,
        "modules/calendar/capacity.html",
        {
            "sprints": sprints,
            "year": year,
            "prev_year": year - 1,
            "next_year": year + 1,
            "today": today,
            "blocked_types": blocked_types,
            "type_labels": _APPT_TYPE_LABELS,
            "type_icons": _APPT_TYPE_ICONS,
            "categories": categories,
            "active_module": "calendar",
            "show_vacations": modules.get("vacations", True),
            "show_appointments": modules.get("appointments", True),
        },
    )


@router.get("/holiday.ics")
async def export_holiday_ics(date: str = "", name: str = "", profile: str = ""):
    from modules.vacations.ics_generator import generate_holiday_ics, holiday_profile_filename

    if not date or not name or not profile:
        raise HTTPException(status_code=400, detail="date, name and profile are required")
    profile_obj = settings_store.get_holiday_ics_profile(profile)
    if not profile_obj:
        raise HTTPException(status_code=404, detail="Holiday ICS profile not found")
    content = generate_holiday_ics(name, date, profile_obj)
    filename = holiday_profile_filename(profile_obj, date, name)
    return Response(
        content=content,
        media_type="text/calendar",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Redirects from old module calendars ────────────────────────────────────


@router.get("/vacations-redirect")
async def vacations_calendar_redirect(year: int = 0, month: int = 0):
    params = []
    if year:
        params.append(f"year={year}")
    if month:
        params.append(f"month={month}")
    qs = "?" + "&".join(params) if params else ""
    return RedirectResponse(f"/calendar{qs}", status_code=301)
