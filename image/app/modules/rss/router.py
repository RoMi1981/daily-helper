"""RSS Reader module."""

import hashlib
import json
import time
from datetime import datetime

import feedparser
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import cache
from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.rss.storage import RssStorage

router = APIRouter(prefix="/rss", dependencies=[require_module("rss")])

CACHE_TTL = 900  # 15 minutes


def _cache_key(feed_id: str) -> str:
    return f"rss:feed:{feed_id}"


def _fetch_feed(url: str) -> dict:
    """Fetch and parse a feed URL. Returns {items, error, fetched_at}."""
    try:
        parsed = feedparser.parse(url)
        if parsed.get("bozo") and not parsed.get("entries"):
            return {
                "items": [],
                "error": str(parsed.get("bozo_exception", "Parse error")),
                "fetched_at": time.time(),
            }
        items = []
        for entry in parsed.entries[:50]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                try:
                    published = datetime(*entry.updated_parsed[:6]).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            summary = ""
            if hasattr(entry, "summary"):
                import re

                summary = re.sub(r"<[^>]+>", "", entry.summary or "")[:300].strip()
            items.append(
                {
                    "title": entry.get("title", "(no title)"),
                    "link": entry.get("link", ""),
                    "published": published,
                    "summary": summary,
                }
            )
        return {"items": items, "error": None, "fetched_at": time.time()}
    except Exception as e:
        return {"items": [], "error": str(e), "fetched_at": time.time()}


def _get_feed_cached(feed: dict) -> dict:
    """Return feed data from Redis cache or fetch fresh."""
    key = _cache_key(feed["id"])
    client = cache.get_client()
    if client:
        try:
            raw = client.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass

    data = _fetch_feed(feed["url"])

    if client:
        try:
            client.setex(key, CACHE_TTL, json.dumps(data))
        except Exception:
            pass

    return data


def _clear_feed_cache(feed_id: str) -> None:
    client = cache.get_client()
    if client:
        try:
            client.delete(_cache_key(feed_id))
        except Exception:
            pass


def _get_store() -> RssStorage | None:
    """Primary storage — used for writes (add/edit/delete feeds)."""
    storage = get_storage()
    git = get_primary_store("rss", storage)
    return RssStorage(git) if git else None


def _get_all_stores() -> list[RssStorage]:
    return [RssStorage(git) for git in get_module_stores("rss", get_storage())]


def _find_store(feed_id: str) -> RssStorage | None:
    for rs in _get_all_stores():
        if any(f["id"] == feed_id for f in rs.list_feeds()):
            return rs
    return None


def _list_all_feeds() -> list[dict]:
    seen: set[str] = set()
    feeds: list[dict] = []
    for rs in _get_all_stores():
        for f in rs.list_feeds():
            if f["id"] not in seen:
                seen.add(f["id"])
                feeds.append(f)
    return feeds


@router.get("", response_class=HTMLResponse)
async def rss_index(request: Request):
    all_feeds = _list_all_feeds()
    enabled = [f for f in all_feeds if f.get("enabled", True)]
    target = next((f for f in enabled if f.get("default")), None) or (
        enabled[0] if enabled else None
    )
    if target:
        return RedirectResponse(f"/rss/{target['id']}", status_code=302)
    return templates.TemplateResponse(
        request,
        "modules/rss/list.html",
        {
            "current_feed": None,
            "all_feeds": all_feeds,
            "has_storage": bool(_get_all_stores()),
            "active_module": "rss",
        },
    )


@router.post("/feeds/new")
async def add_feed(
    name: str = Form(...),
    url: str = Form(...),
    enabled: str = Form(""),
):
    store = _get_store()
    if store:
        store.upsert_feed({"name": name.strip(), "url": url.strip(), "enabled": enabled == "on"})
    return RedirectResponse("/rss", status_code=303)


@router.post("/feeds/{feed_id}/edit")
async def edit_feed(
    feed_id: str,
    name: str = Form(...),
    url: str = Form(...),
    enabled: str = Form(""),
):
    store = _find_store(feed_id)
    if store:
        feed = next((f for f in store.list_feeds() if f["id"] == feed_id), None)
        if feed:
            feed.update({"name": name.strip(), "url": url.strip(), "enabled": enabled == "on"})
            store.upsert_feed(feed)
    return RedirectResponse(f"/rss/{feed_id}", status_code=303)


@router.post("/feeds/{feed_id}/delete")
async def delete_feed(feed_id: str):
    store = _find_store(feed_id)
    if store:
        store.delete_feed(feed_id)
    return RedirectResponse("/rss", status_code=303)


@router.post("/feeds/{feed_id}/set-default")
async def set_default_feed(feed_id: str):
    store = _find_store(feed_id)
    if store:
        store.set_default(feed_id)
    return RedirectResponse(f"/rss/{feed_id}", status_code=303)


@router.get("/feed/{feed_id}", response_class=HTMLResponse)
async def rss_feed_partial(request: Request, feed_id: str):
    feed = next((f for f in _list_all_feeds() if f["id"] == feed_id), None)
    if not feed:
        return HTMLResponse('<p style="color:var(--text-muted)">Feed not found.</p>')
    data = _get_feed_cached(feed)
    return templates.TemplateResponse(
        request,
        "modules/rss/feed_partial.html",
        {
            "feed": feed,
            "items": data["items"],
            "error": data["error"],
            "fetched_at": data["fetched_at"],
        },
    )


@router.post("/feed/{feed_id}/refresh", response_class=HTMLResponse)
async def refresh_feed(request: Request, feed_id: str):
    feed = next((f for f in _list_all_feeds() if f["id"] == feed_id), None)
    if not feed:
        return HTMLResponse('<p style="color:var(--text-muted)">Feed not found.</p>')
    _clear_feed_cache(feed_id)
    data = _get_feed_cached(feed)
    return templates.TemplateResponse(
        request,
        "modules/rss/feed_partial.html",
        {
            "feed": feed,
            "items": data["items"],
            "error": data["error"],
            "fetched_at": data["fetched_at"],
        },
    )


@router.get("/{feed_id}", response_class=HTMLResponse)
async def rss_feed_page(request: Request, feed_id: str):
    all_feeds = _list_all_feeds()
    current_feed = next((f for f in all_feeds if f["id"] == feed_id), None)
    if not current_feed:
        return RedirectResponse("/rss", status_code=302)
    return templates.TemplateResponse(
        request,
        "modules/rss/list.html",
        {
            "current_feed": current_feed,
            "all_feeds": all_feeds,
            "has_storage": bool(_get_all_stores()),
            "active_module": "rss",
        },
    )
