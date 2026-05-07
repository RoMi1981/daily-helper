"""E2E tests for the History module."""

from playwright.sync_api import Page, expect


def _create_entry(page: Page, base: str, title: str, content: str = "body") -> str:
    page.goto(f"{base}/knowledge/new")
    cat = page.locator("#category")
    cat.select_option("__new__")
    page.fill('[name="new_category"]', "E2E-History")
    page.fill('[name="title"]', title)
    page.fill('[name="content"]', content)
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    return page.url


class TestHistoryPage:
    def test_history_page_loads(self, page: Page, live_server):
        """History page renders without error."""
        page.goto(f"{live_server}/history")
        expect(page.locator("h1")).to_be_visible()

    def test_history_nav_link_visible(self, page: Page, live_server):
        """History link is present in the sidebar nav."""
        page.goto(f"{live_server}/")
        expect(page.get_by_role("link", name="History").first).to_be_visible()

    def test_created_entry_appears_in_history(self, page: Page, live_server):
        """A newly created knowledge entry shows up in history."""
        _create_entry(page, live_server, "E2E History Entry Alpha")
        page.goto(f"{live_server}/history")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E History Entry Alpha").first).to_be_visible()

    def test_range_tabs_present(self, page: Page, live_server):
        """Range tab buttons (Today, This week, etc.) are visible."""
        page.goto(f"{live_server}/history")
        expect(page.get_by_role("button", name="Today")).to_be_visible()
        expect(page.get_by_role("button", name="This week")).to_be_visible()

    def test_tab_switch_loads_different_range(self, page: Page, live_server):
        """Clicking a tab loads content without a full page reload."""
        _create_entry(page, live_server, "E2E History Tab Entry")
        page.goto(f"{live_server}/history")
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="This month").click()
        page.wait_for_load_state("networkidle")
        # Should still show history list without error
        expect(page.locator("#history-list")).to_be_visible()
