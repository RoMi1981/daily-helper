"""Unit tests for history routes across all modules.

Verifies that:
- /history routes return 200 with commit list rendered
- ?sha= parameter loads a diff
- 404 is returned for unknown IDs
"""

import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))
os.environ.setdefault("REDIS_URL", "redis://localhost:9999")
os.environ.setdefault("DATA_DIR", "/tmp")

from main import app

client = TestClient(app, raise_server_exceptions=True)

FAKE_COMMITS = [
    {
        "sha": "abc123def456abc1",
        "date": datetime(2026, 4, 20, 10, 0, 0),
        "author": "Robert",
        "message": "update entry",
    },
    {
        "sha": "def456abc123def4",
        "date": datetime(2026, 4, 19, 9, 0, 0),
        "author": "Robert",
        "message": "initial commit",
    },
]

FAKE_DIFF = """\
diff --git a/tasks/abc123.yaml b/tasks/abc123.yaml
--- a/tasks/abc123.yaml
+++ b/tasks/abc123.yaml
@@ -1,3 +1,3 @@
-title: Old title
+title: New title
 done: false
"""


def _mock_store(commits=None, diff=""):
    store = MagicMock()
    store.get_file_history.return_value = commits if commits is not None else FAKE_COMMITS
    store.get_file_diff.return_value = diff
    return store


def _mock_storage(item=None, commits=None, diff=""):
    """Create a mock storage whose _git returns fake history/diff."""
    s = MagicMock()
    s._git = _mock_store(commits=commits, diff=diff)
    return s


# ── Tasks ─────────────────────────────────────────────────────────────────────


class TestTaskHistory:
    def _task(self):
        return {"id": "abc123", "title": "My Task", "done": False, "priority": "medium"}

    def test_task_history_returns_200(self):
        mock_ts = _mock_storage()
        mock_ts.get_task.return_value = self._task()
        with patch("modules.tasks.router._find_task_storage", return_value=mock_ts):
            resp = client.get("/tasks/abc123/history")
        assert resp.status_code == 200
        assert "My Task" in resp.text
        assert "abc123de" in resp.text  # sha[:8]

    def test_task_history_shows_diff(self):
        mock_ts = _mock_storage(diff=FAKE_DIFF)
        mock_ts.get_task.return_value = self._task()
        with patch("modules.tasks.router._find_task_storage", return_value=mock_ts):
            resp = client.get("/tasks/abc123/history?sha=abc123def456abc1")
        assert resp.status_code == 200
        assert "New title" in resp.text

    def test_task_history_404(self):
        with patch("modules.tasks.router._find_task_storage", return_value=None):
            resp = client.get("/tasks/notexist/history")
        assert resp.status_code == 404


# ── Runbooks ──────────────────────────────────────────────────────────────────


class TestRunbookHistory:
    def _rb(self):
        return {"id": "rb001", "title": "Deploy Runbook", "steps": []}

    def test_runbook_history_returns_200(self):
        mock_rs = _mock_storage()
        mock_rs.get_runbook.return_value = self._rb()
        with patch("modules.runbooks.router._find_storage", return_value=mock_rs):
            resp = client.get("/runbooks/rb001/history")
        assert resp.status_code == 200
        assert "Deploy Runbook" in resp.text

    def test_runbook_history_404(self):
        with patch("modules.runbooks.router._find_storage", return_value=None):
            resp = client.get("/runbooks/notexist/history")
        assert resp.status_code == 404


# ── Snippets ──────────────────────────────────────────────────────────────────


class TestSnippetHistory:
    def _sn(self):
        return {"id": "sn001", "title": "Git cleanup", "steps": []}

    def test_snippet_history_returns_200(self):
        mock_ss = _mock_storage()
        mock_ss.get_snippet.return_value = self._sn()
        with patch("modules.snippets.router._find_storage", return_value=mock_ss):
            resp = client.get("/snippets/sn001/history")
        assert resp.status_code == 200
        assert "Git cleanup" in resp.text

    def test_snippet_history_empty_commits(self):
        mock_ss = _mock_storage(commits=[])
        mock_ss.get_snippet.return_value = self._sn()
        with patch("modules.snippets.router._find_storage", return_value=mock_ss):
            resp = client.get("/snippets/sn001/history")
        assert resp.status_code == 200
        assert "No history found" in resp.text


# ── Mail Templates ────────────────────────────────────────────────────────────


class TestMailTemplateHistory:
    def _tpl(self):
        return {"id": "mt001", "name": "Vacation Request", "to": "", "subject": ""}

    def test_mail_template_history_returns_200(self):
        mock_ts = _mock_storage()
        mock_ts.get_template.return_value = self._tpl()
        with patch("modules.mail_templates.router._find_storage", return_value=mock_ts):
            resp = client.get("/mail-templates/mt001/history")
        assert resp.status_code == 200
        assert "Vacation Request" in resp.text

    def test_mail_template_history_404(self):
        with patch("modules.mail_templates.router._find_storage", return_value=None):
            resp = client.get("/mail-templates/notexist/history")
        assert resp.status_code == 404


# ── Ticket Templates ──────────────────────────────────────────────────────────


class TestTicketTemplateHistory:
    def _tpl(self):
        return {"id": "tt001", "name": "Bug Report", "description": "", "body": ""}

    def test_ticket_template_history_returns_200(self):
        mock_ts = _mock_storage()
        mock_ts.get_template.return_value = self._tpl()
        with patch("modules.ticket_templates.router._find_storage", return_value=mock_ts):
            resp = client.get("/ticket-templates/tt001/history")
        assert resp.status_code == 200
        assert "Bug Report" in resp.text

    def test_ticket_template_history_shows_diff(self):
        mock_ts = _mock_storage(diff=FAKE_DIFF)
        mock_ts.get_template.return_value = self._tpl()
        with patch("modules.ticket_templates.router._find_storage", return_value=mock_ts):
            resp = client.get("/ticket-templates/tt001/history?sha=abc123def456abc1")
        assert resp.status_code == 200
        assert "New title" in resp.text


# ── Storage methods ───────────────────────────────────────────────────────────


class TestStorageHistoryMethods:
    """Verify get_file_history and get_file_diff exist and validate SHA."""

    def test_get_file_history_exists(self):
        from core.storage import GitStorage

        assert callable(getattr(GitStorage, "get_file_history", None))

    def test_get_file_diff_rejects_invalid_sha(self):
        from core.storage import GitStorage

        gs = object.__new__(GitStorage)
        gs.local_path = "/tmp"
        gs._build_env = lambda: {}
        result = gs.get_file_diff("../../etc/passwd", "some/file.yaml")
        assert result == ""

    def test_get_file_diff_rejects_empty_sha(self):
        from core.storage import GitStorage

        gs = object.__new__(GitStorage)
        gs.local_path = "/tmp"
        gs._build_env = lambda: {}
        result = gs.get_file_diff("", "some/file.yaml")
        assert result == ""
