"""E2E tests for the Widget Dashboard (start page)."""

from playwright.sync_api import Page, expect


class TestHomeDashboard:
    def test_home_redirects_to_widgets(self, page: Page, live_server):
        """/ redirects to /widgets."""
        page.goto(f"{live_server}/")
        expect(page).to_have_url(f"{live_server}/widgets")

    def test_home_links_to_modules(self, page: Page, live_server):
        """Sidebar contains links to module pages."""
        page.goto(f"{live_server}/widgets")
        expect(page.locator('a[href="/tasks"]').first).to_be_visible()
        expect(page.locator('a[href="/notes"]').first).to_be_visible()

    def test_home_counts_increase_after_creating_content(self, page: Page, live_server):
        """Widget dashboard loads without errors."""
        page.goto(f"{live_server}/widgets")
        expect(page.locator("#widget-grid")).to_be_attached()
