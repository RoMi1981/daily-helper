"""Operations module — copy/move content between repositories."""

import io
import logging
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from core import settings_store
from core.state import get_storage
from core.storage import GitStorageError
from core.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/operations")


# ── Helpers ────────────────────────────────────────────────────────────────


def _repo_name(cfg: dict, repo_id: str) -> str:
    for r in cfg.get("repos", []):
        if r["id"] == repo_id:
            return r.get("name", repo_id)
    return repo_id


def _list_files_for_ops(entries: list[dict]) -> list[dict]:
    """Normalize media entries for the operations UI (need 'id' and 'title')."""
    for e in entries:
        if "title" not in e:
            e["title"] = f"{e['id']}.{e.get('ext', '')}"
    return entries


def _get_items(storage, src_id: str, content_type: str) -> list[dict]:
    """Return items from the source repo for the given content type."""
    store = storage._stores.get(src_id)
    if not store:
        return []
    try:
        if content_type == "knowledge":
            entries = store.get_entries()
            # Group by category for template
            by_cat: dict[str, list] = {}
            for e in entries:
                by_cat.setdefault(e.get("category", ""), []).append(e)
            return [{"category": cat, "entries": items} for cat, items in sorted(by_cat.items())]
        elif content_type == "tasks":
            from modules.tasks.storage import TaskStorage

            return TaskStorage(store).list_tasks()
        elif content_type == "vacations":
            from modules.vacations.storage import VacationStorage

            return VacationStorage(store).list_entries()
        elif content_type == "mail_templates":
            from modules.mail_templates.storage import MailTemplateStorage

            return MailTemplateStorage(store).list_templates()
        elif content_type == "ticket_templates":
            from modules.ticket_templates.storage import TicketTemplateStorage

            return TicketTemplateStorage(store).list_templates()
        elif content_type == "notes":
            from modules.notes.storage import NoteStorage

            return NoteStorage(store).list_notes()
        elif content_type == "links":
            from modules.links.storage import LinkStorage

            return LinkStorage(store, "default").list_links()
        elif content_type == "runbooks":
            from modules.runbooks.storage import RunbookStorage

            return RunbookStorage(store).list_runbooks()
        elif content_type == "snippets":
            from modules.snippets.storage import SnippetStorage

            return SnippetStorage(store).list_snippets()
        elif content_type == "appointments":
            from modules.appointments.storage import AppointmentStorage

            return AppointmentStorage(store).list_entries()
        elif content_type == "motd":
            from modules.motd.storage import MotdStorage

            return MotdStorage(store).list_entries()
        elif content_type == "rss":
            from modules.rss.storage import RssStorage

            return RssStorage(store).list_feeds()
        elif content_type == "potd":
            from modules.potd.router import _list_files as _list_potd

            return _list_files_for_ops(_list_potd(store))
        elif content_type == "memes":
            from modules.memes.router import _list_files as _list_memes

            return _list_files_for_ops(_list_memes(store))
    except Exception as e:
        logger.warning("Failed to list items for %s/%s: %s", src_id, content_type, e)
    return []


def _do_copy_move(
    storage, src_id: str, dst_id: str, content_type: str, item_ids: list[str], action: str
) -> tuple[int, list[str]]:
    """
    Copy or move items between repos.
    Returns (count_ok, errors).
    """
    src_store = storage._stores.get(src_id)
    dst_store = storage._stores.get(dst_id)
    if not src_store or not dst_store:
        return 0, ["Source or target repo not available"]

    errors: list[str] = []
    copied = 0

    try:
        dst_store._pull()
    except Exception as e:
        return 0, [f"Failed to sync target repo: {e}"]

    if content_type == "knowledge":
        for item_id in item_ids:
            try:
                parts = item_id.split("/", 1)
                if len(parts) != 2:
                    continue
                category, slug = parts
                src_file = src_store.knowledge_path / category / f"{slug}.md"
                dst_file = dst_store.knowledge_path / category / f"{slug}.md"
                if not src_file.exists():
                    errors.append(f"Not found: {category}/{slug}")
                    continue
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            except Exception as e:
                errors.append(f"{item_id}: {e}")

    elif content_type == "tasks":
        for task_id in item_ids:
            try:
                src_file = Path(src_store.local_path) / "tasks" / f"{task_id}.yaml"
                dst_file = Path(dst_store.local_path) / "tasks" / f"{task_id}.yaml"
                if not src_file.exists():
                    errors.append(f"Task not found: {task_id}")
                    continue
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            except Exception as e:
                errors.append(f"{task_id}: {e}")

    elif content_type == "vacations":
        for entry_id in item_ids:
            try:
                src_file = Path(src_store.local_path) / "vacations" / "entries" / f"{entry_id}.yaml"
                dst_file = Path(dst_store.local_path) / "vacations" / "entries" / f"{entry_id}.yaml"
                if not src_file.exists():
                    errors.append(f"Entry not found: {entry_id}")
                    continue
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            except Exception as e:
                errors.append(f"{entry_id}: {e}")

    elif content_type == "appointments":
        for entry_id in item_ids:
            try:
                src_file = (
                    Path(src_store.local_path) / "appointments" / "entries" / f"{entry_id}.yaml"
                )
                dst_file = (
                    Path(dst_store.local_path) / "appointments" / "entries" / f"{entry_id}.yaml"
                )
                if not src_file.exists():
                    errors.append(f"Appointment not found: {entry_id}")
                    continue
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            except Exception as e:
                errors.append(f"{entry_id}: {e}")

    elif content_type == "links":
        for item_id in item_ids:
            try:
                src_file = Path(src_store.local_path) / "links" / "default" / f"{item_id}.yaml"
                dst_file = Path(dst_store.local_path) / "links" / "default" / f"{item_id}.yaml"
                if not src_file.exists():
                    errors.append(f"Link not found: {item_id}")
                    continue
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            except Exception as e:
                errors.append(f"{item_id}: {e}")

    elif content_type in (
        "mail_templates",
        "ticket_templates",
        "notes",
        "runbooks",
        "snippets",
        "motd",
        "rss",
    ):
        subdir = content_type
        for item_id in item_ids:
            try:
                src_file = Path(src_store.local_path) / subdir / f"{item_id}.yaml"
                dst_file = Path(dst_store.local_path) / subdir / f"{item_id}.yaml"
                if not src_file.exists():
                    errors.append(f"Template not found: {item_id}")
                    continue
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            except Exception as e:
                errors.append(f"{item_id}: {e}")

    elif content_type in ("potd", "memes"):
        subdir = content_type
        for item_id in item_ids:
            try:
                src_dir = Path(src_store.local_path) / subdir
                dst_dir = Path(dst_store.local_path) / subdir
                dst_dir.mkdir(parents=True, exist_ok=True)
                # Copy all files matching this stem (binary + optional sidecar)
                matched = list(src_dir.glob(f"{item_id}.*"))
                if not matched:
                    errors.append(f"Entry not found: {item_id}")
                    continue
                for f in matched:
                    shutil.copy2(f, dst_dir / f.name)
                copied += 1
            except Exception as e:
                errors.append(f"{item_id}: {e}")

    if copied == 0:
        return 0, errors or ["Nothing to copy"]

    verb = "copy" if action == "copy" else "move"
    try:
        dst_store._commit_and_push(f"ops: {verb} {copied} {content_type} item(s) from {src_id}")
    except GitStorageError as e:
        return 0, [f"Failed to commit to target: {e}"]

    if action == "move":
        try:
            src_store._pull()
        except Exception as e:
            errors.append(f"Warning: failed to sync source before delete: {e}")
        deleted = 0
        for item_id in item_ids:
            try:
                if content_type == "knowledge":
                    parts = item_id.split("/", 1)
                    if len(parts) != 2:
                        continue
                    category, slug = parts
                    f = src_store.knowledge_path / category / f"{slug}.md"
                elif content_type == "tasks":
                    f = Path(src_store.local_path) / "tasks" / f"{item_id}.yaml"
                elif content_type == "vacations":
                    f = Path(src_store.local_path) / "vacations" / "entries" / f"{item_id}.yaml"
                elif content_type == "appointments":
                    f = Path(src_store.local_path) / "appointments" / "entries" / f"{item_id}.yaml"
                elif content_type == "links":
                    f = Path(src_store.local_path) / "links" / "default" / f"{item_id}.yaml"
                elif content_type in (
                    "mail_templates",
                    "ticket_templates",
                    "notes",
                    "runbooks",
                    "snippets",
                    "motd",
                    "rss",
                ):
                    f = Path(src_store.local_path) / content_type / f"{item_id}.yaml"
                    if f.exists():
                        f.unlink()
                        deleted += 1
                    continue
                elif content_type in ("potd", "memes"):
                    src_dir = Path(src_store.local_path) / content_type
                    for fpath in src_dir.glob(f"{item_id}.*"):
                        fpath.unlink()
                        deleted += 1
                    continue
                if f.exists():
                    f.unlink()
                    deleted += 1
            except Exception as e:
                errors.append(f"Delete {item_id}: {e}")
        if deleted:
            try:
                src_store._commit_and_push(
                    f"ops: move {deleted} {content_type} item(s) to {dst_id}"
                )
            except GitStorageError as e:
                errors.append(f"Failed to commit delete on source: {e}")

    return copied, errors


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def operations_index(
    request: Request,
    src: str = "",
    type: str = "knowledge",
    result: str = "",
    errors: str = "",
):
    storage = get_storage()
    cfg = settings_store.load()
    repos = [r for r in cfg.get("repos", []) if r.get("enabled", True)]
    items = []

    if src and storage and src in storage._stores:
        items = _get_items(storage, src, type)

    return templates.TemplateResponse(
        request,
        "modules/operations/index.html",
        {
            "repos": repos,
            "src": src,
            "content_type": type,
            "items": items,
            "result": result,
            "errors": errors,
            "active_module": "operations",
            "configured": len(repos) > 1,
        },
    )


@router.post("/execute")
async def execute_operation(
    request: Request,
    src_repo: str = Form(...),
    dst_repo: str = Form(...),
    content_type: str = Form("knowledge"),
    action: str = Form("copy"),
    items: list[str] = Form(default=[]),
):
    from urllib.parse import quote

    if src_repo == dst_repo:
        return RedirectResponse(
            f"/operations?src={src_repo}&type={content_type}&errors={quote('Source and target must be different.')}",
            status_code=303,
        )
    if not items:
        return RedirectResponse(
            f"/operations?src={src_repo}&type={content_type}&errors={quote('No items selected.')}",
            status_code=303,
        )

    storage = get_storage()
    count, errs = _do_copy_move(storage, src_repo, dst_repo, content_type, items, action)

    verb = "copied" if action == "copy" else "moved"
    result_msg = quote(f"{count} item(s) {verb} successfully.")
    errors_msg = quote("; ".join(errs)) if errs else ""
    return RedirectResponse(
        f"/operations?src={src_repo}&type={content_type}&result={result_msg}&errors={errors_msg}",
        status_code=303,
    )


# ── ZIP export ────────────────────────────────────────────────────────────────

_EXPORT_EXTENSIONS = {".yaml", ".yml", ".md", ".txt"}


@router.get("/export")
async def export_repo(repo_id: str):
    """Download all YAML/MD files from a repo as a ZIP archive."""
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    gs = storage.get_store(repo_id)
    if not gs:
        raise HTTPException(status_code=404, detail="Repo not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        repo_path = Path(gs.local_path)
        git_dir = repo_path / ".git"
        for fpath in repo_path.rglob("*"):
            if fpath.is_dir():
                continue
            # Skip .git directory
            try:
                fpath.relative_to(git_dir)
                continue
            except ValueError:
                pass
            if fpath.suffix.lower() not in _EXPORT_EXTENSIONS:
                continue
            arcname = fpath.relative_to(repo_path).as_posix()
            zf.write(fpath, arcname)

    buf.seek(0)
    cfg = settings_store.load()
    repo_name = _repo_name(cfg, repo_id)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in repo_name).strip("_")
    filename = f"daily-helper_{safe_name}-export.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── ZIP import ────────────────────────────────────────────────────────────────


@router.post("/import")
async def import_repo(
    repo_id: str = Form(...),
    mode: str = Form("merge"),
    file: UploadFile = File(...),
):
    """Import a ZIP archive into a repo (merge = keep existing, overwrite = replace all)."""
    from urllib.parse import quote

    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    gs = storage.get_store(repo_id)
    if not gs:
        raise HTTPException(status_code=404, detail="Repo not found")

    repo = settings_store.get_repo(repo_id) or {}
    if not repo.get("permissions", {}).get("write", False):
        raise HTTPException(status_code=403, detail="Repository is read-only")

    data = await file.read()
    if not data:
        return RedirectResponse(
            f"/operations?errors={quote('Uploaded file is empty.')}",
            status_code=303,
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return RedirectResponse(
            f"/operations?errors={quote('Invalid ZIP file.')}",
            status_code=303,
        )

    repo_path = Path(gs.local_path)
    imported = 0
    skipped = 0

    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            arcname = info.filename
            # Security: reject path traversal
            norm = Path(arcname)
            if norm.is_absolute() or ".." in norm.parts:
                continue
            suffix = norm.suffix.lower()
            if suffix not in _EXPORT_EXTENSIONS:
                continue

            dest = repo_path / norm
            if mode == "merge" and dest.exists():
                skipped += 1
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(info))
            imported += 1

    if imported == 0:
        return RedirectResponse(
            f"/operations?result={quote(f'No files imported ({skipped} skipped — already exist).')}",
            status_code=303,
        )

    try:
        gs._commit_and_push(f"import: {imported} file(s) via ZIP upload")
    except GitStorageError as e:
        return RedirectResponse(
            f"/operations?errors={quote(str(e))}",
            status_code=303,
        )

    msg = f"{imported} file(s) imported."
    if skipped:
        msg += f" {skipped} skipped (already exist)."
    return RedirectResponse(
        f"/operations?result={quote(msg)}",
        status_code=303,
    )
