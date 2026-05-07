"""E2E tests for the Links module — create, category filter, search."""

from playwright.sync_api import Page, expect


class TestLinkCreate:
    def test_link_appears_in_list(self, page: Page, live_server, seeded_links):
        """A seeded link appears on the links page."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Link Alpha").first).to_be_visible()

    def test_link_with_category_shows_category_filter(self, page: Page, live_server, seeded_links):
        """A link with a category makes that category filter appear."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E-Docs").first).to_be_visible()

    def test_link_url_is_rendered(self, page: Page, live_server, seeded_links):
        """The URL of the seeded link is shown (as href)."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        expect(page.locator('a[href="https://urlcheck.example.com"]').first).to_be_visible()


class TestLinkCategoryFilter:
    def test_category_filter_shows_only_matching_links(self, page: Page, live_server, seeded_links):
        """Clicking a category filter shows only links in that category."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        page.get_by_text("E2E-Filter").first.click()
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Filtered Link").first).to_be_visible()


class TestLinkSearch:
    def test_search_returns_matching_link(self, page: Page, live_server, seeded_links):
        """Search query filters the link list."""
        page.goto(f"{live_server}/links?q=Quasar")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Quasar Link").first).to_be_visible()
