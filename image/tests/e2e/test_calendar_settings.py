"""E2E tests for calendar settings — weekends toggle."""

from playwright.sync_api import Page, expect


class TestCalendarWeekends:
    def test_calendar_shows_7_columns_by_default(self, page: Page, live_server):
        """Calendar renders 7 day columns (Mon–Sun) by default."""
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        headers = page.locator(".calendar-header").all()
        assert len(headers) == 7

    def test_hide_weekends_shows_5_columns(self, page: Page, live_server):
        """After disabling weekends, calendar renders only 5 columns (Mon–Fri)."""
        # Disable weekends in settings
        page.goto(f"{live_server}/settings")
        page.wait_for_load_state("networkidle")
        checkbox = page.locator('[name="calendar_show_weekends"]')
        if checkbox.is_checked():
            checkbox.uncheck()
        page.locator('form:has([name="vacation_state"]) button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        headers = page.locator(".calendar-header").all()
        assert len(headers) == 5

        # Restore setting
        page.goto(f"{live_server}/settings")
        page.wait_for_load_state("networkidle")
        page.locator('[name="calendar_show_weekends"]').check()
        page.locator('form:has([name="vacation_state"]) button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

    def test_weekend_legend_hidden_when_weekends_off(self, page: Page, live_server):
        """Weekend legend entry is hidden when weekends are disabled."""
        # Disable weekends
        page.goto(f"{live_server}/settings")
        page.wait_for_load_state("networkidle")
        checkbox = page.locator('[name="calendar_show_weekends"]')
        if checkbox.is_checked():
            checkbox.uncheck()
        page.locator('form:has([name="vacation_state"]) button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        expect(page.locator(".calendar-legend").get_by_text("Weekend")).not_to_be_visible()

        # Restore
        page.goto(f"{live_server}/settings")
        page.wait_for_load_state("networkidle")
        page.locator('[name="calendar_show_weekends"]').check()
        page.locator('form:has([name="vacation_state"]) button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
