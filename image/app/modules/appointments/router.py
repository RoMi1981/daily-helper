"""Appointments module — router for whole-day appointment management."""

import logging
from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from core import settings_store
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.appointments.storage import AppointmentStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", dependencies=[require_module("appointments")])

APPT_TYPES = [
    ("training", "📚 Training"),
    ("conference", "🎙 Conference"),
    ("team_event", "👥 Team Event"),
    ("business_trip", "✈️ Business Trip"),
    ("other", "📌 Other"),
]

TYPE_ICONS = {
    "training": "graduation-cap",
    "conference": "mic",
    "team_event": "users",
    "business_trip": "plane",
    "other": "calendar",
}


def _get_appointment_storage() -> AppointmentStorage | None:
    """Primary storage — used only for creating new appointments."""
    store = get_primary_store("appointments", get_storage())
    return AppointmentStorage(store) if store else None


def _get_all_storages() -> list[AppointmentStorage]:
    return [AppointmentStorage(s) for s in get_module_stores("appointments", get_storage())]


def _find_storage(entry_id: str) -> AppointmentStorage | None:
    for aps in _get_all_storages():
        if aps.get_entry(entry_id):
            return aps
    return None


@router.get("", response_class=HTMLResponse)
async def appointment_list(request: Request, year: int = 0):
    storage = get_storage()
    categories = storage.get_categories() if storage else []
    if not year:
        year = date.today().year

    seen: set[str] = set()
    entries: list[dict] = []
    for aps in _get_all_storages():
        for e in aps.list_entries(year):
            if e["id"] not in seen:
                seen.add(e["id"])
                entries.append(e)

    ics_profiles = settings_store.get_appointment_ics_profiles()
    return templates.TemplateResponse(
        request,
        "modules/appointments/list.html",
        {
            "entries": entries,
            "year": year,
            "categories": categories,
            "active_module": "appointments",
            "configured": bool(_get_all_storages()),
            "today": date.today().isoformat(),
            "appt_types": APPT_TYPES,
            "type_icons": TYPE_ICONS,
            "ics_profiles": ics_profiles,
        },
    )


@router.get("/{entry_id}/export.ics")
async def export_ics(entry_id: str, profile: str = ""):
    from modules.appointments.ics_generator import generate_ics, profile_filename

    stores = _get_all_storages()
    if not stores:
        raise HTTPException(status_code=503, detail="No repository configured")
    entry = None
    for aps in stores:
        entry = aps.get_entry(entry_id)
        if entry:
            break
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if profile:
        profile_obj = settings_store.get_appointment_ics_profile(profile)
        if not profile_obj:
            raise HTTPException(status_code=404, detail="Profile not found")
        content = generate_ics(entry, profile_obj)
        filename = profile_filename(profile_obj, entry)
    else:
        content = generate_ics(
            entry,
            {"show_as": "busy", "all_day": True, "subject": "{title} {start_date}–{end_date}"},
        )
        filename = f"appointment-{entry_id}.ics"

    return Response(
        content=content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/calendar")
async def appointment_calendar(year: int = 0, month: int = 0):
    params = []
    if year:
        params.append(f"year={year}")
    if month:
        params.append(f"month={month}")
    qs = "?" + "&".join(params) if params else ""
    return RedirectResponse(f"/calendar{qs}", status_code=301)


@router.post("", response_class=RedirectResponse)
async def create_appointment(
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    type: str = Form("other"),
    note: str = Form(""),
    recurring: str = Form("none"),
):
    aps = _get_appointment_storage()
    if not aps:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title required")
    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="Start and end date required")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    aps.create_entry(
        {
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "type": type,
            "note": note,
            "recurring": recurring,
        }
    )
    return RedirectResponse("/appointments", status_code=303)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
async def edit_appointment_form(request: Request, entry_id: str):
    entry = None
    for aps in _get_all_storages():
        entry = aps.get_entry(entry_id)
        if entry:
            break
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    storage = get_storage()
    categories = storage.get_categories() if storage else []
    return templates.TemplateResponse(
        request,
        "modules/appointments/form.html",
        {
            "entry": entry,
            "categories": categories,
            "active_module": "appointments",
            "appt_types": APPT_TYPES,
        },
    )


@router.post("/{entry_id}/edit", response_class=RedirectResponse)
async def update_appointment(
    entry_id: str,
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    type: str = Form("other"),
    note: str = Form(""),
    recurring: str = Form("none"),
):
    aps = _find_storage(entry_id)
    if not aps:
        raise HTTPException(status_code=404, detail="Entry not found")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    entry = aps.update_entry(
        entry_id,
        {
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "type": type,
            "note": note,
            "recurring": recurring,
        },
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse("/appointments", status_code=303)


@router.post("/{entry_id}/delete", response_class=RedirectResponse)
async def delete_appointment(entry_id: str):
    aps = _find_storage(entry_id)
    if not aps:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not aps.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse("/appointments", status_code=303)
