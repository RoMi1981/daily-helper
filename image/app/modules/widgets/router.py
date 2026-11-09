"""Widgets dashboard — routes. The registry lives in registry.py, the data
loading in loaders.py."""

import asyncio
import json
import logging
from datetime import date

from core import settings_store
from core.module_repos import get_module_stores
from core.state import get_storage
from core.templates import templates
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .loaders import _WIDGET_LOADERS, _load_calendar_widget, _load_counts, _LoaderContext
from .registry import _DEFAULT_LAYOUT, WIDGET_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/widgets")

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


def _get_layout() -> list[dict]:
    cfg = settings_store.load()
    stored = cfg.get("dashboard_widgets")
    # None = never configured → show defaults; otherwise use exactly what was saved
    if stored is None:
        return [dict(e) for e in _DEFAULT_LAYOUT]
    return list(stored)


def _save_layout(layout: list[dict]) -> None:
    cfg = settings_store.load()
    cfg["dashboard_widgets"] = layout
    settings_store.save(cfg)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def widgets_dashboard(request: Request):
    cfg = settings_store.load()
    storage = get_storage()
    layout = _get_layout()
    modules_enabled = cfg.get("modules_enabled", {})

    active_widgets = []
    layout_by_id = {e["id"]: e for e in layout}
    for entry in layout:
        wid = entry["id"]
        if wid not in WIDGET_REGISTRY:
            continue
        meta = WIDGET_REGISTRY[wid]
        mod = meta.get("module")
        if mod and not modules_enabled.get(mod, True):
            continue
        if entry.get("enabled", True):
            _SIZE_TO_COLS = {"third": 4, "half": 12, "full": 24}
            default_cols = _SIZE_TO_COLS.get(meta.get("size", "third"), 4)
            cols = entry.get("cols") or default_cols
            col_start = entry.get("col_start")
            active_widgets.append(
                {
                    **meta,
                    "id": wid,
                    "settings": entry.get("settings", {}),
                    "cols": cols,
                    "col_start": col_start,
                }
            )

    active_ids = {w["id"] for w in active_widgets}
    available_widgets = []
    for wid, meta in WIDGET_REGISTRY.items():
        if wid in active_ids:
            continue
        mod = meta.get("module")
        if mod and not modules_enabled.get(mod, True):
            continue
        entry = layout_by_id.get(wid, {})
        available_widgets.append({**meta, "id": wid, "settings": entry.get("settings", {})})

    # Load data for active widgets
    counts: dict = {}
    widget_data: dict = {}

    needed_count_modules = {
        WIDGET_REGISTRY[wid]["module"] for wid in active_ids if wid.startswith("stats_") and wid in WIDGET_REGISTRY
    }

    ctx = _LoaderContext(cfg=cfg, storage=storage, vac_cache={}, task_cache={}, appt_cache={})
    pending = [(w["id"], _WIDGET_LOADERS[w["id"]], w["settings"]) for w in active_widgets if w["id"] in _WIDGET_LOADERS]

    # Every loader reads git and blocks; run them off the event loop and in
    # parallel — a dashboard with ten widgets used to be ten sequential reads.
    # The shared caches in ctx may be filled twice when two loaders want the
    # same data at once; that costs one redundant read, never a wrong result.
    jobs = [asyncio.to_thread(loader, settings, ctx) for _, loader, settings in pending]
    if needed_count_modules:
        jobs.append(asyncio.to_thread(_load_counts, cfg, storage, needed_count_modules))

    results = await asyncio.gather(*jobs, return_exceptions=True)
    loader_results, count_results = results[: len(pending)], results[len(pending) :]

    for (wid, _, _), result in zip(pending, loader_results, strict=True):
        if isinstance(result, BaseException):
            logger.error("Error loading widget data for %s", wid, exc_info=result)
        else:
            widget_data.update(result)
    if count_results:
        count_result = count_results[0]
        if isinstance(count_result, BaseException):
            logger.error("Error loading widget counts", exc_info=count_result)
        else:
            counts = count_result

    # Collect RSS feeds list for settings popover
    rss_feeds_for_settings: list[dict] = []
    try:
        if storage and getattr(storage, "_stores", None):
            from modules.rss.storage import RssStorage

            seen: set[str] = set()
            for s in get_module_stores("rss", storage):
                for f in RssStorage(s).list_feeds():
                    if f["id"] not in seen:
                        seen.add(f["id"])
                        rss_feeds_for_settings.append(f)
    except Exception:
        pass

    # Collect link categories for bookmarks settings
    link_categories: list[str] = []
    try:
        if storage and getattr(storage, "_stores", None):
            from modules.links.storage import link_storages

            cats: set[str] = set()
            for s in get_module_stores("links", storage):
                for link_storage in link_storages(s):
                    for lnk in link_storage.list_links():
                        if lnk.get("category"):
                            cats.add(lnk["category"])
            link_categories = sorted(cats)
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "widgets.html",
        {
            "active_widgets": active_widgets,
            "available_widgets": available_widgets,
            "counts": counts,
            **widget_data,
            "today": date.today().isoformat(),
            "rss_feeds_for_settings": rss_feeds_for_settings,
            "link_categories": link_categories,
            "active_module": "widgets",
        },
    )


_MAX_SETTINGS_BYTES = 10_000


def _valid_settings(value) -> bool:
    """Widget settings must be a JSON object of bounded size (dates, labels,
    thresholds) — not arbitrary client-supplied data committed to git."""
    if not isinstance(value, dict):
        return False
    return len(json.dumps(value)) <= _MAX_SETTINGS_BYTES


@router.post("/layout")
async def save_layout(request: Request):
    try:
        data = await request.json()
        layout = _get_layout()
        layout_by_id = {e["id"]: e for e in layout}
        new_layout = []
        for item in data:
            wid = item.get("id")
            if wid not in WIDGET_REGISTRY:
                continue
            entry = layout_by_id.get(wid, {"id": wid, "settings": {}})
            entry["enabled"] = bool(item.get("enabled", True))
            if "cols" in item:
                try:
                    entry["cols"] = max(1, min(24, int(item["cols"])))
                except (ValueError, TypeError):
                    pass
            if "col_start" in item:
                try:
                    entry["col_start"] = max(1, min(24, int(item["col_start"])))
                except (ValueError, TypeError):
                    pass
            if "settings" in item and _valid_settings(item["settings"]):
                entry["settings"] = item["settings"]
            new_layout.append(entry)
        _save_layout(new_layout)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("Error saving widget layout")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.get("/calendar-partial", response_class=HTMLResponse)
async def calendar_widget_partial(request: Request, year: int | None = None, month: int | None = None):
    if month is not None and not (1 <= month <= 12):
        return JSONResponse({"ok": False, "error": "month must be 1-12"}, status_code=400)
    if year is not None and not (1 <= year <= 9999):
        return JSONResponse({"ok": False, "error": "year out of range"}, status_code=400)
    cfg = settings_store.load()
    storage = get_storage()
    try:
        cal = _load_calendar_widget(year, month, cfg, storage)
    except Exception:
        logger.exception("Error loading calendar widget")
        return JSONResponse({"ok": False, "error": "failed to load calendar"}, status_code=500)
    return templates.TemplateResponse(
        request,
        "widgets/_calendar_widget_body.html",
        {"cal": cal},
    )


@router.post("/{widget_id}/settings")
async def save_widget_settings(widget_id: str, request: Request):
    if widget_id not in WIDGET_REGISTRY:
        return JSONResponse({"ok": False}, status_code=404)
    try:
        new_settings = await request.json()
        if not _valid_settings(new_settings):
            return JSONResponse({"ok": False, "error": "invalid settings"}, status_code=400)
        layout = _get_layout()
        for entry in layout:
            if entry["id"] == widget_id:
                entry["settings"] = new_settings
                break
        _save_layout(layout)
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
