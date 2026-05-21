"""Tests for the knowledge module router — covers exception paths and edge cases."""

import os
import sys
import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"

import main as _main_module


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store
    importlib.reload(settings_store)
    from core import settings_store as ss
    _main_module.settings_store = ss
    yield
    from core.state import reset_storage
    reset_storage()


def _make_client():
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


# ── _sidebar exception path (lines 62-63) ────────────────────────────────────

def test_sidebar_exception_is_swallowed(isolated_settings):
    """If store.get_categories() raises, the sidebar returns partial results."""
    from unittest.mock import patch, MagicMock

    broken_store = MagicMock()
    broken_store.get_categories.side_effect = RuntimeError("disk error")

    fake_storage = MagicMock()
    fake_storage._cfg = {"repos": [{"id": "r1", "name": "Repo"}]}

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage), \
         patch("modules.knowledge.router.get_module_stores", return_value=[broken_store]):
        resp = client.get("/knowledge/")
        assert resp.status_code == 200


# ── index get_entries exception path (lines 76-77) ───────────────────────────

def test_index_get_entries_exception_is_swallowed(isolated_settings):
    from unittest.mock import patch, MagicMock

    broken_store = MagicMock()
    broken_store.get_entries.side_effect = RuntimeError("broken")

    fake_storage = MagicMock()
    fake_storage._cfg = {"repos": []}

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage), \
         patch("modules.knowledge.router.get_module_stores", return_value=[broken_store]):
        resp = client.get("/knowledge/")
        assert resp.status_code == 200


# ── search exception path (lines 103-104) and category-only (line 106) ───────

def test_search_store_exception_swallowed(isolated_settings):
    from unittest.mock import patch, MagicMock

    broken_store = MagicMock()
    broken_store.search.side_effect = RuntimeError("broken")

    fake_storage = MagicMock()

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage), \
         patch("modules.knowledge.router.get_module_stores", return_value=[broken_store]):
        resp = client.get("/knowledge/search?q=test")
        assert resp.status_code == 200


def test_search_category_only_no_query(isolated_settings):
    """Category filter without a search query hits storage.get_entries (line 106)."""
    from unittest.mock import patch, MagicMock

    fake_storage = MagicMock()
    fake_storage.get_entries.return_value = []

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage), \
         patch("modules.knowledge.router.get_module_stores", return_value=[]):
        resp = client.get("/knowledge/search?category=SomeCat")
        assert resp.status_code == 200
        fake_storage.get_entries.assert_called_once_with(category="SomeCat")


# ── create_entry validation (lines 152, 154) ──────────────────────────────────

def test_create_entry_empty_category_400(isolated_settings):
    from unittest.mock import patch, MagicMock

    fake_storage = MagicMock()
    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage):
        resp = client.post("/knowledge/entries", data={
            "repo_id": "r1", "category": "  ", "new_category": "  ",
            "title": "T", "content": "Body",
        })
        assert resp.status_code == 400


def test_create_entry_empty_title_400(isolated_settings):
    from unittest.mock import patch, MagicMock

    fake_storage = MagicMock()
    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage):
        resp = client.post("/knowledge/entries", data={
            "repo_id": "r1", "category": "Cat", "new_category": "",
            "title": "   ", "content": "Body",
        })
        assert resp.status_code == 400


def test_create_entry_git_storage_error_redirects(isolated_settings):
    from unittest.mock import patch, MagicMock
    from core.storage import GitStorageError

    fake_storage = MagicMock()
    fake_storage.save_entry.side_effect = GitStorageError("push failed")

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage):
        resp = client.post("/knowledge/entries", data={
            "repo_id": "r1", "category": "Cat", "new_category": "",
            "title": "Title", "content": "Body",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert "/knowledge/new" in resp.headers["location"]


# ── view_entry no storage (line 178) ─────────────────────────────────────────

def test_view_entry_no_storage_503(isolated_settings):
    from unittest.mock import patch

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=None):
        resp = client.get("/knowledge/entries/r1/Cat/some-slug")
        assert resp.status_code == 503


# ── edit_entry_form no storage (line 205) ────────────────────────────────────

def test_edit_entry_form_no_storage_503(isolated_settings):
    from unittest.mock import patch

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=None):
        resp = client.get("/knowledge/entries/r1/Cat/some-slug/edit")
        assert resp.status_code == 503


# ── update_entry no storage + GitStorageError (lines 230, 248-250) ───────────

def test_update_entry_no_storage_503(isolated_settings):
    from unittest.mock import patch

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=None):
        resp = client.post("/knowledge/entries/r1/Cat/slug/edit", data={
            "title": "T", "content": "Body",
        })
        assert resp.status_code == 503


def test_update_entry_git_storage_error_redirects(isolated_settings):
    from unittest.mock import patch, MagicMock
    from core.storage import GitStorageError
    from core import settings_store

    cfg = settings_store.load()
    cfg["repos"] = [{"id": "r1", "name": "R", "permissions": {"write": True}}]
    settings_store.save(cfg)

    fake_storage = MagicMock()
    fake_storage.update_entry.side_effect = GitStorageError("push failed")

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage):
        resp = client.post("/knowledge/entries/r1/Cat/slug/edit", data={
            "title": "T", "content": "Body",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert "/edit" in resp.headers["location"]


# ── pin_entry (lines 264, 270-271) ───────────────────────────────────────────

def test_pin_entry_no_storage_503(isolated_settings):
    from unittest.mock import patch

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=None):
        resp = client.post("/knowledge/entries/r1/Cat/slug/pin")
        assert resp.status_code == 503


def test_pin_entry_git_storage_error_500(isolated_settings):
    from unittest.mock import patch, MagicMock
    from core.storage import GitStorageError
    from core import settings_store

    cfg = settings_store.load()
    cfg["repos"] = [{"id": "r1", "name": "R", "permissions": {"write": True}}]
    settings_store.save(cfg)

    fake_storage = MagicMock()
    fake_storage.toggle_pin.side_effect = GitStorageError("conflict")

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage):
        resp = client.post("/knowledge/entries/r1/Cat/slug/pin")
        assert resp.status_code == 500


# ── delete_entry (lines 285, 291-292) ────────────────────────────────────────

def test_delete_entry_no_storage_503(isolated_settings):
    from unittest.mock import patch

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=None):
        resp = client.post("/knowledge/entries/r1/Cat/slug/delete")
        assert resp.status_code == 503


def test_delete_entry_git_storage_error_500(isolated_settings):
    from unittest.mock import patch, MagicMock
    from core.storage import GitStorageError
    from core import settings_store

    cfg = settings_store.load()
    cfg["repos"] = [{"id": "r1", "name": "R", "permissions": {"write": True}}]
    settings_store.save(cfg)

    fake_storage = MagicMock()
    fake_storage.delete_entry.side_effect = GitStorageError("locked")

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage):
        resp = client.post("/knowledge/entries/r1/Cat/slug/delete")
        assert resp.status_code == 500


# ── category_view exception (lines 305-306) ──────────────────────────────────

def test_category_view_store_exception_swallowed(isolated_settings):
    from unittest.mock import patch, MagicMock

    broken_store = MagicMock()
    broken_store.get_entries.side_effect = RuntimeError("broken")

    fake_storage = MagicMock()

    client = _make_client()
    with patch("modules.knowledge.router.get_storage", return_value=fake_storage), \
         patch("modules.knowledge.router.get_module_stores", return_value=[broken_store]):
        resp = client.get("/knowledge/category/TestCat")
        assert resp.status_code == 200
