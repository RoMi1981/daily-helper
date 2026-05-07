"""API endpoint tests using FastAPI TestClient.

All git/filesystem operations are mocked — no real repo or network needed.
Settings are written to a temp directory via the DATA_DIR env var.
"""

import json
import os
import sys
import pytest

# Run from the app/ directory so StaticFiles/Jinja2 find 'static/' and 'templates/'.
# In Docker the layout is /app/{main.py,static/,...} /app/tests/
# Locally it is image/app/{...} image/tests/
_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = (
    _candidate
    if os.path.isdir(_candidate)
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"  # unreachable — cache off
os.environ.pop("SECRET_KEY", None)  # auto-generated per DATA_DIR

# Import main once — StaticFiles/Jinja2 are bound to the process cwd at import time
import main as _main_module


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Each test gets its own DATA_DIR — settings_store reloaded with new path."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)
    # Patch DATA_DIR in the already-imported main module's settings_store reference
    from core import settings_store as ss

    _main_module.settings_store = ss
    yield
    from core.state import reset_storage

    reset_storage()


@pytest.fixture()
def client(isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


@pytest.fixture()
def client_with_repo(tmp_path, monkeypatch):
    """Client with one writable mock repo pre-configured."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)

    import importlib
    from core import settings_store

    importlib.reload(settings_store)
    _main_module.settings_store = settings_store

    # Write a minimal settings.json with one repo
    cfg = {
        "repos": [
            {
                "id": "repo1",
                "name": "Test Repo",
                "url": "https://example.com/repo.git",
                "platform": "gitea",
                "auth_mode": "none",
                "permissions": {"write": True},
            }
        ]
    }
    (tmp_path / "settings.json").write_text(json.dumps(cfg))

    from unittest.mock import MagicMock, patch

    # Mock a single GitStorage (one repo)
    mock_store = MagicMock()
    mock_store.repo_id = "repo1"
    mock_store.get_categories.return_value = ["TestCat"]
    mock_store.get_entries.return_value = [
        {
            "repo_id": "repo1",
            "category": "TestCat",
            "slug": "hello",
            "title": "Hello",
            "pinned": False,
        }
    ]
    mock_store.search.return_value = [
        {"repo_id": "repo1", "category": "TestCat", "slug": "hello", "title": "Hello"}
    ]
    mock_store.get_entry.return_value = {
        "repo_id": "repo1",
        "category": "TestCat",
        "slug": "hello",
        "title": "Hello",
        "content": "# Hello\n\nWorld.",
        "pinned": False,
    }
    mock_store.save_entry.return_value = {
        "repo_id": "repo1",
        "category": "TestCat",
        "slug": "hello",
    }
    mock_store.update_entry.return_value = {
        "repo_id": "repo1",
        "category": "TestCat",
        "slug": "hello",
    }
    mock_store.delete_entry.return_value = True
    mock_store.toggle_pin.return_value = {
        "repo_id": "repo1",
        "category": "TestCat",
        "slug": "hello",
        "pinned": True,
    }

    mock_storage = MagicMock()
    mock_storage._stores = {"repo1": mock_store}
    mock_storage._cfg = cfg
    mock_storage.get_categories.return_value = [
        {"repo_id": "repo1", "repo_name": "Test Repo", "category": "TestCat"}
    ]
    mock_storage.get_entries.return_value = mock_store.get_entries.return_value
    mock_storage.search.return_value = mock_store.search.return_value
    mock_storage.get_entry.return_value = mock_store.get_entry.return_value
    mock_storage.save_entry.return_value = mock_store.save_entry.return_value
    mock_storage.update_entry.return_value = mock_store.update_entry.return_value
    mock_storage.delete_entry.return_value = True
    mock_storage.toggle_pin.return_value = mock_store.toggle_pin.return_value
    mock_storage.writable_repos.return_value = [{"id": "repo1", "name": "Test Repo"}]

    from core.state import reset_storage

    reset_storage()
    with (
        patch("core.state.get_storage", return_value=mock_storage),
        patch("modules.knowledge.router.get_storage", return_value=mock_storage),
        patch("main.get_storage", return_value=mock_storage),
    ):
        from fastapi.testclient import TestClient

        yield TestClient(_main_module.app, raise_server_exceptions=False), mock_storage


# ── Health ─────────────────────────────────────────────────────────────────


class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_returns_ok_status(self, client):
        r = client.get("/health")
        assert r.json()["status"] == "ok"

    def test_returns_version(self, client):
        r = client.get("/health")
        assert "version" in r.json()

    def test_returns_cache_field(self, client):
        r = client.get("/health")
        assert "cache" in r.json()


# ── Redis status ───────────────────────────────────────────────────────────


class TestRedisStatus:
    def test_returns_200(self, client):
        r = client.get("/api/redis-status")
        assert r.status_code == 200

    def test_returns_html_fragment(self, client):
        r = client.get("/api/redis-status")
        assert "cache-icon" in r.text


# ── Home dashboard ─────────────────────────────────────────────────────────


class TestHome:
    def test_returns_200_no_repos(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_returns_200_with_repo(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/")
        assert r.status_code == 200

    def test_shows_stats(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/")
        assert "Knowledge" in r.text

    def test_home_shows_motd_tile(self, client_with_repo):
        c, mock_storage = client_with_repo
        mock_storage._stores["repo1"].list_committed.return_value = []
        r = c.get("/")
        assert "Messages of the Day" in r.text

    def test_home_shows_potd_tile(self, client_with_repo):
        c, mock_storage = client_with_repo
        mock_storage._stores["repo1"].list_committed.return_value = []
        r = c.get("/")
        assert "Pictures of the Day" in r.text

    def test_home_motd_count(self, client_with_repo):
        c, mock_storage = client_with_repo
        mock_storage._stores["repo1"].list_committed.return_value = ["a.yaml", "b.yaml", "c.yaml"]
        r = c.get("/")
        assert r.status_code == 200
        # 3 YAML files → count 3 appears somewhere in the page
        assert "3" in r.text

    def test_home_potd_count_with_files(self, tmp_path, isolated_settings):
        import json
        from unittest.mock import MagicMock, patch
        from fastapi.testclient import TestClient
        from core.state import reset_storage

        reset_storage()
        potd_dir = tmp_path / "potd"
        potd_dir.mkdir()
        (potd_dir / "2026-05-01.jpg").write_bytes(b"\xff\xd8\xff")
        (potd_dir / "2026-05-02.png").write_bytes(b"\x89PNG")

        class _FakeGit:
            local_path = str(tmp_path)

            def list_committed(self, d):
                p = tmp_path / d
                return [f.name for f in p.iterdir()] if p.is_dir() else []

            def list_committed_recursive(self, d):
                import pathlib

                p = tmp_path / d
                return (
                    [str(f.relative_to(p)) for f in p.rglob("*") if f.is_file()]
                    if p.is_dir()
                    else []
                )

            def read_committed(self, p):
                return None

            def _pull(self):
                pass

            def _commit_and_push(self, m):
                pass

        fake_git = _FakeGit()
        mock_storage = MagicMock()
        mock_storage._stores = {"r1": fake_git}
        mock_storage._cfg = {"repos": [{"id": "r1", "permissions": {"write": True}}]}
        mock_storage.get_entries.return_value = []

        with (
            patch("main.get_storage", return_value=mock_storage),
            patch("core.state.get_storage", return_value=mock_storage),
        ):
            client = TestClient(_main_module.app, raise_server_exceptions=False)
            r = client.get("/")

        assert r.status_code == 200
        assert "Pictures of the Day" in r.text
        assert "2" in r.text


# ── Knowledge index ─────────────────────────────────────────────────────────


class TestKnowledgeIndex:
    def test_returns_200_no_repos(self, client):
        r = client.get("/knowledge/")
        assert r.status_code == 200

    def test_returns_200_with_repo(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/")
        assert r.status_code == 200

    def test_shows_entries(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/")
        assert "Hello" in r.text


# ── Search ─────────────────────────────────────────────────────────────────


class TestSearch:
    def test_empty_query_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/search?q=")
        assert r.status_code == 200

    def test_query_calls_storage(self, client_with_repo):
        c, mock = client_with_repo
        r = c.get("/knowledge/search?q=hello")
        assert r.status_code == 200
        mock._stores["repo1"].search.assert_called_once_with("hello")

    def test_category_filter_passed(self, client_with_repo):
        c, mock = client_with_repo
        r = c.get("/knowledge/search?q=hello&category=TestCat")
        assert r.status_code == 200
        # Category filtering is now done in Python after fetch; result still shown
        assert "Hello" in r.text


# ── New entry form ─────────────────────────────────────────────────────────


class TestNewEntryForm:
    def test_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/new")
        assert r.status_code == 200


# ── Create entry ───────────────────────────────────────────────────────────


class TestCreateEntry:
    def test_redirects_on_success(self, client_with_repo):
        c, _ = client_with_repo
        r = c.post(
            "/knowledge/entries",
            data={
                "repo_id": "repo1",
                "category": "TestCat",
                "new_category": "",
                "title": "My Entry",
                "content": "Some content here.",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/knowledge/entries/repo1/TestCat/hello" in r.headers["location"]

    def test_empty_content_redirects_with_error(self, client_with_repo):
        c, _ = client_with_repo
        r = c.post(
            "/knowledge/entries",
            data={
                "repo_id": "repo1",
                "category": "TestCat",
                "new_category": "",
                "title": "My Entry",
                "content": "",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/knowledge/new" in r.headers["location"]

    def test_no_storage_returns_503(self, client):
        r = client.post(
            "/knowledge/entries",
            data={
                "repo_id": "repo1",
                "category": "TestCat",
                "new_category": "",
                "title": "T",
                "content": "C",
            },
        )
        assert r.status_code == 503


# ── View entry ─────────────────────────────────────────────────────────────


class TestViewEntry:
    def test_returns_200_for_existing(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/entries/repo1/TestCat/hello")
        assert r.status_code == 200

    def test_returns_404_for_missing(self, client_with_repo):
        c, mock = client_with_repo
        mock.get_entry.return_value = None
        r = c.get("/knowledge/entries/repo1/TestCat/missing")
        assert r.status_code == 404

    def test_renders_markdown(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/entries/repo1/TestCat/hello")
        assert "<h1" in r.text or "Hello" in r.text


# ── Edit entry ─────────────────────────────────────────────────────────────


class TestEditEntry:
    def test_edit_form_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/entries/repo1/TestCat/hello/edit")
        assert r.status_code == 200

    def test_edit_form_404_on_missing(self, client_with_repo):
        c, mock = client_with_repo
        mock.get_entry.return_value = None
        r = c.get("/knowledge/entries/repo1/TestCat/missing/edit")
        assert r.status_code == 404

    def test_update_redirects_on_success(self, client_with_repo):
        c, _ = client_with_repo
        r = c.post(
            "/knowledge/entries/repo1/TestCat/hello/edit",
            data={
                "title": "Updated",
                "content": "New content.",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_update_empty_content_redirects_with_error(self, client_with_repo):
        c, _ = client_with_repo
        r = c.post(
            "/knowledge/entries/repo1/TestCat/hello/edit",
            data={
                "title": "Updated",
                "content": "",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" in r.headers["location"]

    def test_update_readonly_repo_returns_403(self, client_with_repo):
        c, _ = client_with_repo
        from core import settings_store

        cfg = settings_store.load()
        cfg["repos"][0]["permissions"]["write"] = False
        settings_store.save(cfg)
        r = c.post(
            "/knowledge/entries/repo1/TestCat/hello/edit",
            data={
                "title": "T",
                "content": "C",
            },
        )
        assert r.status_code == 403


# ── Delete entry ───────────────────────────────────────────────────────────


class TestDeleteEntry:
    def test_delete_redirects_to_home(self, client_with_repo):
        c, _ = client_with_repo
        r = c.post("/knowledge/entries/repo1/TestCat/hello/delete", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/knowledge"

    def test_delete_404_when_not_found(self, client_with_repo):
        c, mock = client_with_repo
        mock.delete_entry.return_value = False
        r = c.post("/knowledge/entries/repo1/TestCat/missing/delete")
        assert r.status_code == 404

    def test_delete_readonly_returns_403(self, client_with_repo):
        c, _ = client_with_repo
        from core import settings_store

        cfg = settings_store.load()
        cfg["repos"][0]["permissions"]["write"] = False
        settings_store.save(cfg)
        r = c.post("/knowledge/entries/repo1/TestCat/hello/delete")
        assert r.status_code == 403


# ── Pin ────────────────────────────────────────────────────────────────────


class TestPinEntry:
    def test_pin_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        r = c.post("/knowledge/entries/repo1/TestCat/hello/pin")
        assert r.status_code == 200

    def test_pin_returns_html_partial(self, client_with_repo):
        c, _ = client_with_repo
        r = c.post("/knowledge/entries/repo1/TestCat/hello/pin")
        assert "pin" in r.text.lower()

    def test_pin_readonly_returns_403(self, client_with_repo):
        c, _ = client_with_repo
        from core import settings_store

        cfg = settings_store.load()
        cfg["repos"][0]["permissions"]["write"] = False
        settings_store.save(cfg)
        r = c.post("/knowledge/entries/repo1/TestCat/hello/pin")
        assert r.status_code == 403


# ── Category view ──────────────────────────────────────────────────────────


class TestCategoryView:
    def test_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/category/TestCat")
        assert r.status_code == 200

    def test_page_param_accepted(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/knowledge/category/TestCat?page=1")
        assert r.status_code == 200


# ── Preview ────────────────────────────────────────────────────────────────


class TestPreview:
    def test_renders_markdown(self, client):
        r = client.post(
            "/api/preview",
            json={"content": "# Hello"},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert "<h1" in r.text

    def test_empty_content_returns_empty(self, client):
        r = client.post(
            "/api/preview", json={"content": ""}, headers={"Content-Type": "application/json"}
        )
        assert r.status_code == 200

    def test_xss_stripped(self, client):
        r = client.post(
            "/api/preview",
            json={"content": "<script>alert(1)</script>"},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert "<script>" not in r.text


# ── Settings ───────────────────────────────────────────────────────────────


class TestSettings:
    def test_settings_page_returns_200(self, client):
        r = client.get("/settings")
        assert r.status_code == 200

    def test_save_git_identity_redirects(self, client):
        r = client.post(
            "/settings/git-identity",
            data={
                "git_user_name": "Test User",
                "git_user_email": "test@example.com",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "saved=1" in r.headers["location"]

    def test_tls_mode_saved(self, client):
        r = client.post(
            "/settings/tls",
            data={
                "tls_mode": "http",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_add_repo_with_per_repo_identity(self, client):
        r = client.post(
            "/settings/repos",
            data={
                "name": "My Repo",
                "url": "https://example.com/repo.git",
                "platform": "gitea",
                "auth_mode": "none",
                "git_user_name": "Alice",
                "git_user_email": "alice@example.com",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        from core import settings_store

        repos = settings_store.load().get("repos", [])
        assert repos[0]["git_user_name"] == "Alice"
        assert repos[0]["git_user_email"] == "alice@example.com"

    def test_add_repo_with_gpg_fields_stored_encrypted(self, client):
        r = client.post(
            "/settings/repos",
            data={
                "name": "Signed Repo",
                "url": "https://example.com/repo.git",
                "platform": "github",
                "auth_mode": "pat",
                "gpg_key": "-----BEGIN PGP PRIVATE KEY BLOCK-----\nfakekey\n-----END PGP PRIVATE KEY BLOCK-----",
                "gpg_passphrase": "s3cret",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        from core import settings_store

        # Decrypted value should be intact
        repo = settings_store.load()["repos"][0]
        assert "fakekey" in repo["gpg_key"]
        assert repo["gpg_passphrase"] == "s3cret"

    def test_update_repo_keeps_existing_gpg_when_empty(self, client):
        client.post(
            "/settings/repos",
            data={
                "name": "Repo",
                "url": "https://example.com/r.git",
                "platform": "gitea",
                "auth_mode": "none",
                "gpg_key": "ORIGINAL_KEY",
                "gpg_passphrase": "pass",
            },
        )
        from core import settings_store

        repo_id = settings_store.load()["repos"][0]["id"]
        # Update without GPG fields — should keep existing
        r = client.post(
            f"/settings/repos/{repo_id}",
            data={
                "name": "Repo Updated",
                "url": "https://example.com/r.git",
                "platform": "gitea",
                "auth_mode": "none",
                "gpg_key": "",
                "gpg_passphrase": "",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        repo = settings_store.load()["repos"][0]
        assert repo["gpg_key"] == "ORIGINAL_KEY"
        assert repo["gpg_passphrase"] == "pass"


# ── Templates API ──────────────────────────────────────────────────────────


class TestTemplatesApi:
    def test_get_templates_returns_json(self, client):
        r = client.get("/api/templates")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_template(self, client):
        r = client.post(
            "/settings/templates",
            data={
                "name": "My Template",
                "content": "## Template content",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_delete_template(self, client):
        # Add first
        client.post(
            "/settings/templates",
            data={
                "name": "To Delete",
                "content": "x",
            },
        )
        from core import settings_store

        templates = settings_store.get_templates()
        assert templates
        tid = templates[0]["id"]
        r = client.post(f"/settings/templates/{tid}/delete", follow_redirects=False)
        assert r.status_code == 303


# ── Repo Toggle ────────────────────────────────────────────────────────────


class TestRepoToggle:
    def test_toggle_disables_repo(self, client):
        from core import settings_store

        settings_store.upsert_repo(
            {
                "id": "togtest",
                "name": "Toggle Test",
                "url": "https://x.com/r.git",
                "platform": "gitea",
                "auth_mode": "none",
                "enabled": True,
                "permissions": {"read": False, "write": False},
            }
        )
        r = client.post("/settings/repos/togtest/toggle")
        assert r.status_code == 200
        assert "Enable" in r.text  # now disabled → button says Enable
        repo = next(r for r in settings_store.load()["repos"] if r["id"] == "togtest")
        assert repo["enabled"] is False

    def test_toggle_re_enables_repo(self, client):
        from core import settings_store

        settings_store.upsert_repo(
            {
                "id": "togtest2",
                "name": "Toggle Test 2",
                "url": "https://x.com/r.git",
                "platform": "gitea",
                "auth_mode": "none",
                "enabled": False,
                "permissions": {"read": False, "write": False},
            }
        )
        r = client.post("/settings/repos/togtest2/toggle")
        assert r.status_code == 200
        assert "Disable" in r.text  # now enabled → button says Disable
        repo = next(r for r in settings_store.load()["repos"] if r["id"] == "togtest2")
        assert repo["enabled"] is True

    def test_disabled_repo_excluded_from_storage(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import importlib
        from core import settings_store as ss

        importlib.reload(ss)
        import json

        cfg = {
            "repos": [
                {
                    "id": "r1",
                    "name": "Active",
                    "url": "https://x.com/r1.git",
                    "platform": "gitea",
                    "auth_mode": "none",
                    "enabled": True,
                    "permissions": {"read": True, "write": True},
                },
                {
                    "id": "r2",
                    "name": "Inactive",
                    "url": "https://x.com/r2.git",
                    "platform": "gitea",
                    "auth_mode": "none",
                    "enabled": False,
                    "permissions": {"read": True, "write": True},
                },
            ]
        }
        (tmp_path / "settings.json").write_text(json.dumps(cfg))
        from unittest.mock import patch, MagicMock

        mock_git = MagicMock()
        with patch("core.storage.GitStorage.__init__", return_value=None) as mock_init:
            from core.storage import MultiRepoStorage

            store = MultiRepoStorage(cfg)
            ids = list(store._stores.keys())
            # Only enabled repos should be initialised
            for call in mock_init.call_args_list:
                assert call.kwargs.get("repo_id") != "r2"


# ── Metrics ────────────────────────────────────────────────────────────────


class TestMetrics:
    def test_disabled_by_default_returns_404(self, client):
        r = client.get("/metrics")
        assert r.status_code == 404

    def test_enabled_returns_200(self, client):
        from core import settings_store

        cfg = settings_store.load()
        cfg["metrics_enabled"] = True
        settings_store.save(cfg)
        r = client.get("/metrics")
        assert r.status_code == 200

    def test_prometheus_format(self, client):
        from core import settings_store

        cfg = settings_store.load()
        cfg["metrics_enabled"] = True
        settings_store.save(cfg)
        r = client.get("/metrics", headers={"Accept": "text/plain"})
        assert r.status_code == 200
        assert "daily_helper_" in r.text

    def test_json_format(self, client):
        from core import settings_store

        cfg = settings_store.load()
        cfg["metrics_enabled"] = True
        settings_store.save(cfg)
        r = client.get("/metrics", headers={"Accept": "application/json"})
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "version" in data


# ── Cache flush ────────────────────────────────────────────────────────────


class TestCacheFlush:
    def test_returns_200(self, client):
        r = client.post("/api/cache/flush")
        assert r.status_code == 200

    def test_returns_ok_html(self, client):
        r = client.post("/api/cache/flush")
        assert "flush" in r.text.lower() or "✓" in r.text


# ── Tasks API ──────────────────────────────────────────────────────────────


class TestTaskList:
    def test_returns_200_no_storage(self, client):
        r = client.get("/tasks")
        assert r.status_code == 200

    def test_returns_200_with_storage(self, client):
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.list_tasks.return_value = [
            {
                "id": "t1",
                "title": "Buy milk",
                "done": False,
                "priority": "medium",
                "due_date": "",
                "description": "",
                "recurring": "none",
            },
        ]
        with patch("modules.tasks.router._get_all_task_storages", return_value=[mock_ts]):
            r = client.get("/tasks")
        assert r.status_code == 200
        assert "Buy milk" in r.text

    def test_shows_no_repo_banner_when_unconfigured(self, client):
        from unittest.mock import patch

        with patch("modules.tasks.router._get_task_storage", return_value=None):
            r = client.get("/tasks")
        assert r.status_code == 200
        assert "No repository" in r.text or "Settings" in r.text


class TestTaskCreate:
    def test_create_redirects(self, client):
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.create_task.return_value = {"id": "t1", "title": "New"}
        with patch("modules.tasks.router._get_task_storage", return_value=mock_ts):
            r = client.post(
                "/tasks", data={"title": "New", "priority": "medium"}, follow_redirects=False
            )
        assert r.status_code == 303
        assert r.headers["location"].startswith("/tasks")

    def test_create_no_storage_returns_503(self, client):
        from unittest.mock import patch

        with patch("modules.tasks.router._get_task_storage", return_value=None):
            r = client.post("/tasks", data={"title": "X"}, follow_redirects=False)
        assert r.status_code == 503

    def test_toggle_returns_200(self, client):
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.toggle_done.return_value = {
            "id": "t1",
            "title": "T",
            "done": True,
            "priority": "medium",
            "due_date": "",
            "description": "",
            "recurring": "none",
        }
        with patch("modules.tasks.router._find_task_storage", return_value=mock_ts):
            r = client.post("/tasks/t1/toggle")
        assert r.status_code == 200

    def test_delete_redirects(self, client):
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.delete_task.return_value = True
        with patch("modules.tasks.router._find_task_storage", return_value=mock_ts):
            r = client.post("/tasks/t1/delete", follow_redirects=False)
        assert r.status_code == 303


# ── Vacations API ──────────────────────────────────────────────────────────


class TestVacationList:
    def test_returns_200_no_storage(self, client):
        r = client.get("/vacations")
        assert r.status_code == 200

    def test_returns_200_with_year_param(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.get_account.return_value = {
            "year": 2027,
            "total_days": 30,
            "used_days": 0,
            "planned_days": 0,
            "remaining_days": 30,
            "remaining_after_planned": 30,
            "entries": [],
        }
        with patch("modules.vacations.router._get_vacation_storage", return_value=mock_vs):
            r = client.get("/vacations?year=2027")
        assert r.status_code == 200
        assert "2027" in r.text


class TestVacationCreate:
    def test_create_redirects(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.create_entry.return_value = {"id": "v1"}
        with patch("modules.vacations.router._get_vacation_storage", return_value=mock_vs):
            r = client.post(
                "/vacations",
                data={
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-10",
                },
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == "/vacations"

    def test_create_no_storage_returns_503(self, client):
        from unittest.mock import patch

        with patch("modules.vacations.router._get_vacation_storage", return_value=None):
            r = client.post(
                "/vacations",
                data={
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-10",
                },
                follow_redirects=False,
            )
        assert r.status_code == 503

    def test_status_update_redirects(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.update_status.return_value = {
            "id": "v1",
            "start_date": "2026-07-01",
            "end_date": "2026-07-10",
            "status": "approved",
        }
        mock_vs.get_account.return_value = {
            "year": 2026,
            "total_days": 30,
            "used_days": 5,
            "planned_days": 0,
            "remaining_days": 25,
            "remaining_after_planned": 25,
            "entries": [],
        }
        with (
            patch("modules.vacations.router._find_storage", return_value=mock_vs),
            patch("modules.vacations.router._get_vacation_storage", return_value=mock_vs),
            patch("modules.vacations.router._list_all_entries", return_value=[]),
            patch(
                "modules.vacations.router.get_storage",
                return_value=MagicMock(get_categories=lambda: []),
            ),
        ):
            r = client.post("/vacations/v1/status", data={"status": "approved"})
        assert r.status_code == 200

    def test_delete_redirects(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.delete_entry.return_value = True
        with patch("modules.vacations.router._find_storage", return_value=mock_vs):
            r = client.post("/vacations/v1/delete", follow_redirects=False)
        assert r.status_code == 303


class TestVacationCSVExport:
    def test_returns_csv(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.list_entries.return_value = [
            {
                "id": "v1",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
                "status": "approved",
                "note": "Summer",
            },
        ]
        with patch(
            "modules.vacations.router._list_all_entries",
            return_value=mock_vs.list_entries.return_value,
        ):
            r = client.get("/vacations/export.csv?year=2026")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "v1" in r.text
        assert "Summer" in r.text

    def test_csv_header_row(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.list_entries.return_value = []
        with patch("modules.vacations.router._list_all_entries", return_value=[]):
            r = client.get("/vacations/export.csv")
        assert "start_date" in r.text
        assert "end_date" in r.text
        assert "status" in r.text


class TestVacationICSExport:
    def test_returns_ics(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.get_entry.return_value = {
            "id": "v1",
            "start_date": "2026-07-01",
            "end_date": "2026-07-10",
            "status": "approved",
            "note": "Summer break",
        }
        with patch("modules.vacations.router._find_storage", return_value=mock_vs):
            r = client.get("/vacations/v1/export.ics")
        assert r.status_code == 200
        assert "text/calendar" in r.headers["content-type"]
        assert "BEGIN:VCALENDAR" in r.text
        assert "DTSTART;VALUE=DATE:20260701" in r.text
        assert "DTEND;VALUE=DATE:20260711" in r.text
        assert "Summer break" in r.text

    def test_not_found_returns_404(self, client):
        from unittest.mock import patch

        with patch("modules.vacations.router._find_storage", return_value=None):
            r = client.get("/vacations/missing/export.ics")
        assert r.status_code == 404


# ── Settings Export / Import ───────────────────────────────────────────────


class TestSettingsExport:
    def test_returns_encrypted_file(self, client):
        from core.crypto import is_encrypted, decrypt_export
        import json

        r = client.post("/settings/export", data={"password": "testpw"})
        assert r.status_code == 200
        assert "application/octet-stream" in r.headers["content-type"]
        assert is_encrypted(r.content)
        data = json.loads(decrypt_export(r.content, "testpw"))
        assert "repos" in data

    def test_filename_header(self, client):
        r = client.post("/settings/export", data={"password": "testpw"})
        assert "daily-helper-settings.dhbak" in r.headers.get("content-disposition", "")


class TestBackupToRepo:
    def test_no_password_returns_400(self, client):
        r = client.post(
            "/settings/backup-to-repo", data={"backup_password": "", "backup_repo_id": "somerepo"}
        )
        assert r.status_code == 400
        assert "flash-error" in r.text

    def test_no_repo_returns_400(self, client):
        r = client.post(
            "/settings/backup-to-repo", data={"backup_password": "pw", "backup_repo_id": ""}
        )
        assert r.status_code == 400
        assert "flash-error" in r.text

    def test_unknown_repo_returns_400(self, client):
        r = client.post(
            "/settings/backup-to-repo",
            data={"backup_password": "pw", "backup_repo_id": "nonexistent"},
        )
        assert r.status_code == 400
        assert "flash-error" in r.text


class TestSettingsImport:
    def test_import_replaces_settings(self, client):
        import io

        payload = json.dumps({"repos": [], "git_user_name": "Imported User"})
        r = client.post(
            "/settings/import",
            files={"file": ("settings.json", io.BytesIO(payload.encode()), "application/json")},
            follow_redirects=False,
        )
        assert r.status_code == 303
        from core import settings_store

        assert settings_store.load()["git_user_name"] == "Imported User"

    def test_import_invalid_json_redirects_with_error(self, client):
        import io

        r = client.post(
            "/settings/import",
            files={"file": ("bad.json", io.BytesIO(b"not json"), "application/json")},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" in r.headers["location"].lower()


# ── Module Enable/Disable ─────────────────────────────────────────────────


class TestModuleSettings:
    def test_all_modules_enabled_by_default(self, client):
        from core import settings_store

        assert settings_store.is_module_enabled("knowledge") is True
        assert settings_store.is_module_enabled("tasks") is True
        assert settings_store.is_module_enabled("vacations") is True

    def test_save_modules_succeeds(self, client):
        r = client.post("/settings/modules", data={"knowledge": "on", "tasks": "on"})
        assert r.status_code in (200, 303)

    def test_disabled_module_stores_false(self, client):
        from core import settings_store

        client.post("/settings/modules", data={"knowledge": "on"})
        assert settings_store.is_module_enabled("tasks") is False
        assert settings_store.is_module_enabled("vacations") is False
        assert settings_store.is_module_enabled("knowledge") is True

    def test_disabled_tasks_returns_404(self, client):
        from core import settings_store

        settings_store.set_modules_enabled({"tasks": False})
        r = client.get("/tasks")
        assert r.status_code == 404

    def test_disabled_vacations_returns_404(self, client):
        from core import settings_store

        settings_store.set_modules_enabled({"vacations": False})
        r = client.get("/vacations")
        assert r.status_code == 404

    def test_disabled_knowledge_returns_404(self, client):
        from core import settings_store

        settings_store.set_modules_enabled({"knowledge": False})
        r = client.get("/knowledge")
        assert r.status_code == 404

    def test_reenabled_module_accessible(self, client):
        from core import settings_store

        settings_store.set_modules_enabled({"tasks": False})
        assert client.get("/tasks").status_code == 404
        settings_store.set_modules_enabled({"tasks": True})
        assert client.get("/tasks").status_code == 200


# ── ICS Profile Settings ───────────────────────────────────────────────────


class TestICSProfileSettings:
    def test_add_profile_redirects(self, client):
        r = client.post(
            "/settings/ics-profiles",
            data={
                "name": "Team Cal",
                "recipients": "boss@firm.de",
                "show_as": "free",
                "all_day": "on",
                "subject": "Vacation {start_date}",
                "body": "{note}",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_add_profile_persisted(self, client):
        client.post(
            "/settings/ics-profiles",
            data={
                "name": "Team Cal",
                "show_as": "oof",
                "all_day": "on",
                "subject": "Urlaub",
                "body": "",
            },
        )
        from core import settings_store

        profiles = settings_store.get_ics_profiles()
        assert any(p["name"] == "Team Cal" for p in profiles)

    def test_add_profile_timed_stores_times(self, client):
        client.post(
            "/settings/ics-profiles",
            data={
                "name": "Blocker",
                "show_as": "oof",
                "start_time": "08:05",
                "end_time": "16:35",
                "subject": "Außer Haus",
                "body": "",
            },
        )
        from core import settings_store

        profiles = settings_store.get_ics_profiles()
        blocker = next(p for p in profiles if p["name"] == "Blocker")
        assert blocker["all_day"] is False
        assert blocker["start_time"] == "08:05"
        assert blocker["end_time"] == "16:35"

    def test_add_profile_recipients_parsed(self, client):
        client.post(
            "/settings/ics-profiles",
            data={
                "name": "Multi",
                "show_as": "free",
                "all_day": "on",
                "recipients_required": "a@x.de, b@x.de",
                "subject": "S",
                "body": "",
            },
        )
        from core import settings_store

        profiles = settings_store.get_ics_profiles()
        p = next(x for x in profiles if x["name"] == "Multi")
        assert "a@x.de" in p["recipients_required"]
        assert "b@x.de" in p["recipients_required"]

    def test_delete_profile_redirects(self, client):
        from core import settings_store

        p = settings_store.upsert_ics_profile(
            {"name": "Del", "show_as": "oof", "all_day": True, "subject": "X", "body": ""}
        )
        r = client.post(f"/settings/ics-profiles/{p['id']}/delete", follow_redirects=False)
        assert r.status_code == 303

    def test_delete_profile_removes_it(self, client):
        from core import settings_store

        p = settings_store.upsert_ics_profile(
            {"name": "Gone", "show_as": "oof", "all_day": True, "subject": "X", "body": ""}
        )
        client.post(f"/settings/ics-profiles/{p['id']}/delete")
        profiles = settings_store.get_ics_profiles()
        assert not any(x["id"] == p["id"] for x in profiles)

    def test_edit_profile_updates_fields(self, client):
        from core import settings_store

        p = settings_store.upsert_ics_profile(
            {"name": "Before", "show_as": "oof", "all_day": True, "subject": "S", "body": ""}
        )
        client.post(
            f"/settings/ics-profiles/{p['id']}/edit",
            data={
                "name": "After",
                "show_as": "free",
                "subject": "Updated",
                "body": "desc",
                "recipients_required": "x@y.de",
                "category": "Blue",
            },
        )
        updated = settings_store.get_ics_profile(p["id"])
        assert updated["name"] == "After"
        assert updated["show_as"] == "free"
        assert updated["subject"] == "Updated"
        assert updated["all_day"] is False
        assert "x@y.de" in updated["recipients_required"]


# ── ICS Export with Profile ────────────────────────────────────────────────


class TestVacationICSExportWithProfile:
    _ENTRY = {
        "id": "v1",
        "start_date": "2026-07-01",
        "end_date": "2026-07-03",
        "status": "approved",
        "note": "Summer",
    }

    def _mock_client(self, client):
        from unittest.mock import patch, MagicMock

        mock_vs = MagicMock()
        mock_vs.get_entry.return_value = self._ENTRY
        return patch("modules.vacations.router._find_storage", return_value=mock_vs)

    def _add_profile(self, **kwargs):
        from core import settings_store

        defaults = {
            "name": "Test",
            "show_as": "oof",
            "all_day": True,
            "subject": "Vacation {start_date}",
            "body": "{note}",
        }
        defaults.update(kwargs)
        return settings_store.upsert_ics_profile(defaults)

    def test_export_with_profile_returns_ics(self, client):
        p = self._add_profile()
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert r.status_code == 200
        assert "text/calendar" in r.headers["content-type"]
        assert "BEGIN:VCALENDAR" in r.text

    def test_export_unknown_profile_returns_404(self, client):
        with self._mock_client(client):
            r = client.get("/vacations/v1/export.ics?profile=doesnotexist")
        assert r.status_code == 404

    def test_export_without_profile_still_works(self, client):
        with self._mock_client(client):
            r = client.get("/vacations/v1/export.ics")
        assert r.status_code == 200
        assert "BEGIN:VCALENDAR" in r.text

    def test_export_allday_has_date_dtstart(self, client):
        p = self._add_profile(all_day=True)
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert "DTSTART;VALUE=DATE:" in r.text

    def test_export_timed_has_tzid_dtstart(self, client):
        p = self._add_profile(all_day=False, start_time="08:05", end_time="16:35")
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert "DTSTART;TZID=Europe/Berlin:" in r.text
        assert "VTIMEZONE" in r.text

    def test_export_free_has_transparent(self, client):
        p = self._add_profile(show_as="free")
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert "TRANSP:TRANSPARENT" in r.text
        assert "BUSYSTATUS:FREE" in r.text

    def test_export_oof_has_opaque(self, client):
        p = self._add_profile(show_as="oof")
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert "TRANSP:OPAQUE" in r.text
        assert "BUSYSTATUS:OOF" in r.text

    def test_export_with_recipients(self, client):
        p = self._add_profile(recipients=["boss@firm.de", "team@firm.de"])
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert "ATTENDEE" in r.text
        assert "boss@firm.de" in r.text
        assert "RSVP=FALSE" in r.text

    def test_export_with_category(self, client):
        p = self._add_profile(category="Grüne Kategorie")
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert "CATEGORIES:Grüne Kategorie" in r.text

    def test_export_subject_placeholder_resolved(self, client):
        p = self._add_profile(subject="Urlaub ab {start_date}")
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert "Urlaub ab 2026-07-01" in r.text

    def test_export_one_vevent_per_workday(self, client):
        # 2026-07-01 to 2026-07-03 = Wed, Thu, Fri (3 work days)
        p = self._add_profile(all_day=True)
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        assert r.text.count("BEGIN:VEVENT") == 3

    def test_profile_filename_used(self, client):
        p = self._add_profile(name="Team Kalender")
        with self._mock_client(client):
            r = client.get(f"/vacations/v1/export.ics?profile={p['id']}")
        cd = r.headers.get("content-disposition", "")
        assert "team-kalender_" in cd
        assert ".ics" in cd


# ── Operations ─────────────────────────────────────────────────────────────


class TestOperations:
    """Tests for /operations — copy/move content between repos."""

    @pytest.fixture()
    def two_repo_client(self, tmp_path, monkeypatch):
        """Client with two mock repos configured."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.delenv("SECRET_KEY", raising=False)

        import importlib
        from core import settings_store

        importlib.reload(settings_store)
        _main_module.settings_store = settings_store

        cfg = {
            "repos": [
                {
                    "id": "repo1",
                    "name": "Repo One",
                    "url": "https://example.com/r1.git",
                    "platform": "gitea",
                    "auth_mode": "none",
                    "permissions": {"write": True},
                },
                {
                    "id": "repo2",
                    "name": "Repo Two",
                    "url": "https://example.com/r2.git",
                    "platform": "gitea",
                    "auth_mode": "none",
                    "permissions": {"write": True},
                },
            ]
        }
        (tmp_path / "settings.json").write_text(json.dumps(cfg))

        from unittest.mock import MagicMock, patch

        def _make_store(repo_id):
            s = MagicMock()
            s.repo_id = repo_id
            s.local_path = str(tmp_path / repo_id)
            s.knowledge_path = tmp_path / repo_id / "knowledge"
            s.get_entries.return_value = [
                {"category": "Cat", "slug": "entry1", "title": "Entry One", "pinned": False}
            ]
            return s

        mock_store1 = _make_store("repo1")
        mock_store2 = _make_store("repo2")

        mock_storage = MagicMock()
        mock_storage._stores = {"repo1": mock_store1, "repo2": mock_store2}
        mock_storage._cfg = cfg

        from core.state import reset_storage

        reset_storage()
        with (
            patch("core.state.get_storage", return_value=mock_storage),
            patch("modules.operations.router.get_storage", return_value=mock_storage),
        ):
            from fastapi.testclient import TestClient

            yield (
                TestClient(_main_module.app, raise_server_exceptions=False),
                mock_storage,
                mock_store1,
                mock_store2,
            )

    def test_operations_hidden_with_one_repo(self, client):
        r = client.get("/operations")
        # With 0 repos configured get_repo_count() == 0, page renders but shows empty state
        assert r.status_code == 200

    def test_operations_index_returns_200(self, two_repo_client):
        c, *_ = two_repo_client
        r = c.get("/operations")
        assert r.status_code == 200
        assert "Repo One" in r.text
        assert "Repo Two" in r.text

    def test_operations_shows_items_for_source(self, two_repo_client):
        c, *_ = two_repo_client
        r = c.get("/operations?src=repo1&type=knowledge")
        assert r.status_code == 200
        assert "Entry One" in r.text

    def test_execute_same_src_dst_returns_error(self, two_repo_client):
        c, *_ = two_repo_client
        r = c.post(
            "/operations/execute",
            data={
                "src_repo": "repo1",
                "dst_repo": "repo1",
                "content_type": "knowledge",
                "action": "copy",
                "items": ["Cat/entry1"],
            },
            follow_redirects=True,
        )
        assert "Source and target must be different" in r.text

    def test_execute_no_items_returns_error(self, two_repo_client):
        c, *_ = two_repo_client
        r = c.post(
            "/operations/execute",
            data={
                "src_repo": "repo1",
                "dst_repo": "repo2",
                "content_type": "knowledge",
                "action": "copy",
            },
            follow_redirects=True,
        )
        assert "No items selected" in r.text

    def test_execute_copy_calls_commit(self, two_repo_client, tmp_path):
        c, _, mock_store1, mock_store2 = two_repo_client
        # Create the source file so shutil.copy2 can find it
        src_dir = tmp_path / "repo1" / "knowledge" / "Cat"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "entry1.md").write_text("# Entry One")

        r = c.post(
            "/operations/execute",
            data={
                "src_repo": "repo1",
                "dst_repo": "repo2",
                "content_type": "knowledge",
                "action": "copy",
                "items": ["Cat/entry1"],
            },
            follow_redirects=True,
        )
        assert r.status_code == 200
        mock_store2._commit_and_push.assert_called_once()
        # copy should NOT delete from source
        mock_store1._commit_and_push.assert_not_called()


# ── Mail Templates ──────────────────────────────────────────────────────────


class TestMailTemplates:
    """Tests for /mail-templates CRUD."""

    def test_list_returns_200(self, client_with_repo):
        c, mock = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.list_templates.return_value = []
        with patch("modules.mail_templates.router._get_storage", return_value=mock_ts):
            r = c.get("/mail-templates")
        assert r.status_code == 200

    def test_list_shows_templates(self, client_with_repo):
        c, mock = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.list_templates.return_value = [
            {
                "id": "abc1",
                "name": "Welcome Mail",
                "to": "a@b.de",
                "cc": "",
                "subject": "Hi",
                "body": "Hello",
            }
        ]
        with patch("modules.mail_templates.router._get_all_storages", return_value=[mock_ts]):
            r = c.get("/mail-templates")
        assert "Welcome Mail" in r.text
        assert "a@b.de" in r.text

    def test_new_form_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/mail-templates/new")
        assert r.status_code == 200

    def test_create_redirects(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.create_template.return_value = {"id": "x1", "name": "Test"}
        with patch("modules.mail_templates.router._get_storage", return_value=mock_ts):
            r = c.post(
                "/mail-templates/new",
                data={"name": "Test", "to": "a@b.de", "cc": "", "subject": "Hi", "body": "Body"},
            )
        assert r.status_code in (200, 303)
        mock_ts.create_template.assert_called_once()

    def test_create_requires_name(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        with patch("modules.mail_templates.router._get_storage", return_value=mock_ts):
            r = c.post(
                "/mail-templates/new",
                data={"name": "", "to": "", "cc": "", "subject": "", "body": ""},
            )
        assert r.status_code in (400, 422)

    def test_edit_form_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.get_template.return_value = {
            "id": "abc1",
            "name": "T",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "",
        }
        with patch("modules.mail_templates.router._find_storage", return_value=mock_ts):
            r = c.get("/mail-templates/abc1/edit")
        assert r.status_code == 200

    def test_edit_form_404_on_missing(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.get_template.return_value = None
        with patch("modules.mail_templates.router._get_storage", return_value=mock_ts):
            r = c.get("/mail-templates/nope/edit")
        assert r.status_code == 404

    def test_update_calls_storage(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.update_template.return_value = {"id": "abc1", "name": "Updated"}
        with (
            patch("modules.mail_templates.router._find_storage", return_value=mock_ts),
            patch("modules.mail_templates.router._get_all_storages", return_value=[mock_ts]),
        ):
            r = c.post(
                "/mail-templates/abc1/edit",
                data={"name": "Updated", "to": "", "cc": "", "subject": "", "body": ""},
            )
        assert r.status_code in (200, 303)
        mock_ts.update_template.assert_called_once()

    def test_delete_calls_storage(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        with (
            patch("modules.mail_templates.router._find_storage", return_value=mock_ts),
            patch("modules.mail_templates.router._get_all_storages", return_value=[mock_ts]),
        ):
            r = c.post("/mail-templates/abc1/delete")
        assert r.status_code in (200, 303)
        mock_ts.delete_template.assert_called_once_with("abc1")

    def test_disabled_module_returns_404(self, client_with_repo):
        c, _ = client_with_repo
        from core import settings_store

        settings_store.set_modules_enabled({"mail_templates": False})
        r = c.get("/mail-templates")
        settings_store.set_modules_enabled({"mail_templates": True})
        assert r.status_code == 404


# ── Ticket Templates ─────────────────────────────────────────────────────────


class TestTicketTemplates:
    """Tests for /ticket-templates CRUD."""

    def test_list_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.list_templates.return_value = []
        with patch("modules.ticket_templates.router._get_storage", return_value=mock_ts):
            r = c.get("/ticket-templates")
        assert r.status_code == 200

    def test_list_shows_templates(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.list_templates.return_value = [
            {
                "id": "t1",
                "name": "Bug Report",
                "description": "Report a bug",
                "body": "Steps to reproduce",
            }
        ]
        with patch("modules.ticket_templates.router._get_all_storages", return_value=[mock_ts]):
            r = c.get("/ticket-templates")
        assert "Bug Report" in r.text
        assert "Report a bug" in r.text

    def test_new_form_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        r = c.get("/ticket-templates/new")
        assert r.status_code == 200

    def test_create_redirects(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.create_template.return_value = {"id": "t1", "name": "Bug"}
        with patch("modules.ticket_templates.router._get_storage", return_value=mock_ts):
            r = c.post(
                "/ticket-templates/new",
                data={"name": "Bug", "description": "A bug", "body": "Repro steps"},
            )
        assert r.status_code in (200, 303)
        mock_ts.create_template.assert_called_once()

    def test_create_requires_name(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        with patch("modules.ticket_templates.router._get_storage", return_value=mock_ts):
            r = c.post("/ticket-templates/new", data={"name": "", "description": "", "body": ""})
        assert r.status_code in (400, 422)

    def test_edit_form_returns_200(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.get_template.return_value = {
            "id": "t1",
            "name": "Bug",
            "description": "",
            "body": "",
        }
        with patch("modules.ticket_templates.router._find_storage", return_value=mock_ts):
            r = c.get("/ticket-templates/t1/edit")
        assert r.status_code == 200

    def test_edit_form_404_on_missing(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.get_template.return_value = None
        with patch("modules.ticket_templates.router._get_storage", return_value=mock_ts):
            r = c.get("/ticket-templates/nope/edit")
        assert r.status_code == 404

    def test_update_calls_storage(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        mock_ts.update_template.return_value = {"id": "t1", "name": "Updated"}
        with (
            patch("modules.ticket_templates.router._find_storage", return_value=mock_ts),
            patch("modules.ticket_templates.router._get_all_storages", return_value=[mock_ts]),
        ):
            r = c.post(
                "/ticket-templates/t1/edit", data={"name": "Updated", "description": "", "body": ""}
            )
        assert r.status_code in (200, 303)
        mock_ts.update_template.assert_called_once()

    def test_delete_calls_storage(self, client_with_repo):
        c, _ = client_with_repo
        from unittest.mock import patch, MagicMock

        mock_ts = MagicMock()
        with (
            patch("modules.ticket_templates.router._find_storage", return_value=mock_ts),
            patch("modules.ticket_templates.router._get_all_storages", return_value=[mock_ts]),
        ):
            r = c.post("/ticket-templates/t1/delete")
        assert r.status_code in (200, 303)
        mock_ts.delete_template.assert_called_once_with("t1")

    def test_disabled_module_returns_404(self, client_with_repo):
        c, _ = client_with_repo
        from core import settings_store

        settings_store.set_modules_enabled({"ticket_templates": False})
        r = c.get("/ticket-templates")
        settings_store.set_modules_enabled({"ticket_templates": True})
        assert r.status_code == 404
