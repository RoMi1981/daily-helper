"""Tests for modules/history/router.py — _filter_commits and history view (migrated from audit)."""

import os
import sys
import time

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = (
    _candidate
    if os.path.isdir(_candidate)
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"

import main as _main_module


# ── _filter_commits unit tests ─────────────────────────────────────────────────


def _make_commit(ts: int, author: str, subject: str, changes: list[dict]) -> dict:
    return {"ts": ts, "hash": "abc", "author": author, "subject": subject, "changes": changes}


def _change(module: str, action: str = "M", title: str = "item") -> dict:
    return {"module": module, "action": action, "title": title, "url": f"/{module}/1"}


def test_filter_no_filters():
    from modules.history.router import _filter_commits

    commits = [
        _make_commit(1000, "Alice", "add note", [_change("notes")]),
        _make_commit(2000, "Bob", "add task", [_change("tasks")]),
    ]
    result = _filter_commits(commits, "", "", "", "")
    assert len(result) == 2


def test_filter_by_module():
    from modules.history.router import _filter_commits

    commits = [
        _make_commit(1000, "Alice", "note", [_change("notes")]),
        _make_commit(2000, "Bob", "task", [_change("tasks")]),
        _make_commit(3000, "Alice", "mixed", [_change("notes"), _change("tasks")]),
    ]
    result = _filter_commits(commits, "notes", "", "", "")
    assert len(result) == 2
    # mixed commit has only notes changes in result
    assert all(ch["module"] == "notes" for r in result for ch in r["changes"])


def test_filter_by_module_removes_empty_commits():
    from modules.history.router import _filter_commits

    commits = [
        _make_commit(1000, "Alice", "only tasks", [_change("tasks")]),
    ]
    result = _filter_commits(commits, "notes", "", "", "")
    assert result == []


def test_filter_by_author_exact():
    from modules.history.router import _filter_commits

    commits = [
        _make_commit(1000, "Alice", "a", [_change("notes")]),
        _make_commit(2000, "Bob", "b", [_change("notes")]),
    ]
    result = _filter_commits(commits, "", "alice", "", "")
    assert len(result) == 1
    assert result[0]["author"] == "Alice"


def test_filter_by_author_case_insensitive():
    from modules.history.router import _filter_commits

    commits = [_make_commit(1000, "ALICE", "a", [_change("notes")])]
    result = _filter_commits(commits, "", "alice", "", "")
    assert len(result) == 1


def test_filter_by_author_partial():
    from modules.history.router import _filter_commits

    commits = [
        _make_commit(1000, "Alice Smith", "a", [_change("notes")]),
        _make_commit(2000, "Bob Jones", "b", [_change("notes")]),
    ]
    result = _filter_commits(commits, "", "smith", "", "")
    assert len(result) == 1


def test_filter_by_date_from():
    from modules.history.router import _filter_commits
    from datetime import datetime

    cutoff = int(datetime(2026, 1, 15).timestamp())
    commits = [
        _make_commit(int(datetime(2026, 1, 10).timestamp()), "A", "old", [_change("notes")]),
        _make_commit(int(datetime(2026, 1, 20).timestamp()), "A", "new", [_change("notes")]),
    ]
    result = _filter_commits(commits, "", "", "2026-01-15", "")
    assert len(result) == 1
    assert result[0]["subject"] == "new"


def test_filter_by_date_to():
    from modules.history.router import _filter_commits
    from datetime import datetime

    commits = [
        _make_commit(int(datetime(2026, 1, 10).timestamp()), "A", "old", [_change("notes")]),
        _make_commit(int(datetime(2026, 1, 20).timestamp()), "A", "new", [_change("notes")]),
    ]
    result = _filter_commits(commits, "", "", "", "2026-01-15")
    assert len(result) == 1
    assert result[0]["subject"] == "old"


def test_filter_by_date_range():
    from modules.history.router import _filter_commits
    from datetime import datetime

    commits = [
        _make_commit(int(datetime(2026, 1, 5).timestamp()), "A", "too early", [_change("notes")]),
        _make_commit(int(datetime(2026, 1, 15).timestamp()), "A", "in range", [_change("notes")]),
        _make_commit(int(datetime(2026, 1, 25).timestamp()), "A", "too late", [_change("notes")]),
    ]
    result = _filter_commits(commits, "", "", "2026-01-10", "2026-01-20")
    assert len(result) == 1
    assert result[0]["subject"] == "in range"


def test_filter_invalid_date_is_ignored():
    from modules.history.router import _filter_commits

    commits = [_make_commit(1000, "A", "x", [_change("notes")])]
    # Should not raise, just ignore invalid date
    result = _filter_commits(commits, "", "", "not-a-date", "also-not-a-date")
    assert len(result) == 1


def test_filter_combined_module_and_author():
    from modules.history.router import _filter_commits

    commits = [
        _make_commit(1000, "Alice", "a", [_change("notes")]),
        _make_commit(2000, "Bob", "b", [_change("notes")]),
        _make_commit(3000, "Alice", "c", [_change("tasks")]),
    ]
    result = _filter_commits(commits, "notes", "alice", "", "")
    assert len(result) == 1
    assert result[0]["author"] == "Alice"
    assert result[0]["changes"][0]["module"] == "notes"


# ── Router integration ─────────────────────────────────────────────────────────


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


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


def test_audit_view_no_storage(client):
    resp = client.get("/history")
    assert resp.status_code == 200


def test_audit_view_with_filters(client):
    resp = client.get("/history?module=notes&author=Alice&date_from=2026-01-01&date_to=2026-12-31")
    assert resp.status_code == 200


def test_audit_view_with_storage(tmp_path, isolated_settings):
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()

    fake_commits = [
        {
            "ts": int(time.time()),
            "hash": "abc1234",
            "author": "Alice",
            "subject": "add note",
            "changes": [{"module": "notes", "action": "A", "title": "My Note", "url": "/notes/1"}],
        }
    ]
    mock_storage = MagicMock()
    mock_storage.get_history.return_value = fake_commits

    with patch("modules.history.router.get_storage", return_value=mock_storage):
        client = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = client.get("/history")
    assert resp.status_code == 200
    assert b"Alice" in resp.content
    assert b"add note" in resp.content


def test_audit_view_module_filter_passed(tmp_path, isolated_settings):
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()

    mock_storage = MagicMock()
    mock_storage.get_history.return_value = []

    with patch("modules.history.router.get_storage", return_value=mock_storage):
        client = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = client.get("/history?module=tasks")
    assert resp.status_code == 200
