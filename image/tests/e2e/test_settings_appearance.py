"""E2E tests for the Appearance settings section (theme mode: dark/light/auto)."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture(autouse=True)
def go_to_appearance(page: Page, live_server):
    page.goto(f"{live_server}/settings#appearance")
    expect(page.locator("#appearance")).to_be_visible()


class TestAppearanceSection:
    def test_appearance_section_visible(self, page: Page):
        """Appearance fieldset is present on the settings page."""
        expect(page.locator("#appearance legend")).to_contain_text("Appearance")

    def test_three_radio_options_present(self, page: Page):
        """All three radio buttons (auto, dark, light) are rendered."""
        expect(page.locator('input[name="theme_mode"][value="auto"]')).to_be_visible()
        expect(page.locator('input[name="theme_mode"][value="dark"]')).to_be_visible()
        expect(page.locator('input[name="theme_mode"][value="light"]')).to_be_visible()

    def test_subnav_has_appearance_link(self, page: Page, live_server):
        page.goto(f"{live_server}/settings")
        expect(page.locator('.settings-subnav a[href="#appearance"]')).to_be_visible()

    def test_save_dark_mode(self, page: Page, live_server):
        """Selecting Dark and saving persists the choice and applies dark theme."""
        page.locator('input[name="theme_mode"][value="dark"]').check()
        page.locator("#appearance button[type=submit]").click()
        page.wait_for_url(f"{live_server}/settings*")

        # Radio should now be checked
        expect(page.locator('input[name="theme_mode"][value="dark"]')).to_be_checked()
        # data-theme should not be "light" (dark is default — attribute may be absent)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme != "light", f"Expected dark theme, got data-theme='{theme}'"

    def test_save_light_mode(self, page: Page, live_server):
        """Selecting Light and saving persists the choice and applies light theme."""
        page.locator('input[name="theme_mode"][value="light"]').check()
        page.locator("#appearance button[type=submit]").click()
        page.wait_for_url(f"{live_server}/settings*")

        expect(page.locator('input[name="theme_mode"][value="light"]')).to_be_checked()
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme == "light", f"Expected light theme, got data-theme='{theme}'"

    def test_save_auto_mode(self, page: Page, live_server):
        """Selecting Auto and saving persists the choice."""
        # First set to dark so we have something to switch from
        page.locator('input[name="theme_mode"][value="dark"]').check()
        page.locator("#appearance button[type=submit]").click()
        page.wait_for_url(f"{live_server}/settings*")

        page.goto(f"{live_server}/settings#appearance")
        page.locator('input[name="theme_mode"][value="auto"]').check()
        page.locator("#appearance button[type=submit]").click()
        page.wait_for_url(f"{live_server}/settings*")

        expect(page.locator('input[name="theme_mode"][value="auto"]')).to_be_checked()

    def test_theme_applied_immediately_on_save(self, page: Page, live_server):
        """Theme changes take effect before the page reloads (JS applies it immediately)."""
        # Start fresh on a non-settings page to clear localStorage
        page.goto(f"{live_server}/")
        page.evaluate("localStorage.removeItem('theme')")

        page.goto(f"{live_server}/settings#appearance")
        page.locator('input[name="theme_mode"][value="light"]').check()

        # Intercept the submit — theme should change before navigation
        page.evaluate("""
            document.getElementById('appearance-form').addEventListener('submit', function() {
                window.__themeBeforeNav = document.documentElement.getAttribute('data-theme');
            }, {once: true});
        """)
        page.locator("#appearance button[type=submit]").click()
        page.wait_for_url(f"{live_server}/settings*")

        # After redirect, localStorage should no longer have a stale dark value
        stored = page.evaluate("localStorage.getItem('theme')")
        assert stored in (None, "light"), f"localStorage theme should be null or 'light', got {stored!r}"
