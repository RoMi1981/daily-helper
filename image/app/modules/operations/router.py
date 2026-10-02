"""Operations module — copy/move content between repositories."""

import asyncio
import io
import logging
import shutil
import zipfile
from pathlib import Path

from core import settings_store
from core.state import get_storage
from core.storage import GitStorageError
from core.templates import templates
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

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
            from modules.links.storage import link_storages

            # Links live under links/{section_id}/ — link_storages() walks every
            # configured section, or non-default-section links are invisible to
            # (and unreachable from) this UI. IDs are prefixed with their
            # section so multiple sections can be told apart.
            items = []
            for link_storage in link_storages(store):
                for link in link_storage.list_links():
                    items.append(
                        {
                            **link,
                            "id": f"{link_storage.section_id}/{link['id']}",
                            "section_id": link_storage.section_id,
                        }
                    )
            return items
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
        elif content_type == "eol":
            from modules.eol.storage import EolStorage

            return EolStorage(store).list_entries()
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


def _valid_item_ids(storage, src_id: str, content_type: str) -> set[str]:
    """IDs that actually exist for this content type in the source repo.

    Used to reject manipulated item_ids (e.g. containing '..') before they
    are turned into filesystem paths — item_ids come straight from a client
    form field and must never be trusted as path components on their own.
    """
    if content_type == "knowledge":
        entries = storage._stores.get(src_id) and storage._stores[src_id].get_entries() or []
        return {f"{e.get('category', '')}/{e.get('slug', '')}" for e in entries}
    items = _get_items(storage, src_id, content_type)
    return {i["id"] for i in items if "id" in i}


# Repo-relative layout per content type. Copy and move both work purely on
# these paths, so a new content type is one entry here plus one in _get_items.
_ITEM_DIRS = {
    "tasks": "tasks",
    "vacations": "vacations/entries",
    "appointments": "appointments/entries",
    "eol": "eol",
    "mail_templates": "mail_templates",
    "ticket_templates": "ticket_templates",
    "notes": "notes",
    "runbooks": "runbooks",
    "snippets": "snippets",
    "motd": "motd",
    "rss": "rss",
}
# Media items are one binary plus an optional sidecar, both named by the id.
_MEDIA_TYPES = ("potd", "memes")


def _item_paths(store, content_type: str, item_id: str) -> list[str]:
    """Repo-relative paths that make up one item, or [] if the id does not fit
    the content type. Media types are globbed in *store*, everything else has a
    fixed name and is returned whether or not it exists."""
    if content_type == "knowledge":
        category, sep, slug = item_id.partition("/")
        if not sep or not slug:
            return []
        return [f"knowledge/{category}/{slug}.md"]
    if content_type == "links":
        section_id, sep, link_id = item_id.partition("/")
        if not sep or not link_id:
            return []
        return [f"links/{section_id}/{link_id}.yaml"]
    if content_type in _MEDIA_TYPES:
        root = Path(store.local_path)
        return sorted(f.relative_to(root).as_posix() for f in (root / content_type).glob(f"{item_id}.*"))
    subdir = _ITEM_DIRS.get(content_type)
    if not subdir:
        return []
    return [f"{subdir}/{item_id}.yaml"]


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

    valid_ids = _valid_item_ids(storage, src_id, content_type)
    rejected = [i for i in item_ids if i not in valid_ids]
    item_ids = [i for i in item_ids if i in valid_ids]

    errors: list[str] = [f"Rejected unknown id: {i}" for i in rejected]
    copied = 0

    # Each repo's transaction takes that repo's own lock: target first for the
    # copy, source afterwards for the delete. The two are never held at once,
    # so a second operation in the opposite direction cannot deadlock against
    # this one.
    src_root = Path(src_store.local_path)
    dst_root = Path(dst_store.local_path)

    with dst_store.write_lock():
        try:
            dst_store._pull()
        except Exception as e:
            return 0, [f"Failed to sync target repo: {e}"]

        # Only items copied completely may be deleted from the source on a move;
        # a half-copied item is removed from the target again so it is neither
        # lost nor committed in pieces.
        copied_ids: list[str] = []
        for item_id in item_ids:
            written: list[Path] = []
            try:
                rel_paths = [p for p in _item_paths(src_store, content_type, item_id) if (src_root / p).exists()]
                if not rel_paths:
                    errors.append(f"Not found: {item_id}")
                    continue
                for rel in rel_paths:
                    dst_file = dst_root / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_root / rel, dst_file)
                    written.append(dst_file)
                copied_ids.append(item_id)
                copied += 1
            except Exception as e:
                errors.append(f"{item_id}: {e}")
                for f in written:
                    f.unlink(missing_ok=True)

        if copied == 0:
            return 0, errors or ["Nothing to copy"]

        verb = "copy" if action == "copy" else "move"
        try:
            dst_store._commit_and_push(f"ops: {verb} {copied} {content_type} item(s) from {src_id}")
        except GitStorageError as e:
            return 0, [f"Failed to commit to target: {e}"]

    if action == "move":
        with src_store.write_lock():
            try:
                src_store._pull()
            except Exception as e:
                errors.append(f"Warning: failed to sync source before delete: {e}")
            deleted = 0
            for item_id in copied_ids:
                try:
                    for rel in _item_paths(src_store, content_type, item_id):
                        f = src_root / rel
                        if f.exists():
                            f.unlink()
                            deleted += 1
                except Exception as e:
                    errors.append(f"Delete {item_id}: {e}")
            if deleted:
                try:
                    src_store._commit_and_push(f"ops: move {deleted} {content_type} item(s) to {dst_id}")
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
    count, errs = await asyncio.to_thread(_do_copy_move, storage, src_repo, dst_repo, content_type, items, action)

    verb = "copied" if action == "copy" else "moved"
    result_msg = quote(f"{count} item(s) {verb} successfully.")
    errors_msg = quote("; ".join(errs)) if errs else ""
    return RedirectResponse(
        f"/operations?src={src_repo}&type={content_type}&result={result_msg}&errors={errors_msg}",
        status_code=303,
    )


# ── ZIP export ────────────────────────────────────────────────────────────────

_EXPORT_EXTENSIONS = {".yaml", ".yml", ".md", ".txt"}


def _build_export_zip(repo_path: Path) -> io.BytesIO:
    """Synchronous tree-walk + compress — run via asyncio.to_thread since it
    can take real time for a repo with many files/attachments and would
    otherwise block the single event loop for the whole duration."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
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
    return buf


@router.get("/export")
async def export_repo(repo_id: str):
    """Download all YAML/MD files from a repo as a ZIP archive."""
    storage = get_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")
    gs = storage.get_store(repo_id)
    if not gs:
        raise HTTPException(status_code=404, detail="Repo not found")

    buf = await asyncio.to_thread(_build_export_zip, Path(gs.local_path))
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


def _import_zip(gs, zf: zipfile.ZipFile, mode: str) -> tuple[int, int]:
    """Unpack the archive into the repo and commit. Returns (imported, skipped).

    Synchronous on purpose — run via asyncio.to_thread, the push at the end
    would otherwise block the event loop."""
    repo_path = Path(gs.local_path)
    imported = 0
    skipped = 0

    with gs.write_lock(), zf:
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

        if imported:
            gs._commit_and_push(f"import: {imported} file(s) via ZIP upload")

    return imported, skipped


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

    try:
        imported, skipped = await asyncio.to_thread(_import_zip, gs, zf, mode)
    except GitStorageError as e:
        return RedirectResponse(
            f"/operations?errors={quote(str(e))}",
            status_code=303,
        )
    if imported == 0:
        return RedirectResponse(
            f"/operations?result={quote(f'No files imported ({skipped} skipped — already exist).')}",
            status_code=303,
        )

    msg = f"{imported} file(s) imported."
    if skipped:
        msg += f" {skipped} skipped (already exist)."
    return RedirectResponse(
        f"/operations?result={quote(msg)}",
        status_code=303,
    )
