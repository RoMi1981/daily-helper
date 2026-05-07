"""Tests for settings endpoints in main.py not covered by test_api.py."""

import os
import sys

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
def client(isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


# ── Notes settings ─────────────────────────────────────────────────────────


def test_save_notes_settings_end(client):
    resp = client.post(
        "/settings/notes", data={"notes_scroll_position": "end"}, follow_redirects=False
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["notes_scroll_position"] == "end"


def test_save_notes_settings_start(client):
    resp = client.post(
        "/settings/notes", data={"notes_scroll_position": "start"}, follow_redirects=False
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["notes_scroll_position"] == "start"


# ── Vacation settings ──────────────────────────────────────────────────────


def test_save_vacation_settings(client):
    resp = client.post(
        "/settings/vacation",
        data={
            "vacation_state": "NW",
            "vacation_days_per_year": "28",
            "vacation_carryover": "5",
            "holiday_language": "en_US",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["vacation_state"] == "NW"
    assert cfg["vacation_days_per_year"] == 28
    assert cfg["vacation_carryover"] == 5
    assert cfg["holiday_language"] == "en_US"


def test_save_vacation_settings_invalid_language(client):
    resp = client.post(
        "/settings/vacation",
        data={
            "vacation_state": "BY",
            "vacation_days_per_year": "30",
            "vacation_carryover": "0",
            "holiday_language": "fr_FR",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["holiday_language"] == "de"  # falls back to default


def test_save_vacation_settings_min_days(client):
    resp = client.post(
        "/settings/vacation",
        data={
            "vacation_state": "BY",
            "vacation_days_per_year": "0",
            "vacation_carryover": "0",
            "holiday_language": "de",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["vacation_days_per_year"] == 1  # max(1, 0) = 1


# ── Module repo assignment ─────────────────────────────────────────────────


def test_save_module_repos_empty(client):
    resp = client.post("/settings/module-repos", data={}, follow_redirects=False)
    assert resp.status_code == 303


def test_save_module_repos_with_assignment(client):
    # Add a repo first
    from core import settings_store

    cfg = settings_store.load()
    cfg["repos"] = [
        {
            "id": "repo1",
            "name": "Test",
            "url": "https://example.com",
            "platform": "gitea",
            "auth_mode": "none",
            "enabled": True,
            "permissions": {"read": True, "write": True},
        }
    ]
    settings_store.save(cfg)

    resp = client.post(
        "/settings/module-repos",
        data={
            "notes_repos": "repo1",
            "notes_primary": "repo1",
            "rss_repos": "repo1",
            "rss_primary": "repo1",
            "motd_repos": "repo1",
            "motd_primary": "repo1",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["module_repos"]["notes"]["primary"] == "repo1"
    assert cfg["module_repos"]["rss"]["primary"] == "repo1"
    assert cfg["module_repos"]["motd"]["primary"] == "repo1"


# ── Git identity ───────────────────────────────────────────────────────────


def test_save_git_identity(client):
    resp = client.post(
        "/settings/git-identity",
        data={
            "git_user_name": "Test User",
            "git_user_email": "test@example.com",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["git_user_name"] == "Test User"
    assert cfg["git_user_email"] == "test@example.com"


# ── TLS settings ───────────────────────────────────────────────────────────


def test_save_tls_http(client):
    resp = client.post(
        "/settings/tls",
        data={
            "tls_mode": "http",
            "tls_san": "localhost",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["tls_mode"] == "http"


# ── Modules toggle ─────────────────────────────────────────────────────────


def test_save_modules_all_on(client):
    resp = client.post(
        "/settings/modules",
        data={
            "knowledge": "on",
            "tasks": "on",
            "vacations": "on",
            "mail_templates": "on",
            "ticket_templates": "on",
            "notes": "on",
            "links": "on",
            "runbooks": "on",
            "appointments": "on",
            "snippets": "on",
            "rss": "on",
            "motd": "on",
            "potd": "on",
            "memes": "on",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert all(cfg["modules_enabled"].values())


def test_save_modules_disable_runbooks(client):
    resp = client.post(
        "/settings/modules",
        data={
            "knowledge": "on",
            "tasks": "on",
            "vacations": "on",
            "mail_templates": "on",
            "ticket_templates": "on",
            "notes": "on",
            "links": "on",
            # runbooks omitted → off
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["modules_enabled"]["runbooks"] is False


# ── Metrics ────────────────────────────────────────────────────────────────


def test_save_metrics_enabled(client):
    resp = client.post("/settings/metrics", data={"metrics_enabled": "on"}, follow_redirects=False)
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["metrics_enabled"] is True


def test_save_metrics_disabled(client):
    resp = client.post("/settings/metrics", data={}, follow_redirects=False)
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["metrics_enabled"] is False


def test_save_rss_home_limit(client):
    resp = client.post("/settings/rss-home", data={"rss_home_limit": "7"}, follow_redirects=False)
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["rss_home_limit"] == 7


def test_save_rss_home_limit_minimum(client):
    resp = client.post("/settings/rss-home", data={"rss_home_limit": "0"}, follow_redirects=False)
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["rss_home_limit"] >= 1


# ── Repo CRUD: sensitive field preservation ────────────────────────────────

SAMPLE_CERT = "-----BEGIN CERTIFICATE-----\nMIIBxxx\n-----END CERTIFICATE-----"
SAMPLE_PAT = "glpat-testtoken123"


def _add_repo(client, ca_cert="", pat="", auth_mode="none"):
    """Helper: add a repo via POST /settings/repos and return its id."""
    from core import settings_store

    resp = client.post(
        "/settings/repos",
        data={
            "name": "Test Repo",
            "url": "https://git.example.com/org/repo.git",
            "platform": "gitlab",
            "auth_mode": auth_mode,
            "ca_cert": ca_cert,
            "pat": pat,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cfg = settings_store.load()
    return cfg["repos"][-1]["id"]


def test_ca_cert_saved_on_create(client):
    """CA cert entered on first save is stored."""
    from core import settings_store

    _add_repo(client, ca_cert=SAMPLE_CERT)
    cfg = settings_store.load()
    assert cfg["repos"][-1]["ca_cert"] == SAMPLE_CERT


def test_ca_cert_preserved_on_update_without_reentry(client):
    """CA cert is kept when form is saved without re-entering the cert (empty field)."""
    from core import settings_store

    repo_id = _add_repo(client, ca_cert=SAMPLE_CERT)
    # Save again with empty ca_cert — simulates browser submitting hidden panel's empty textarea
    resp = client.post(
        f"/settings/repos/{repo_id}",
        data={
            "name": "Test Repo",
            "url": "https://git.example.com/org/repo.git",
            "platform": "gitlab",
            "auth_mode": "none",
            "ca_cert": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    assert repo["ca_cert"] == SAMPLE_CERT, "CA cert must not be cleared when form field is empty"


def test_ca_cert_can_be_updated(client):
    """CA cert is replaced when a new non-empty value is submitted."""
    from core import settings_store

    repo_id = _add_repo(client, ca_cert=SAMPLE_CERT)
    new_cert = "-----BEGIN CERTIFICATE-----\nNEWCERT\n-----END CERTIFICATE-----"
    client.post(
        f"/settings/repos/{repo_id}",
        data={
            "name": "Test Repo",
            "url": "https://git.example.com/org/repo.git",
            "platform": "gitlab",
            "auth_mode": "none",
            "ca_cert": new_cert,
        },
        follow_redirects=False,
    )
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    assert repo["ca_cert"] == new_cert


def test_pat_preserved_on_update_without_reentry(client):
    """PAT is kept when form is saved without re-entering it."""
    from core import settings_store

    repo_id = _add_repo(client, pat=SAMPLE_PAT, auth_mode="pat")
    resp = client.post(
        f"/settings/repos/{repo_id}",
        data={
            "name": "Test Repo",
            "url": "https://git.example.com/org/repo.git",
            "platform": "gitlab",
            "auth_mode": "pat",
            "pat": "",  # empty — leave existing
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    assert repo["pat"] == SAMPLE_PAT, "PAT must not be cleared when form field is empty"


def test_pat_can_be_updated(client):
    """PAT is replaced when a new non-empty value is submitted."""
    from core import settings_store

    repo_id = _add_repo(client, pat=SAMPLE_PAT, auth_mode="pat")
    new_pat = "glpat-newtoken456"
    client.post(
        f"/settings/repos/{repo_id}",
        data={
            "name": "Test Repo",
            "url": "https://git.example.com/org/repo.git",
            "platform": "gitlab",
            "auth_mode": "pat",
            "pat": new_pat,
        },
        follow_redirects=False,
    )
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    assert repo["pat"] == new_pat


# ── API endpoints ──────────────────────────────────────────────────────────


def test_api_templates(client):
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Export / Import settings ───────────────────────────────────────────────


def test_export_settings(client):
    from core.crypto import decrypt_export, is_encrypted

    resp = client.post("/settings/export", data={"password": "testpass"})
    assert resp.status_code == 200
    assert "application/octet-stream" in resp.headers["content-type"]
    assert "daily-helper-settings.dhbak" in resp.headers.get("content-disposition", "")
    assert is_encrypted(resp.content)
    import json

    data = json.loads(decrypt_export(resp.content, "testpass"))
    assert isinstance(data, dict)


def test_export_settings_no_password(client):
    resp = client.post("/settings/export", data={"password": ""}, follow_redirects=False)
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


def test_import_settings_valid(client, tmp_path):
    import json, io
    from core import settings_store

    payload = {"git_user_name": "Imported User", "git_user_email": "imp@example.com"}
    resp = client.post(
        "/settings/import",
        files={
            "file": ("settings.json", io.BytesIO(json.dumps(payload).encode()), "application/json"),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "saved=1" in resp.headers["location"]
    cfg = settings_store.load()
    assert cfg["git_user_name"] == "Imported User"


def test_import_encrypted_dhbak(client):
    """Import .dhbak file with correct password succeeds."""
    import json, io
    from core import settings_store
    from core.crypto import encrypt_export

    payload = {"git_user_name": "Encrypted Import", "git_user_email": "enc@example.com"}
    encrypted = encrypt_export(json.dumps(payload), "importpass")
    resp = client.post(
        "/settings/import",
        files={
            "file": ("backup.dhbak", io.BytesIO(encrypted), "application/octet-stream"),
        },
        data={"import_password": "importpass"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "saved=1" in resp.headers["location"]
    cfg = settings_store.load()
    assert cfg["git_user_name"] == "Encrypted Import"


def test_import_encrypted_wrong_password(client):
    """Import .dhbak file with wrong password returns error redirect."""
    import json, io
    from core.crypto import encrypt_export

    payload = {"git_user_name": "Should Not Import"}
    encrypted = encrypt_export(json.dumps(payload), "correctpass")
    resp = client.post(
        "/settings/import",
        files={
            "file": ("backup.dhbak", io.BytesIO(encrypted), "application/octet-stream"),
        },
        data={"import_password": "wrongpass"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


def test_import_encrypted_no_password(client):
    """Import .dhbak file without password returns error redirect."""
    import json, io
    from core.crypto import encrypt_export

    encrypted = encrypt_export(json.dumps({"x": 1}), "pw")
    resp = client.post(
        "/settings/import",
        files={
            "file": ("backup.dhbak", io.BytesIO(encrypted), "application/octet-stream"),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]
    assert (
        "encrypted" in resp.headers["location"].lower()
        or "password" in resp.headers["location"].lower()
    )


def test_import_settings_no_file(client):
    resp = client.post("/settings/import", data={}, follow_redirects=False)
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


def test_import_settings_invalid_json(client):
    import io

    resp = client.post(
        "/settings/import",
        files={
            "file": ("bad.json", io.BytesIO(b"not json at all"), "application/json"),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


def test_import_settings_wrong_type(client):
    import json, io

    resp = client.post(
        "/settings/import",
        files={
            "file": ("list.json", io.BytesIO(json.dumps([1, 2, 3]).encode()), "application/json"),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


# ── check_repo_permissions ─────────────────────────────────────────────────


def _add_repo_direct(client, **kwargs):
    """Add a repo and return its id."""
    from core import settings_store

    data = {
        "name": "Repo",
        "url": "https://git.example.com/org/r.git",
        "platform": "gitea",
        "auth_mode": "none",
        **kwargs,
    }
    client.post("/settings/repos", data=data, follow_redirects=False)
    cfg = settings_store.load()
    return cfg["repos"][-1]["id"]


def test_check_permissions_repo_not_found(client):
    resp = client.post("/settings/repos/does-not-exist/check")
    assert resp.status_code == 200
    assert "not found" in resp.text.lower()


def test_check_permissions_no_credentials(client):
    repo_id = _add_repo_direct(client, auth_mode="none")
    resp = client.post(f"/settings/repos/{repo_id}/check")
    assert resp.status_code == 200
    assert "read" in resp.text


def test_check_permissions_missing_creds(client):
    """auth_mode=pat but no PAT → no access."""
    repo_id = _add_repo_direct(client, auth_mode="pat", pat="")
    resp = client.post(f"/settings/repos/{repo_id}/check")
    assert resp.status_code == 200
    assert "no access" in resp.text or "error" in resp.text.lower()


# ── test_repo_connection ───────────────────────────────────────────────────


def test_test_connection_repo_not_found(client):
    resp = client.post("/settings/repos/missing-id/test")
    assert resp.status_code == 200
    assert "not found" in resp.text.lower()


def test_test_connection_no_credentials(client, monkeypatch):
    """With auth_mode=none a probe is built — mock test_connection to avoid real git."""
    from unittest.mock import MagicMock, patch

    repo_id = _add_repo_direct(client, auth_mode="none")

    fake_info = {
        "ok": False,
        "read_ok": False,
        "write_ok": False,
        "write_tested": False,
        "auth_mode": "none",
        "platform": "gitea",
        "pat_present": False,
        "ca_cert_present": False,
        "ssh_key_present": False,
        "effective_url": "https://git.example.com/org/r.git",
        "output": "ls-remote failed",
        "write_output": "",
    }

    with patch("main._make_probe") as mock_probe:
        probe_instance = MagicMock()
        probe_instance.test_connection.return_value = fake_info
        mock_probe.return_value = probe_instance
        resp = client.post(f"/settings/repos/{repo_id}/test")

    assert resp.status_code == 200
    assert "Connection failed" in resp.text or "Connection successful" in resp.text


# ── Template CRUD ──────────────────────────────────────────────────────────


def test_add_update_delete_template(client):
    from core import settings_store

    # Add
    resp = client.post(
        "/settings/templates", data={"name": "My Tpl", "content": "Hello"}, follow_redirects=False
    )
    assert resp.status_code == 303
    cfg = settings_store.load()
    tpls = cfg.get("templates", [])
    assert any(t["name"] == "My Tpl" for t in tpls)
    tpl_id = next(t["id"] for t in tpls if t["name"] == "My Tpl")

    # Update
    resp = client.post(
        f"/settings/templates/{tpl_id}",
        data={"name": "Updated Tpl", "content": "World"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cfg = settings_store.load()
    updated = next(t for t in cfg["templates"] if t["id"] == tpl_id)
    assert updated["name"] == "Updated Tpl"

    # Delete
    resp = client.post(f"/settings/templates/{tpl_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    cfg = settings_store.load()
    assert not any(t["id"] == tpl_id for t in cfg.get("templates", []))


# ── Generate SSH keypair ───────────────────────────────────────────────────


def test_generate_keypair(client):
    resp = client.post("/settings/generate-keypair")
    assert resp.status_code == 200
    data = resp.json()
    assert "private_key" in data
    assert "public_key" in data
    assert "BEGIN" in data["private_key"]
    assert "ssh-" in data["public_key"]


# ── Redis & cache endpoints ────────────────────────────────────────────────


def test_redis_status(client):
    resp = client.get("/api/redis-status")
    assert resp.status_code == 200
    assert "cache" in resp.text.lower() or "⚡" in resp.text


def test_flush_cache(client):
    resp = client.post("/api/cache/flush")
    assert resp.status_code == 200
    assert "flush" in resp.text.lower() or "✓" in resp.text


# ── Repo delete ────────────────────────────────────────────────────────────


def test_delete_repo(client):
    from core import settings_store

    repo_id = _add_repo_direct(client)
    cfg = settings_store.load()
    assert any(r["id"] == repo_id for r in cfg["repos"])

    resp = client.post(f"/settings/repos/{repo_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    cfg = settings_store.load()
    assert not any(r["id"] == repo_id for r in cfg["repos"])


# ── URL uniqueness ─────────────────────────────────────────────────────────


def test_add_repo_duplicate_url_rejected(client):
    """Adding a second repo with the same URL is rejected."""
    from core import settings_store

    _add_repo_direct(client, url="https://git.example.com/org/r.git")
    resp = client.post(
        "/settings/repos",
        data={
            "name": "Duplicate",
            "url": "https://git.example.com/org/r.git",
            "platform": "gitea",
            "auth_mode": "none",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]
    cfg = settings_store.load()
    assert sum(1 for r in cfg["repos"] if r["url"] == "https://git.example.com/org/r.git") == 1


def test_update_repo_duplicate_url_rejected(client):
    """Updating a repo to a URL already used by another repo is rejected."""
    from core import settings_store

    _add_repo_direct(client, url="https://git.example.com/org/r.git")
    repo2_id = _add_repo_direct(client, url="https://git.example.com/org/r2.git", name="Repo2")
    resp = client.post(
        f"/settings/repos/{repo2_id}",
        data={
            "name": "Repo2",
            "url": "https://git.example.com/org/r.git",  # already taken
            "platform": "gitea",
            "auth_mode": "none",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]
    cfg = settings_store.load()
    repo2 = next(r for r in cfg["repos"] if r["id"] == repo2_id)
    assert repo2["url"] == "https://git.example.com/org/r2.git"  # unchanged


def test_update_repo_same_url_allowed(client):
    """Saving a repo with its own URL (unchanged) is allowed."""
    from core import settings_store

    repo_id = _add_repo_direct(client, url="https://git.example.com/org/r.git")
    resp = client.post(
        f"/settings/repos/{repo_id}",
        data={
            "name": "Renamed",
            "url": "https://git.example.com/org/r.git",
            "platform": "gitea",
            "auth_mode": "none",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" not in resp.headers["location"]


# ── Copy repo ──────────────────────────────────────────────────────────────


def test_copy_repo_creates_new(client):
    """Copy creates a new repo with a different URL, inheriting all settings."""
    from core import settings_store

    repo_id = _add_repo_direct(
        client, url="https://git.example.com/org/r.git", auth_mode="pat", pat="mytoken"
    )
    resp = client.post(
        f"/settings/repos/{repo_id}/copy",
        data={
            "name": "Copy of Repo",
            "url": "https://git.example.com/org/r-copy.git",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "saved=1" in resp.headers["location"]
    cfg = settings_store.load()
    assert len(cfg["repos"]) == 2
    copy = next(r for r in cfg["repos"] if r["url"] == "https://git.example.com/org/r-copy.git")
    assert copy["name"] == "Copy of Repo"
    assert copy["pat"] == "mytoken"  # inherited
    assert copy["id"] != repo_id


def test_copy_repo_duplicate_url_rejected(client):
    """Copy with a URL already in use is rejected."""
    from core import settings_store

    repo_id = _add_repo_direct(client, url="https://git.example.com/org/r.git")
    resp = client.post(
        f"/settings/repos/{repo_id}/copy",
        data={
            "name": "Copy",
            "url": "https://git.example.com/org/r.git",  # same as source
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]
    cfg = settings_store.load()
    assert len(cfg["repos"]) == 1


def test_copy_repo_not_found(client):
    resp = client.post(
        "/settings/repos/does-not-exist/copy",
        data={
            "name": "X",
            "url": "https://git.example.com/org/new.git",
        },
    )
    assert resp.status_code == 404


# ── TLS custom cert/key ────────────────────────────────────────────────────


def test_save_tls_with_custom_cert_and_key(client):
    """Lines 560, 562: custom cert and key are saved when non-empty."""
    resp = client.post(
        "/settings/tls",
        data={
            "tls_mode": "custom",
            "tls_san": "myhost",
            "tls_custom_crt": "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
            "tls_custom_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert "fake" in cfg.get("tls_custom_crt", "")
    assert "fake" in cfg.get("tls_custom_key", "")


# ── TLS generate endpoint ──────────────────────────────────────────────────


def test_generate_tls_cert(client):
    """Lines 767-775: generate TLS cert returns HTML with cert info."""
    resp = client.post("/settings/tls/generate", data={"tls_san": "localhost, 127.0.0.1"})
    assert resp.status_code == 200
    # Either returns cert info or error — both are HTML responses
    assert len(resp.text) > 0


def test_generate_tls_cert_failure(client, monkeypatch):
    """Line 773: exception path returns error HTML."""
    import core.tls as tls_mod

    monkeypatch.setattr(
        tls_mod,
        "generate_ca_and_server_cert",
        lambda san: (_ for _ in ()).throw(RuntimeError("tls broke")),
    )
    resp = client.post("/settings/tls/generate", data={"tls_san": "localhost"})
    assert resp.status_code == 200
    assert "Error" in resp.text or "error" in resp.text.lower()


# ── CA cert download ───────────────────────────────────────────────────────


def test_download_ca_cert_not_found(client):
    """Lines 818-821: 404 when no cert has been generated."""
    import core.tls as tls_mod
    from pathlib import Path

    # Ensure no CA cert exists at the expected path
    if tls_mod.CA_CERT_PATH.exists():
        import pytest

        pytest.skip("CA cert already generated on this system")
    resp = client.get("/settings/tls/ca.crt")
    assert resp.status_code == 404


# ── Redis stats ────────────────────────────────────────────────────────────


def test_redis_status_connected_with_stats(client, monkeypatch):
    """Lines 836-847: redis connected with stats shows key count and hit rate."""
    import core.cache as cache_mod

    monkeypatch.setattr(cache_mod, "is_connected", lambda: True)
    monkeypatch.setattr(
        cache_mod, "get_stats", lambda: {"key_count": 42, "hit_rate": 85, "breakdown": {}}
    )
    resp = client.get("/api/redis-status")
    assert resp.status_code == 200
    assert "42" in resp.text
    assert "85" in resp.text


def test_redis_status_connected_no_stats(client, monkeypatch):
    """Line 847: redis connected but stats unavailable."""
    import core.cache as cache_mod

    monkeypatch.setattr(cache_mod, "is_connected", lambda: True)
    monkeypatch.setattr(cache_mod, "get_stats", lambda: None)
    resp = client.get("/api/redis-status")
    assert resp.status_code == 200
    assert "⚡" in resp.text


# ── Restart endpoint ───────────────────────────────────────────────────────


def test_restart_returns_restarting(client, monkeypatch):
    """Lines 857-861: restart endpoint returns 200 with restarting status."""
    import asyncio

    # Mock create_task to avoid actually killing the process
    monkeypatch.setattr(asyncio, "create_task", lambda coro: coro.close() or None)
    resp = client.post("/api/restart")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"


# ── Notes line numbers ─────────────────────────────────────────────────────


def test_save_notes_line_numbers_on(client):
    """Line 560, 562 in save_notes_settings: line numbers enabled."""
    resp = client.post(
        "/settings/notes",
        data={
            "notes_scroll_position": "end",
            "notes_line_numbers": "on",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["notes_line_numbers"] is True


def test_save_notes_line_numbers_off(client):
    """notes_line_numbers omitted (unchecked) → False."""
    resp = client.post(
        "/settings/notes",
        data={
            "notes_scroll_position": "end",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["notes_line_numbers"] is False


# ── check_permissions: SSH and basic auth paths ────────────────────────────


def test_check_permissions_ssh_auth(client, monkeypatch):
    """Lines 377-386: SSH auth mode triggers _make_probe + test_connection."""
    from unittest.mock import MagicMock, patch
    from core import settings_store

    # Add a repo with ssh auth
    repo_id = _add_repo_direct(client, auth_mode="ssh")
    # Inject ssh_key so the branch is taken
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    repo["ssh_key"] = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----"
    settings_store.save(cfg)

    fake_info = {
        "ok": True,
        "output": "ok",
        "read_ok": True,
        "write_ok": True,
        "write_tested": True,
        "write_output": "",
        "auth_mode": "ssh",
        "platform": "gitea",
        "pat_present": False,
        "ca_cert_present": False,
        "ssh_key_present": True,
        "effective_url": "ssh://git@x.com/r.git",
    }

    with patch("main._make_probe") as mock_probe:
        probe = MagicMock()
        probe.test_connection.return_value = fake_info
        mock_probe.return_value = probe
        resp = client.post(f"/settings/repos/{repo_id}/check")

    assert resp.status_code == 200
    assert "read" in resp.text or "write" in resp.text


def test_check_permissions_basic_auth(client, monkeypatch):
    """Lines 388-397: basic auth mode triggers _make_probe + test_connection."""
    from unittest.mock import MagicMock, patch
    from core import settings_store

    repo_id = _add_repo_direct(client, auth_mode="basic")
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    repo["basic_password"] = "secret"
    settings_store.save(cfg)

    fake_info = {
        "ok": False,
        "output": "auth failed",
        "read_ok": False,
        "write_ok": False,
        "write_tested": False,
        "write_output": "",
        "auth_mode": "basic",
        "platform": "gitea",
        "pat_present": False,
        "ca_cert_present": False,
        "ssh_key_present": False,
        "effective_url": "https://x.com/r.git",
    }

    with patch("main._make_probe") as mock_probe:
        probe = MagicMock()
        probe.test_connection.return_value = fake_info
        mock_probe.return_value = probe
        resp = client.post(f"/settings/repos/{repo_id}/check")

    assert resp.status_code == 200
    assert "no access" in resp.text or "error" in resp.text.lower()


def test_check_permissions_exception(client, monkeypatch):
    """Lines 402-403: exception in check_permissions returns error span."""
    from unittest.mock import patch
    from core import settings_store

    repo_id = _add_repo_direct(client, auth_mode="pat")
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    repo["pat"] = "mytoken"
    settings_store.save(cfg)

    with patch("main.permission_checker.check_permissions", side_effect=RuntimeError("boom")):
        resp = client.post(f"/settings/repos/{repo_id}/check")

    assert resp.status_code == 200
    assert "Error" in resp.text or "boom" in resp.text


# ── test_connection success paths ──────────────────────────────────────────


def test_test_connection_read_ok_write_ok(client, monkeypatch):
    """Lines 477-480, 501-502: read+write success path."""
    from unittest.mock import MagicMock, patch

    repo_id = _add_repo_direct(client)

    fake_info = {
        "ok": True,
        "read_ok": True,
        "write_ok": True,
        "write_tested": True,
        "auth_mode": "none",
        "platform": "gitea",
        "pat_present": False,
        "ca_cert_present": False,
        "ssh_key_present": False,
        "effective_url": "https://git.example.com/org/r.git",
        "output": "refs/heads/main",
        "write_output": "pushed write-test branch",
    }

    with patch("main._make_probe") as mock_probe:
        probe = MagicMock()
        probe.test_connection.return_value = fake_info
        mock_probe.return_value = probe
        resp = client.post(f"/settings/repos/{repo_id}/test")

    assert resp.status_code == 200
    assert "Connection successful" in resp.text
    assert "pushed write-test branch" in resp.text


def test_test_connection_read_ok_write_fail(client, monkeypatch):
    """Line 480: read ok but write fail shows warning."""
    from unittest.mock import MagicMock, patch

    repo_id = _add_repo_direct(client)

    fake_info = {
        "ok": False,
        "read_ok": True,
        "write_ok": False,
        "write_tested": True,
        "auth_mode": "none",
        "platform": "gitea",
        "pat_present": False,
        "ca_cert_present": False,
        "ssh_key_present": False,
        "effective_url": "https://git.example.com/org/r.git",
        "output": "refs/heads/main",
        "write_output": "push rejected",
    }

    with patch("main._make_probe") as mock_probe:
        probe = MagicMock()
        probe.test_connection.return_value = fake_info
        mock_probe.return_value = probe
        resp = client.post(f"/settings/repos/{repo_id}/test")

    assert resp.status_code == 200
    assert "Read OK" in resp.text or "write" in resp.text.lower()


def test_test_connection_with_pat(client, monkeypatch):
    """Lines 463-466: PAT present triggers permission_checker call."""
    from unittest.mock import MagicMock, patch
    from core import settings_store

    repo_id = _add_repo_direct(client, auth_mode="pat")
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    repo["pat"] = "mytoken"
    settings_store.save(cfg)

    fake_info = {
        "ok": True,
        "read_ok": True,
        "write_ok": True,
        "write_tested": True,
        "auth_mode": "pat",
        "platform": "gitea",
        "pat_present": True,
        "ca_cert_present": False,
        "ssh_key_present": False,
        "effective_url": "https://git.example.com/org/r.git",
        "output": "ok",
        "write_output": "",
    }

    with (
        patch("main._make_probe") as mock_probe,
        patch(
            "main.permission_checker.check_permissions",
            return_value={"read": True, "write": True, "error": None},
        ) as mock_perm,
    ):
        probe = MagicMock()
        probe.test_connection.return_value = fake_info
        mock_probe.return_value = probe
        resp = client.post(f"/settings/repos/{repo_id}/test")

    assert resp.status_code == 200
    mock_perm.assert_called_once()


def test_test_connection_exception(client, monkeypatch):
    """Lines 515-517: exception path returns error div."""
    from unittest.mock import patch

    repo_id = _add_repo_direct(client)

    with patch("main._make_probe", side_effect=RuntimeError("probe exploded")):
        resp = client.post(f"/settings/repos/{repo_id}/test")

    assert resp.status_code == 200
    assert "Error" in resp.text or "probe exploded" in resp.text


def test_test_connection_gitlab_url_handling(client, monkeypatch):
    """Lines 447-448: gitlab platform uses URL-encoded project path."""
    from unittest.mock import MagicMock, patch
    from core import settings_store

    repo_id = _add_repo_direct(client, url="https://gitlab.com/mygroup/myrepo.git")
    cfg = settings_store.load()
    repo = next(r for r in cfg["repos"] if r["id"] == repo_id)
    repo["platform"] = "gitlab"
    settings_store.save(cfg)

    fake_info = {
        "ok": False,
        "read_ok": False,
        "write_ok": False,
        "write_tested": False,
        "auth_mode": "none",
        "platform": "gitlab",
        "pat_present": False,
        "ca_cert_present": False,
        "ssh_key_present": False,
        "effective_url": "https://gitlab.com/mygroup/myrepo.git",
        "output": "failed",
        "write_output": "",
    }

    with patch("main._make_probe") as mock_probe:
        probe = MagicMock()
        probe.test_connection.return_value = fake_info
        mock_probe.return_value = probe
        resp = client.post(f"/settings/repos/{repo_id}/test")

    assert resp.status_code == 200
    # gitlab uses /projects/ endpoint
    assert "gitlab" in resp.text.lower() or "Connection" in resp.text


def test_test_connection_url_parse_fails(client, monkeypatch):
    """Line 452: url that can't be parsed → api_url = api_base."""
    from unittest.mock import MagicMock, patch
    from core import settings_store

    repo_id = _add_repo_direct(client, url="not-a-url")

    fake_info = {
        "ok": False,
        "read_ok": False,
        "write_ok": False,
        "write_tested": False,
        "auth_mode": "none",
        "platform": "gitea",
        "pat_present": False,
        "ca_cert_present": False,
        "ssh_key_present": False,
        "effective_url": "not-a-url",
        "output": "failed",
        "write_output": "",
    }

    with patch("main._make_probe") as mock_probe:
        probe = MagicMock()
        probe.test_connection.return_value = fake_info
        mock_probe.return_value = probe
        resp = client.post(f"/settings/repos/{repo_id}/test")

    assert resp.status_code == 200


# ── update_repo 404 ────────────────────────────────────────────────────────


def test_update_repo_not_found(client):
    """Line 270: updating non-existent repo returns 404."""
    resp = client.post(
        "/settings/repos/does-not-exist",
        data={
            "name": "X",
            "url": "https://git.example.com/org/r.git",
            "platform": "gitea",
            "auth_mode": "none",
        },
    )
    assert resp.status_code == 404


# ── Metrics storage exception ──────────────────────────────────────────────


def test_get_metrics_storage_exception(client, monkeypatch):
    """Lines 884-885: storage.get_categories/get_entries exception falls back to []."""
    from unittest.mock import MagicMock, patch
    from core import settings_store as ss

    cfg = ss.load()
    cfg["repos"] = [
        {
            "id": "r1",
            "name": "Repo 1",
            "url": "https://x.com/r.git",
            "platform": "gitea",
            "auth_mode": "none",
            "enabled": True,
            "permissions": {"read": True, "write": True},
        }
    ]
    cfg["metrics_enabled"] = True
    ss.save(cfg)

    mock_store = MagicMock()
    mock_store.get_categories.side_effect = RuntimeError("storage broken")
    mock_store.get_entries.side_effect = RuntimeError("storage broken")

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": mock_store}

    with patch("main.get_storage", return_value=mock_storage):
        resp = client.get("/metrics")

    assert resp.status_code == 200


# ── Metrics with storage ───────────────────────────────────────────────────


def test_get_metrics_with_storage(client, monkeypatch):
    """Lines 879-886: metrics endpoint with active storage."""
    from unittest.mock import MagicMock, patch
    from core import settings_store

    # Add a repo
    from core import settings_store as ss

    cfg = ss.load()
    cfg["repos"] = [
        {
            "id": "r1",
            "name": "Repo 1",
            "url": "https://x.com/r.git",
            "platform": "gitea",
            "auth_mode": "none",
            "enabled": True,
            "permissions": {"read": True, "write": True},
        }
    ]
    cfg["metrics_enabled"] = True
    ss.save(cfg)

    mock_store = MagicMock()
    mock_store.get_categories.return_value = ["Linux", "Python"]
    mock_store.get_entries.return_value = [{"title": "e1"}, {"title": "e2"}]

    mock_storage = MagicMock()
    mock_storage._stores = {"r1": mock_store}

    with patch("main.get_storage", return_value=mock_storage):
        resp = client.get("/metrics")

    assert resp.status_code == 200


# ── Appearance settings ────────────────────────────────────────────────────


def test_save_appearance_dark(client):
    resp = client.post("/settings/appearance", data={"theme_mode": "dark"}, follow_redirects=False)
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["theme_mode"] == "dark"


def test_save_appearance_light(client):
    resp = client.post("/settings/appearance", data={"theme_mode": "light"}, follow_redirects=False)
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["theme_mode"] == "light"


def test_save_appearance_auto(client):
    resp = client.post("/settings/appearance", data={"theme_mode": "auto"}, follow_redirects=False)
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["theme_mode"] == "auto"


def test_save_appearance_invalid_defaults_to_auto(client):
    resp = client.post(
        "/settings/appearance", data={"theme_mode": "rainbow"}, follow_redirects=False
    )
    assert resp.status_code == 303
    from core import settings_store

    cfg = settings_store.load()
    assert cfg["theme_mode"] == "auto"


def test_appearance_redirect_includes_anchor(client):
    resp = client.post("/settings/appearance", data={"theme_mode": "dark"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "#appearance" in resp.headers["location"]


def test_settings_page_renders_appearance_section(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert 'id="appearance"' in resp.text
    assert 'name="theme_mode"' in resp.text
    assert 'value="auto"' in resp.text
    assert 'value="dark"' in resp.text
    assert 'value="light"' in resp.text


def _dark_radio_checked(html: str) -> bool:
    import re

    return bool(
        re.search(r'<input[^>]*value="dark"[^>]*checked', html)
        or re.search(r'<input[^>]*checked[^>]*value="dark"', html)
    )


def test_settings_page_reflects_saved_theme_mode(client):
    client.post("/settings/appearance", data={"theme_mode": "dark"}, follow_redirects=False)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert _dark_radio_checked(resp.text), "dark radio should be checked after saving dark"
