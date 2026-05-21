"""Tests for the mail_templates module — router and storage."""

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


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        pass

    def read_committed(self, path):
        full = os.path.join(self.local_path, path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def list_committed(self, directory):
        full = os.path.join(self.local_path, directory)
        if not os.path.isdir(full):
            return []
        return os.listdir(full)


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
def client_with_storage(tmp_path, isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from unittest.mock import patch
    from core import settings_store

    reset_storage()
    fake_git = FakeGit(tmp_path)

    cfg = settings_store.load()
    cfg["modules_enabled"]["mail_templates"] = True
    settings_store.save(cfg)

    def fake_get_primary(module, storage):
        if module == "mail_templates":
            return fake_git
        return None

    with (
        patch("modules.mail_templates.router.get_storage", return_value=object()),
        patch("modules.mail_templates.router.get_primary_store", side_effect=fake_get_primary),
        patch("modules.mail_templates.router.get_module_stores", return_value=[fake_git]),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        yield c, fake_git


@pytest.fixture()
def client_no_storage(isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from unittest.mock import patch
    from core import settings_store

    reset_storage()
    cfg = settings_store.load()
    cfg["modules_enabled"]["mail_templates"] = True
    settings_store.save(cfg)

    with (
        patch("modules.mail_templates.router.get_storage", return_value=None),
        patch("modules.mail_templates.router.get_primary_store", return_value=None),
        patch("modules.mail_templates.router.get_module_stores", return_value=[]),
    ):
        c = TestClient(_main_module.app, raise_server_exceptions=False)
        yield c


# ── List ─────────────────────────────────────────────────────────────────────


def test_list_no_storage(client_no_storage):
    resp = client_no_storage.get("/mail-templates")
    assert resp.status_code == 200
    assert b"configured" in resp.content.lower() or b"settings" in resp.content.lower()


def test_list_empty(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/mail-templates")
    assert resp.status_code == 200


def test_list_shows_template(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    ts = MailTemplateStorage(fake_git)
    ts.create_template(
        {"name": "Invoice", "to": "boss@example.com", "subject": "Invoice", "cc": "", "body": "Hi"}
    )
    resp = client.get("/mail-templates")
    assert resp.status_code == 200
    assert b"Invoice" in resp.content


def test_list_saved_banner(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/mail-templates?saved=1")
    assert resp.status_code == 200
    assert b"saved" in resp.content.lower()


# ── Create ────────────────────────────────────────────────────────────────────


def test_create_redirects(client_with_storage):
    client, fake_git = client_with_storage
    resp = client.post(
        "/mail-templates/new",
        data={
            "name": "Welcome",
            "to": "x@example.com",
            "cc": "",
            "subject": "Hi",
            "body": "Hello",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/mail-templates" in resp.headers["location"]


def test_create_no_storage_503(client_no_storage):
    resp = client_no_storage.post(
        "/mail-templates/new",
        data={
            "name": "X",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "",
        },
    )
    assert resp.status_code == 503


def test_create_empty_name_400(client_with_storage):
    client, _ = client_with_storage
    resp = client.post(
        "/mail-templates/new",
        data={
            "name": "   ",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "",
        },
    )
    assert resp.status_code == 400


# ── Edit form ─────────────────────────────────────────────────────────────────


def test_edit_form_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/mail-templates/nonexistent/edit")
    assert resp.status_code == 404


def test_edit_form_renders(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {"name": "Draft", "to": "", "cc": "", "subject": "Sub", "body": ""}
    )
    resp = client.get(f"/mail-templates/{t['id']}/edit")
    assert resp.status_code == 200
    assert b"Draft" in resp.content


# ── Update ────────────────────────────────────────────────────────────────────


def test_update_no_storage_503(client_no_storage):
    resp = client_no_storage.post(
        "/mail-templates/someid/edit",
        data={
            "name": "X",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "",
        },
    )
    assert resp.status_code == 503


def test_update_empty_name_400(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {"name": "Old", "to": "", "cc": "", "subject": "", "body": ""}
    )
    resp = client.post(
        f"/mail-templates/{t['id']}/edit",
        data={
            "name": "  ",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "",
        },
    )
    assert resp.status_code == 400


def test_update_not_found_404(client_with_storage):
    client, _ = client_with_storage
    resp = client.post(
        "/mail-templates/badid/edit",
        data={
            "name": "X",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "",
        },
    )
    assert resp.status_code == 404


def test_update_redirects(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {"name": "Old", "to": "", "cc": "", "subject": "Orig", "body": ""}
    )
    resp = client.post(
        f"/mail-templates/{t['id']}/edit",
        data={
            "name": "New Name",
            "to": "a@b.com",
            "cc": "",
            "subject": "Updated",
            "body": "Body",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303


# ── EML download ──────────────────────────────────────────────────────────────


def test_eml_download_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/mail-templates/missing/download.eml")
    assert resp.status_code == 404


def test_eml_download_content_type(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {
            "name": "Report",
            "to": "boss@example.com",
            "cc": "cc@example.com",
            "subject": "Monthly Report",
            "body": "Please find attached.",
        }
    )
    resp = client.get(f"/mail-templates/{t['id']}/download.eml")
    assert resp.status_code == 200
    assert "message/rfc822" in resp.headers["content-type"]


def test_eml_download_has_rfc_headers(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {
            "name": "Status Update",
            "to": "team@example.com",
            "cc": "mgr@example.com",
            "subject": "Weekly Status",
            "body": "All good.",
        }
    )
    resp = client.get(f"/mail-templates/{t['id']}/download.eml")
    body = resp.text
    assert "To: team@example.com" in body
    assert "CC: mgr@example.com" in body
    assert "Subject: Weekly Status" in body
    assert "MIME-Version: 1.0" in body
    assert "Content-Type: text/plain" in body
    assert "All good." in body


def test_eml_download_without_optional_fields(client_with_storage, tmp_path):
    """Template with no To/CC/Subject still generates valid EML."""
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {
            "name": "Minimal",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "Just a body.",
        }
    )
    resp = client.get(f"/mail-templates/{t['id']}/download.eml")
    assert resp.status_code == 200
    body = resp.text
    assert "MIME-Version: 1.0" in body
    assert "Just a body." in body
    assert "To:" not in body
    assert "CC:" not in body
    assert "Subject:" not in body


def test_eml_filename_sanitized(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {
            "name": "Résumé/Follow-up!",
            "to": "",
            "cc": "",
            "subject": "",
            "body": "",
        }
    )
    resp = client.get(f"/mail-templates/{t['id']}/download.eml")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    # Filename should not contain / or !
    assert "/" not in cd.split("filename=")[-1]
    assert "!" not in cd.split("filename=")[-1]


# ── Delete ────────────────────────────────────────────────────────────────────


def test_delete_no_storage_503(client_no_storage):
    resp = client_no_storage.post("/mail-templates/someid/delete")
    assert resp.status_code == 503


def test_delete_redirects(client_with_storage, tmp_path):
    client, fake_git = client_with_storage
    from modules.mail_templates.storage import MailTemplateStorage

    t = MailTemplateStorage(fake_git).create_template(
        {"name": "Bye", "to": "", "cc": "", "subject": "", "body": ""}
    )
    resp = client.post(f"/mail-templates/{t['id']}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert "/mail-templates" in resp.headers["location"]
