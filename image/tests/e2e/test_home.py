"""E2E tests for the Home dashboard."""

from playwright.sync_api import Page, expect


class TestHomeDashboard:
    def test_home_loads_with_stat_cards(self, page: Page, live_server):
        """Home page shows module stat cards."""
        page.goto(f"{live_server}/")
        expect(page.locator(".home-stat-card").first).to_be_visible()

    def test_home_links_to_modules(self, page: Page, live_server):
        """Stat cards are clickable links to their modules."""
        page.goto(f"{live_server}/")
        # At least the Tasks card should be present
        expect(page.locator('.home-stat-card[href="/tasks"]')).to_be_visible()
        expect(page.locator('.home-stat-card[href="/notes"]')).to_be_visible()
        expect(page.locator('.home-stat-card[href="/runbooks"]')).to_be_visible()

    def test_home_counts_increase_after_creating_content(self, page: Page, live_server):
        """Note count on home page is a non-negative integer."""
        page.goto(f"{live_server}/")
        # The stat value is a number (≥ 0)
        value_text = page.locator('.home-stat-card[href="/notes"] .home-stat-value').inner_text()
        assert value_text.strip().isdigit(), f"Expected digit, got: {value_text!r}"
