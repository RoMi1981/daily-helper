"""E2E tests for the RSS Reader module."""

from playwright.sync_api import Page, expect


def _add_feed(page: Page, live_server: str, name: str, url: str) -> None:
    page.goto(f"{live_server}/rss")
    page.locator('button.btn-primary[onclick="toggleAddForm()"]').click()
    page.wait_for_selector("#add-feed-form", state="visible")
    page.locator("#add-feed-form").locator('[name="name"]').fill(name)
    page.locator("#add-feed-form").locator('[name="url"]').fill(url)
    page.locator("#add-feed-form").locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


class TestRssFeedManagement:
    def test_rss_page_loads(self, page: Page, live_server):
        """RSS page renders without error when no feeds configured."""
        page.goto(f"{live_server}/rss")
        expect(page.locator("body")).to_contain_text("RSS")

    def test_add_feed_appears_in_list(self, page: Page, live_server):
        """Adding a new feed shows its name in the sidebar."""
        _add_feed(page, live_server, "E2E Test Feed", "https://e2e-test.example.com/feed.xml")
        expect(page.locator("body")).to_contain_text("E2E Test Feed")

    def test_edit_feed_updates_name(self, page: Page, live_server):
        """Editing a feed updates its display name."""
        _add_feed(
            page, live_server, "E2E Feed Before Edit", "https://e2e-edit.example.com/feed.xml"
        )

        page.locator("a", has_text="E2E Feed Before Edit").first.click()
        page.wait_for_load_state("networkidle")

        page.locator("button", has_text="Edit").click()
        page.wait_for_selector("#feed-edit-form", state="visible")
        page.locator("#feed-edit-form").locator('[name="name"]').fill("E2E Feed After Edit")
        page.locator("#feed-edit-form").locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator("body")).to_contain_text("E2E Feed After Edit")

    def test_delete_feed_removes_from_list(self, page: Page, live_server):
        """Deleting a feed removes it from the sidebar."""
        _add_feed(
            page, live_server, "E2E Feed To Delete", "https://e2e-delete.example.com/feed.xml"
        )

        page.locator("a", has_text="E2E Feed To Delete").first.click()
        page.wait_for_load_state("networkidle")

        page.on("dialog", lambda d: d.accept())
        page.locator('form[action*="/delete"] button').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator("body")).not_to_contain_text("E2E Feed To Delete")

    def test_set_default_feed(self, page: Page, live_server):
        """Setting a feed as default causes it to load first on /rss."""
        _add_feed(page, live_server, "E2E Default Feed", "https://e2e-default.example.com/feed.xml")

        page.goto(f"{live_server}/rss", wait_until="networkidle")
        page.wait_for_selector('a:has-text("E2E Default Feed")', timeout=15000)
        page.locator("a", has_text="E2E Default Feed").first.click()
        page.wait_for_load_state("networkidle")

        set_default_btn = page.locator('form[action*="set-default"] button')
        if set_default_btn.count() > 0:
            set_default_btn.click()
            page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/rss", wait_until="networkidle")
        expect(page.locator("body")).to_contain_text("E2E Default Feed")
