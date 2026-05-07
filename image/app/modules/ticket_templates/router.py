"""Ticket Templates module — router."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.ticket_templates.storage import TicketTemplateStorage

router = APIRouter(prefix="/ticket-templates", dependencies=[require_module("ticket_templates")])


def _get_storage() -> TicketTemplateStorage | None:
    """Primary storage — used only for creating new templates."""
    store = get_primary_store("ticket_templates", get_storage())
    return TicketTemplateStorage(store) if store else None


def _get_all_storages() -> list[TicketTemplateStorage]:
    return [TicketTemplateStorage(s) for s in get_module_stores("ticket_templates", get_storage())]


def _find_storage(template_id: str) -> TicketTemplateStorage | None:
    for ts in _get_all_storages():
        if ts.get_template(template_id):
            return ts
    return None


@router.get("", response_class=HTMLResponse)
async def list_templates(request: Request, saved: str = "", error: str = ""):
    seen: set[str] = set()
    templates_list: list[dict] = []
    for ts in _get_all_storages():
        for t in ts.list_templates():
            if t["id"] not in seen:
                seen.add(t["id"])
                templates_list.append(t)
    return templates.TemplateResponse(
        request,
        "modules/ticket_templates/list.html",
        {
            "templates": templates_list,
            "configured": bool(_get_all_storages()),
            "active_module": "ticket_templates",
            "saved": saved,
            "error": error,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_template_form(request: Request):
    return templates.TemplateResponse(
        request,
        "modules/ticket_templates/form.html",
        {
            "template": None,
            "active_module": "ticket_templates",
        },
    )


@router.post("/new")
async def create_template(
    name: str = Form(...),
    description: str = Form(""),
    body: str = Form(""),
):
    ts = _get_storage()
    if not ts:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name required")
    ts.create_template({"name": name, "description": description, "body": body})
    return RedirectResponse("/ticket-templates?saved=1", status_code=303)


@router.get("/{template_id}/edit", response_class=HTMLResponse)
async def edit_form(template_id: str, request: Request):
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404)
    t = ts.get_template(template_id)
    return templates.TemplateResponse(
        request,
        "modules/ticket_templates/form.html",
        {
            "template": t,
            "active_module": "ticket_templates",
        },
    )


@router.post("/{template_id}/edit")
async def update_template(
    template_id: str,
    name: str = Form(...),
    description: str = Form(""),
    body: str = Form(""),
):
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404)
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name required")
    if not ts.update_template(
        template_id, {"name": name, "description": description, "body": body}
    ):
        raise HTTPException(status_code=404)
    return RedirectResponse("/ticket-templates?saved=1", status_code=303)


@router.get("/{template_id}/history", response_class=HTMLResponse)
async def template_history(request: Request, template_id: str):
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Template not found")
    tpl = ts.get_template(template_id)
    path = f"ticket_templates/{template_id}.yaml"
    commits = ts._git.get_file_history(path)
    sha = request.query_params.get("sha")
    diff = ts._git.get_file_diff(sha, path) if sha else None
    return templates.TemplateResponse(
        request,
        "modules/ticket_templates/history.html",
        {
            "item": tpl,
            "item_title": tpl.get("name", template_id),
            "back_url": "/ticket-templates",
            "commits": commits,
            "diff": diff,
            "selected_sha": sha,
            "active_module": "ticket_templates",
        },
    )


@router.post("/{template_id}/delete")
async def delete_template(template_id: str):
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404)
    ts.delete_template(template_id)
    return RedirectResponse("/ticket-templates", status_code=303)
