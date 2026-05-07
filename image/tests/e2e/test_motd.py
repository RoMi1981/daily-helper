"""E2E tests for the Message of the Day (MOTD) module."""

from playwright.sync_api import Page, expect


class TestMotdCrud:
    def test_motd_list_loads(self, page: Page, live_server):
        """MOTD list page renders without error."""
        page.goto(f"{live_server}/motd")
        expect(page.locator("h1")).to_contain_text("Message of the Day")

    def test_create_motd_appears_in_list(self, page: Page, live_server):
        """Creating a new MOTD entry shows it in the list."""
        page.goto(f"{live_server}/motd/new")
        page.fill('[name="text"]', "E2E Test MOTD Entry unique-e2e-motd-12345")
        page.locator('[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/motd")
        expect(page.locator("body")).to_contain_text("E2E Test MOTD Entry unique-e2e-motd-12345")

    def test_edit_motd_updates_content(self, page: Page, live_server):
        """Editing a MOTD entry updates the stored body."""
        # Create first
        page.goto(f"{live_server}/motd/new")
        page.fill('[name="text"]', "E2E MOTD Before Edit")
        page.locator('[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")

        # Find the edit link for this entry
        page.goto(f"{live_server}/motd")
        entry = page.locator(".card", has_text="E2E MOTD Before Edit").first
        entry.locator('a[href*="/edit"]').click()
        page.wait_for_load_state("networkidle")

        page.fill('[name="text"]', "E2E MOTD After Edit")
        page.locator('[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/motd")
        expect(page.locator("body")).to_contain_text("E2E MOTD After Edit")

    def test_delete_motd_removes_from_list(self, page: Page, live_server):
        """Deleting a MOTD entry removes it from the list."""
        page.goto(f"{live_server}/motd/new")
        page.fill('[name="text"]', "E2E MOTD To Delete unique-delete-xyz")
        page.locator('[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/motd")
        entry = page.locator(".card", has_text="E2E MOTD To Delete unique-delete-xyz").first
        page.on("dialog", lambda d: d.accept())
        entry.locator('form[action*="/delete"] button').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator("body")).not_to_contain_text("E2E MOTD To Delete unique-delete-xyz")

    def test_home_motd_widget_visible(self, page: Page, live_server):
        """After creating a MOTD, the home page shows the widget section."""
        page.goto(f"{live_server}/motd/new")
        page.fill('[name="text"]', "E2E Home Widget MOTD")
        page.locator('[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/")
        page.wait_for_timeout(500)  # let HTMX widget load
        expect(page.locator("#motd-widget")).to_be_visible()
