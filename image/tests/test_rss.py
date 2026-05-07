"""Tests for RSS Reader module."""

import importlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("REDIS_URL", "redis://localhost:9999")

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = (
    _candidate
    if os.path.isdir(_candidate)
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

import main as _main_module

from fastapi.testclient import TestClient


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def read_committed(self, path: str):
        full = os.path.join(self.local_path, path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def list_committed(self, directory: str) -> list:
        full = os.path.join(self.local_path, directory)
        if not os.path.isdir(full):
            return []
        return os.listdir(full)


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from core import settings_store

    importlib.reload(settings_store)
    from core import settings_store as ss

    _main_module.settings_store = ss
    yield
    from core.state import reset_storage

    reset_storage()


@pytest.fixture()
def rss_client(isolated_settings):
    from core.state import reset_storage

    reset_storage()
    with (
        patch("modules.rss.router.get_storage", return_value=None),
        patch("modules.rss.router.get_primary_store", return_value=None),
        patch("modules.rss.router.get_module_stores", return_value=[]),
    ):
        yield TestClient(_main_module.app)


@pytest.fixture()
def rss_client_with_storage(tmp_path, isolated_settings):
    from core.state import reset_storage
    from modules.rss.storage import RssStorage

    reset_storage()
    fake_git = FakeGit(tmp_path)
    store = RssStorage(fake_git)
    store.upsert_feed({"name": "Test Feed", "url": "https://example.com/feed.xml", "enabled": True})

    with (
        patch("modules.rss.router.get_storage"),
        patch("modules.rss.router.get_primary_store", return_value=fake_git),
        patch("modules.rss.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app), store


def _make_entry(title="Test Item", link="https://example.com/1", summary="A summary"):
    e = MagicMock()
    e.get = lambda k, d="": {"title": title, "link": link}.get(k, d)
    e.published_parsed = (2026, 5, 1, 10, 0, 0, 0, 0, 0)
    e.updated_parsed = None
    e.summary = summary
    return e


def _make_parsed(entries=None, bozo=False):
    p = MagicMock()
    p.entries = entries or []
    p.get = lambda k, d=None: {"bozo": bozo, "bozo_exception": None}.get(k, d)
    return p


class TestRssList:
    def test_returns_200(self, rss_client):
        r = rss_client.get("/rss")
        assert r.status_code == 200

    def test_shows_no_feeds_message(self, rss_client):
        r = rss_client.get("/rss")
        assert "No RSS feeds" in r.text or "No repository configured" in r.text

    def test_shows_feed_name(self, rss_client_with_storage):
        client, _ = rss_client_with_storage
        r = client.get("/rss")
        assert "Test Feed" in r.text

    def test_shows_refresh_button(self, rss_client_with_storage):
        client, _ = rss_client_with_storage
        r = client.get("/rss")
        assert "refresh-cw" in r.text

    def test_disabled_when_module_off(self, isolated_settings):
        from core import settings_store
        from core.state import reset_storage

        reset_storage()
        cfg = settings_store.load()
        cfg["modules_enabled"]["rss"] = False
        settings_store.save(cfg)

        with (
            patch("modules.rss.router.get_storage", return_value=None),
            patch("modules.rss.router.get_primary_store", return_value=None),
        ):
            client = TestClient(_main_module.app, raise_server_exceptions=False)
            r = client.get("/rss")
        assert r.status_code == 404


class TestRssFeedPartial:
    def test_returns_items(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]

        entry = _make_entry("Hello World", "https://example.com/hello", "Short summary")
        parsed = _make_parsed(entries=[entry])

        with (
            patch("modules.rss.router.feedparser.parse", return_value=parsed),
            patch("modules.rss.router.cache.get_client", return_value=None),
        ):
            r = client.get(f"/rss/feed/{feed_id}")

        assert r.status_code == 200
        assert "Hello World" in r.text

    def test_shows_error_on_bozo(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]

        parsed = _make_parsed(entries=[], bozo=True)
        parsed.get = lambda k, d=None: {
            "bozo": True,
            "bozo_exception": Exception("bad feed"),
        }.get(k, d)

        with (
            patch("modules.rss.router.feedparser.parse", return_value=parsed),
            patch("modules.rss.router.cache.get_client", return_value=None),
        ):
            r = client.get(f"/rss/feed/{feed_id}")

        assert r.status_code == 200
        assert "bad feed" in r.text

    def test_unknown_feed_returns_not_found_text(self, rss_client_with_storage):
        client, _ = rss_client_with_storage
        r = client.get("/rss/feed/nonexistent")
        assert r.status_code == 200
        assert "not found" in r.text.lower()

    def test_uses_redis_cache(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]

        cached = json.dumps(
            {
                "items": [
                    {
                        "title": "Cached",
                        "link": "https://x.com",
                        "published": None,
                        "summary": "",
                    }
                ],
                "error": None,
                "fetched_at": 0,
            }
        )
        mock_client = MagicMock()
        mock_client.get.return_value = cached

        with patch("modules.rss.router.cache.get_client", return_value=mock_client):
            r = client.get(f"/rss/feed/{feed_id}")

        assert "Cached" in r.text

    def test_empty_feed_shows_no_items(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]
        parsed = _make_parsed(entries=[])

        with (
            patch("modules.rss.router.feedparser.parse", return_value=parsed),
            patch("modules.rss.router.cache.get_client", return_value=None),
        ):
            r = client.get(f"/rss/feed/{feed_id}")

        assert "No items found" in r.text


class TestRssRefresh:
    def test_refresh_clears_cache_and_returns_items(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]

        entry = _make_entry("Fresh Item")
        parsed = _make_parsed(entries=[entry])
        mock_client = MagicMock()
        mock_client.get.return_value = None

        with (
            patch("modules.rss.router.feedparser.parse", return_value=parsed),
            patch("modules.rss.router.cache.get_client", return_value=mock_client),
        ):
            r = client.post(f"/rss/feed/{feed_id}/refresh")

        assert r.status_code == 200
        assert "Fresh Item" in r.text
        mock_client.delete.assert_called_once()

    def test_refresh_unknown_feed(self, rss_client_with_storage):
        client, _ = rss_client_with_storage
        r = client.post("/rss/feed/nonexistent/refresh")
        assert r.status_code == 200
        assert "not found" in r.text.lower()


class TestRssStorage:
    def test_upsert_and_list(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        store.upsert_feed({"name": "Heise", "url": "https://heise.de/feed", "enabled": True})
        feeds = store.list_feeds()
        assert any(f["name"] == "Heise" for f in feeds)

    def test_upsert_assigns_id(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        feed = store.upsert_feed({"name": "X", "url": "https://x.com", "enabled": True})
        assert feed.get("id")

    def test_delete(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        feed = store.upsert_feed({"name": "Del", "url": "https://del.com", "enabled": True})
        assert store.delete_feed(feed["id"])
        assert not any(f["id"] == feed["id"] for f in store.list_feeds())

    def test_delete_nonexistent(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        assert not store.delete_feed("nonexistent")

    def test_update_existing(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        feed = store.upsert_feed({"name": "Old", "url": "https://old.com", "enabled": True})
        feed["name"] = "New"
        store.upsert_feed(feed)
        feeds = store.list_feeds()
        match = next(f for f in feeds if f["id"] == feed["id"])
        assert match["name"] == "New"
        assert len([f for f in feeds if f["id"] == feed["id"]]) == 1

    def test_commits_on_upsert(self, tmp_path):
        from modules.rss.storage import RssStorage

        git = FakeGit(tmp_path)
        store = RssStorage(git)
        store.upsert_feed({"name": "X", "url": "https://x.com", "enabled": True})
        assert git._committed

    def test_commits_on_delete(self, tmp_path):
        from modules.rss.storage import RssStorage

        git = FakeGit(tmp_path)
        store = RssStorage(git)
        feed = store.upsert_feed({"name": "X", "url": "https://x.com", "enabled": True})
        git._committed.clear()
        store.delete_feed(feed["id"])
        assert git._committed

    def test_set_default(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        a = store.upsert_feed({"name": "A", "url": "https://a.com", "enabled": True})
        b = store.upsert_feed({"name": "B", "url": "https://b.com", "enabled": True})
        store.set_default(b["id"])
        feeds = {f["id"]: f for f in store.list_feeds()}
        assert not feeds[a["id"]].get("default")
        assert feeds[b["id"]].get("default")

    def test_set_default_clears_previous(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        a = store.upsert_feed({"name": "A", "url": "https://a.com", "enabled": True})
        b = store.upsert_feed({"name": "B", "url": "https://b.com", "enabled": True})
        store.set_default(a["id"])
        store.set_default(b["id"])
        feeds = {f["id"]: f for f in store.list_feeds()}
        assert not feeds[a["id"]].get("default")
        assert feeds[b["id"]].get("default")

    def test_set_default_nonexistent(self, tmp_path):
        from modules.rss.storage import RssStorage

        store = RssStorage(FakeGit(tmp_path))
        assert not store.set_default("nonexistent")

    def test_set_default_commits(self, tmp_path):
        from modules.rss.storage import RssStorage

        git = FakeGit(tmp_path)
        store = RssStorage(git)
        feed = store.upsert_feed({"name": "X", "url": "https://x.com", "enabled": True})
        git._committed.clear()
        store.set_default(feed["id"])
        assert git._committed


class TestRssFeedPage:
    def test_feed_page_returns_200(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]
        r = client.get(f"/rss/{feed_id}")
        assert r.status_code == 200
        assert "Test Feed" in r.text

    def test_feed_page_unknown_redirects(self, rss_client_with_storage):
        client, _ = rss_client_with_storage
        r = client.get("/rss/nonexistent", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/rss"

    def test_rss_index_redirects_to_first_feed(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]
        r = client.get("/rss", follow_redirects=False)
        assert r.status_code == 302
        assert feed_id in r.headers["location"]

    def test_rss_index_redirects_to_default_feed(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        b = store.upsert_feed({"name": "B Feed", "url": "https://b.com/feed", "enabled": True})
        store.set_default(b["id"])
        r = client.get("/rss", follow_redirects=False)
        assert r.status_code == 302
        assert b["id"] in r.headers["location"]

    def test_set_default_route_redirects(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed_id = store.list_feeds()[0]["id"]
        r = client.post(f"/rss/feeds/{feed_id}/set-default", follow_redirects=False)
        assert r.status_code == 303
        assert feed_id in r.headers["location"]

    def test_subnav_shows_all_feeds(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        store.upsert_feed({"name": "Second Feed", "url": "https://two.com/feed", "enabled": True})
        feed_id = store.list_feeds()[0]["id"]
        r = client.get(f"/rss/{feed_id}")
        assert "Test Feed" in r.text
        assert "Second Feed" in r.text

    def test_star_shown_for_default_feed(self, rss_client_with_storage):
        client, store = rss_client_with_storage
        feed = store.list_feeds()[0]
        store.set_default(feed["id"])
        r = client.get(f"/rss/{feed['id']}")
        assert "set-default" in r.text
