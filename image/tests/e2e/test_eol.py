"""E2E tests for the EOL Tracker module."""

import urllib.parse
import urllib.request

import pytest
from playwright.sync_api import Page, expect


def _add_eol_entry(live_server: str, product: str, cycle: str, label: str = "") -> None:
    """Directly POST an EOL entry without going through the external API search."""
    data = urllib.parse.urlencode(
        {"product": product, "cycle": cycle, "label": label or f"{product} {cycle}", "notes": ""}
    ).encode()
    req = urllib.request.Request(
        f"{live_server}/eol/add",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError:
        pass  # 303 redirect — expected


class TestEolPage:
    def test_page_loads(self, page: Page, live_server):
        page.goto(f"{live_server}/eol")
        page.wait_for_load_state("networkidle")
        expect(page.locator("h1")).to_be_visible()

    def test_page_has_track_software_button(self, page: Page, live_server):
        page.goto(f"{live_server}/eol")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("Track Software").first).to_be_visible()

    def test_add_page_has_search_form(self, page: Page, live_server):
        page.goto(f"{live_server}/eol/add")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#eol-search-input")).to_be_visible()

    def test_search_input_accepts_text(self, page: Page, live_server):
        page.goto(f"{live_server}/eol/add")
        page.wait_for_load_state("networkidle")
        page.locator("#eol-search-input").fill("python")
        expect(page.locator("#eol-search-input")).to_have_value("python")


class TestEolEntry:
    def test_entry_appears_after_add(self, page: Page, live_server):
        _add_eol_entry(live_server, "e2e-test-product", "1.0", "E2E Test Product 1.0")
        page.goto(f"{live_server}/eol")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("e2e-test-product").first).to_be_visible()

    def test_cycle_is_visible(self, page: Page, live_server):
        _add_eol_entry(live_server, "e2e-cycle-product", "2.5", "E2E Cycle Product 2.5")
        page.goto(f"{live_server}/eol")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("2.5").first).to_be_visible()

    def test_notes_toggle_opens_form(self, page: Page, live_server):
        _add_eol_entry(live_server, "e2e-notes-product", "3.0", "E2E Notes Product 3.0")
        page.goto(f"{live_server}/eol")
        page.wait_for_load_state("networkidle")

        row = page.locator(".eol-entry", has_text="3.0").first
        notes_btn = row.locator("button", has_text="Notes")
        notes_btn.click()
        page.wait_for_timeout(200)

        # The notes form should now be visible
        notes_textarea = row.locator("textarea[name='notes']")
        expect(notes_textarea).to_be_visible()

    def test_delete_entry(self, page: Page, live_server):
        _add_eol_entry(live_server, "e2e-delete-product", "9.9", "E2E Delete Product 9.9")
        page.goto(f"{live_server}/eol")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("e2e-delete-product").first).to_be_visible()

        row = page.locator(".eol-entry", has_text="9.9").first
        delete_form = row.locator('form[action*="/delete"]')
        # Bypass the confirm dialog
        page.evaluate("window.confirm = () => true")
        delete_form.locator("button").click()
        page.wait_for_load_state("networkidle")

        # Entry should be gone
        expect(page.get_by_text("e2e-delete-product")).not_to_be_visible()
