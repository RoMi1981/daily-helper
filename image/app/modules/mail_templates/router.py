"""Mail Templates module — router."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.mail_templates.storage import MailTemplateStorage

router = APIRouter(prefix="/mail-templates", dependencies=[require_module("mail_templates")])


def _get_storage() -> MailTemplateStorage | None:
    """Primary storage — used only for creating new templates."""
    store = get_primary_store("mail_templates", get_storage())
    return MailTemplateStorage(store) if store else None


def _get_all_storages() -> list[MailTemplateStorage]:
    return [MailTemplateStorage(s) for s in get_module_stores("mail_templates", get_storage())]


def _find_storage(template_id: str) -> MailTemplateStorage | None:
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
        "modules/mail_templates/list.html",
        {
            "templates": templates_list,
            "configured": bool(_get_all_storages()),
            "active_module": "mail_templates",
            "saved": saved,
            "error": error,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_template_form(request: Request):
    return templates.TemplateResponse(
        request,
        "modules/mail_templates/form.html",
        {
            "template": None,
            "active_module": "mail_templates",
        },
    )


@router.post("/new")
async def create_template(
    name: str = Form(...),
    to: str = Form(""),
    cc: str = Form(""),
    subject: str = Form(""),
    body: str = Form(""),
):
    ts = _get_storage()
    if not ts:
        raise HTTPException(status_code=503, detail="Storage not configured")
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name required")
    ts.create_template({"name": name, "to": to, "cc": cc, "subject": subject, "body": body})
    return RedirectResponse("/mail-templates?saved=1", status_code=303)


@router.get("/{template_id}/edit", response_class=HTMLResponse)
async def edit_form(template_id: str, request: Request):
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404)
    t = ts.get_template(template_id)
    return templates.TemplateResponse(
        request,
        "modules/mail_templates/form.html",
        {
            "template": t,
            "active_module": "mail_templates",
        },
    )


@router.post("/{template_id}/edit")
async def update_template(
    template_id: str,
    name: str = Form(...),
    to: str = Form(""),
    cc: str = Form(""),
    subject: str = Form(""),
    body: str = Form(""),
):
    if not _get_all_storages():
        raise HTTPException(status_code=503, detail="No repository configured")
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404)
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name required")
    if not ts.update_template(
        template_id, {"name": name, "to": to, "cc": cc, "subject": subject, "body": body}
    ):
        raise HTTPException(status_code=404)
    return RedirectResponse("/mail-templates?saved=1", status_code=303)


@router.get("/{template_id}/download.eml")
async def download_eml(template_id: str):
    t = None
    for ts in _get_all_storages():
        t = ts.get_template(template_id)
        if t:
            break
    if not t:
        raise HTTPException(status_code=404)
    lines = []
    if t.get("to"):
        lines.append(f"To: {t['to']}")
    if t.get("cc"):
        lines.append(f"CC: {t['cc']}")
    if t.get("subject"):
        lines.append(f"Subject: {t['subject']}")
    lines.append("MIME-Version: 1.0")
    lines.append("Content-Type: text/plain; charset=utf-8")
    lines.append("")
    lines.append(t.get("body", ""))
    eml_content = "\r\n".join(lines)
    safe_name = "".join(
        c if (c.isascii() and c.isalnum()) or c in " -_" else "_" for c in t["name"]
    ).strip()
    filename = f"{safe_name}.eml"
    return Response(
        content=eml_content.encode("utf-8"),
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{template_id}/history", response_class=HTMLResponse)
async def template_history(request: Request, template_id: str):
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Template not found")
    tpl = ts.get_template(template_id)
    path = f"mail_templates/{template_id}.yaml"
    commits = ts._git.get_file_history(path)
    sha = request.query_params.get("sha")
    diff = ts._git.get_file_diff(sha, path) if sha else None
    return templates.TemplateResponse(
        request,
        "modules/mail_templates/history.html",
        {
            "item": tpl,
            "item_title": tpl.get("name", template_id),
            "back_url": "/mail-templates",
            "commits": commits,
            "diff": diff,
            "selected_sha": sha,
            "active_module": "mail_templates",
        },
    )


@router.post("/{template_id}/delete")
async def delete_template(template_id: str):
    if not _get_all_storages():
        raise HTTPException(status_code=503, detail="No repository configured")
    ts = _find_storage(template_id)
    if not ts:
        raise HTTPException(status_code=404)
    ts.delete_template(template_id)
    return RedirectResponse("/mail-templates", status_code=303)
