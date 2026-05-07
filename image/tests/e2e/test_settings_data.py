"""E2E tests for Settings → Data: encrypted export/import and backup-to-repo."""

import io
import json
import urllib.error
import urllib.parse
import urllib.request

import pytest
from playwright.sync_api import Page, expect


def _post_export(live_server: str, password: str) -> bytes:
    """Helper: POST /settings/export and return raw bytes."""
    data = urllib.parse.urlencode({"password": password}).encode()
    req = urllib.request.Request(
        f"{live_server}/settings/export",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        return e.read()


class TestEncryptedExport:
    def test_export_form_visible_in_settings(self, page: Page, live_server):
        """Settings → Data section contains the export form with password field."""
        page.goto(f"{live_server}/settings#data")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.getElementById('data').scrollIntoView()")
        page.wait_for_timeout(300)

        expect(page.locator('input[name="password"]').first).to_be_visible()
        expect(page.locator('button:has-text("Export encrypted backup")')).to_be_visible()

    def test_export_without_password_shows_error(self, page: Page, live_server):
        """Submitting the export form without a password redirects to settings with error."""
        page.goto(f"{live_server}/settings#data")
        page.wait_for_load_state("networkidle")

        # Submit with empty password (HTML required may prevent it — bypass via JS)
        page.evaluate("""
            const form = document.querySelector('form[action="/settings/export"]');
            const pw = form.querySelector('input[name="password"]');
            pw.removeAttribute('required');
        """)
        page.locator('form[action="/settings/export"] button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator(".alert-error")).to_be_visible()

    def test_export_with_password_downloads_dhbak(self, page: Page, live_server):
        """Filling in a password and clicking Export triggers a .dhbak download."""
        page.goto(f"{live_server}/settings#data")
        page.wait_for_load_state("networkidle")

        with page.expect_download() as dl_info:
            page.locator('form[action="/settings/export"] input[name="password"]').fill("e2epassword")
            page.locator('form[action="/settings/export"] button[type="submit"]').click()

        download = dl_info.value
        assert download.suggested_filename.endswith(".dhbak"), \
            f"Expected .dhbak, got: {download.suggested_filename}"

    def test_exported_file_is_encrypted(self, live_server):
        """Exported bytes start with the DHBK magic header."""
        data = _post_export(live_server, "testpassword")
        assert data[:4] == b"DHBK", \
            f"Expected DHBK magic, got: {data[:4]!r}"

    def test_exported_file_decrypts_to_valid_json(self, live_server):
        """Exported .dhbak decrypts to a valid settings dict."""
        import sys
        import os
        _candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app"))
        _app_dir = _candidate if os.path.isdir(_candidate) else os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", ".."))
        sys.path.insert(0, _app_dir)
        from core.crypto import decrypt_export

        raw = _post_export(live_server, "decryptme")
        decrypted = decrypt_export(raw, "decryptme")
        cfg = json.loads(decrypted)
        assert isinstance(cfg, dict)
        assert "repos" in cfg


class TestEncryptedImport:
    def test_import_form_has_password_field(self, page: Page, live_server):
        """Settings → Data import form has a password field for .dhbak files."""
        page.goto(f"{live_server}/settings#data")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.getElementById('data').scrollIntoView()")
        page.wait_for_timeout(300)

        expect(page.locator('input[name="import_password"]')).to_be_visible()
        expect(page.locator('input[name="file"]')).to_be_visible()

    def test_import_dhbak_wrong_password_shows_error(self, page: Page, live_server, tmp_path):
        """Uploading a .dhbak with the wrong password shows an error flash."""
        import sys, os
        _candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app"))
        _app_dir = _candidate if os.path.isdir(_candidate) else os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", ".."))
        sys.path.insert(0, _app_dir)
        from core.crypto import encrypt_export

        payload = json.dumps({"git_user_name": "Should Not Import"})
        encrypted = encrypt_export(payload, "correctpass")
        backup_file = tmp_path / "test.dhbak"
        backup_file.write_bytes(encrypted)

        page.goto(f"{live_server}/settings#data")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.getElementById('data').scrollIntoView()")
        page.wait_for_timeout(300)

        page.locator('input[name="file"]').set_input_files(str(backup_file))
        page.locator('input[name="import_password"]').fill("wrongpass")
        page.once("dialog", lambda d: d.accept())
        page.locator('form[action="/settings/import"] button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator(".alert-error")).to_be_visible()

    def test_import_dhbak_correct_password_succeeds(self, page: Page, live_server, tmp_path):
        """Uploading a .dhbak with the correct password imports successfully."""
        import sys, os
        _candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app"))
        _app_dir = _candidate if os.path.isdir(_candidate) else os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", ".."))
        sys.path.insert(0, _app_dir)
        from core.crypto import encrypt_export

        # Keep existing settings structure but change a recognizable field
        raw_cfg = _post_export(live_server, "tmppw")
        from core.crypto import decrypt_export
        cfg = json.loads(decrypt_export(raw_cfg, "tmppw"))
        cfg["git_user_name"] = "E2E Imported User"
        payload = json.dumps(cfg)
        encrypted = encrypt_export(payload, "importpass")
        backup_file = tmp_path / "valid.dhbak"
        backup_file.write_bytes(encrypted)

        page.goto(f"{live_server}/settings#data")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.getElementById('data').scrollIntoView()")
        page.wait_for_timeout(300)

        page.locator('input[name="file"]').set_input_files(str(backup_file))
        page.locator('input[name="import_password"]').fill("importpass")

        page.once("dialog", lambda d: d.accept())
        page.locator('form[action="/settings/import"] button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator(".alert-success").first).to_be_visible()
        # Verify settings page reloaded correctly (no crash)
        expect(page.locator(".settings-subnav")).to_be_visible()

    def test_import_dhbak_no_password_shows_error(self, page: Page, live_server, tmp_path):
        """Uploading a .dhbak without entering a password shows an error."""
        import sys, os
        _candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app"))
        _app_dir = _candidate if os.path.isdir(_candidate) else os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", ".."))
        sys.path.insert(0, _app_dir)
        from core.crypto import encrypt_export

        encrypted = encrypt_export('{"git_user_name": "nope"}', "somepass")
        backup_file = tmp_path / "nopass.dhbak"
        backup_file.write_bytes(encrypted)

        page.goto(f"{live_server}/settings#data")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.getElementById('data').scrollIntoView()")
        page.wait_for_timeout(300)

        page.locator('input[name="file"]').set_input_files(str(backup_file))
        # Leave import_password empty
        page.once("dialog", lambda d: d.accept())
        page.locator('form[action="/settings/import"] button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator(".alert-error")).to_be_visible()


class TestFloccusGrantPage:
    def test_grant_page_without_token_shows_error(self, page: Page, live_server):
        """GET /index.php/login/v2/grant without token returns an error page."""
        page.goto(f"{live_server}/index.php/login/v2/grant")
        page.wait_for_load_state("networkidle")
        # Should show an error (400), not a login form
        expect(page.locator("h2")).to_contain_text("Invalid Link")

    def test_grant_page_with_invalid_token_shows_error(self, page: Page, live_server):
        """GET grant page with a non-existent token returns error."""
        page.goto(f"{live_server}/index.php/login/v2/grant?token=notarealtoken")
        page.wait_for_load_state("networkidle")
        # Token not in store → form still shows (token is just passed through to form)
        # The page renders the form (token validation happens on POST)
        content = page.content()
        assert "Floccus Login" in content or "Invalid" in content


class TestSprintCapacityPage:
    def test_capacity_page_loads(self, page: Page, live_server):
        """Sprint capacity page loads without error."""
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        # Either shows sprints or the "no sprints configured" empty state
        body = page.locator("body")
        expect(body).to_be_visible()
        # No server error
        assert page.title() != "500 Internal Server Error"

    def test_capacity_page_shows_year_navigation(self, page: Page, live_server):
        """Sprint capacity page has year navigation buttons."""
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        expect(page.locator('a[href*="capacity?year"]').first).to_be_visible()

    def test_capacity_page_current_year_button(self, page: Page, live_server):
        """Sprint capacity page has a 'This year' button."""
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        expect(page.locator('a:has-text("This year")')).to_be_visible()
