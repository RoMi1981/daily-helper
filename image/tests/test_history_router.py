"""Unit tests for the history router — verifies event structure."""

import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))
os.environ.setdefault("REDIS_URL", "redis://localhost:9999")

from main import app

client = TestClient(app, raise_server_exceptions=True)

FAKE_COMMITS = [
    {
        "ts": int(datetime(2026, 4, 23, 10, 0, 0).timestamp()),
        "hash": "abc1234",
        "author": "Alice",
        "subject": "add tasks, links and notes",
        "changes": [
            {
                "action": "A",
                "module": "tasks",
                "title": "My Task",
                "deleted": False,
                "url": "/tasks/abc12345/edit",
            },
            {
                "action": "M",
                "module": "links",
                "title": "Gitea",
                "deleted": False,
                "url": "/links/def67890/edit?section=default",
            },
            {
                "action": "A",
                "module": "notes",
                "title": "My Note",
                "deleted": False,
                "url": "/notes/ghi11111",
            },
        ],
    }
]


def _mock_storage(commits):
    storage = MagicMock()
    storage.get_history.return_value = commits
    return storage


class TestHistoryEventStructure:
    def test_events_contain_url(self):
        """Each history event must include a url field."""
        with (
            patch("modules.history.router.get_storage", return_value=_mock_storage(FAKE_COMMITS)),
            patch("modules.history.router.cache.get", return_value=None),
            patch("modules.history.router.cache.set"),
        ):
            resp = client.get("/history", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        # All three change entries should have non-empty hrefs in the HTML
        assert "/tasks/abc12345/edit" in resp.text
        assert "/links/def67890/edit" in resp.text
        assert "/notes/ghi11111" in resp.text

    def test_events_contain_title(self):
        """Each history event must show the resolved title, not the ID."""
        with (
            patch("modules.history.router.get_storage", return_value=_mock_storage(FAKE_COMMITS)),
            patch("modules.history.router.cache.get", return_value=None),
            patch("modules.history.router.cache.set"),
        ):
            resp = client.get("/history", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "My Task" in resp.text
        assert "Gitea" in resp.text
        assert "My Note" in resp.text

    def test_no_events_empty_state(self):
        """Empty history renders without error."""
        with (
            patch("modules.history.router.get_storage", return_value=_mock_storage([])),
            patch("modules.history.router.cache.get", return_value=None),
            patch("modules.history.router.cache.set"),
        ):
            resp = client.get("/history", headers={"HX-Request": "true"})
        assert resp.status_code == 200

    def test_invalid_range_defaults_to_week(self):
        """Unknown range key falls back to 'week'."""
        with (
            patch("modules.history.router.get_storage", return_value=_mock_storage([])),
            patch("modules.history.router.cache.get", return_value=None),
            patch("modules.history.router.cache.set"),
        ):
            resp = client.get("/history?range=bogus", headers={"HX-Request": "true"})
        assert resp.status_code == 200

    def test_url_not_pointing_to_history(self):
        """No href should point back to /history itself."""
        with (
            patch("modules.history.router.get_storage", return_value=_mock_storage(FAKE_COMMITS)),
            patch("modules.history.router.cache.get", return_value=None),
            patch("modules.history.router.cache.set"),
        ):
            resp = client.get("/history", headers={"HX-Request": "true"})
        # Links must not be empty (which would resolve to current page)
        assert 'href=""' not in resp.text
        assert 'href="/history"' not in resp.text
