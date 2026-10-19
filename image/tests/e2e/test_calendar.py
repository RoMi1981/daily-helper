"""E2E tests for the Calendar module — page load, navigation, capacity view."""

import re

from playwright.sync_api import Page, expect


class TestCalendarPage:
    def test_page_loads(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        expect(page.locator("h1")).to_be_visible()

    def test_calendar_grid_is_visible(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        expect(page.locator(".calendar-grid")).to_be_visible()

    def test_month_name_in_heading(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        heading = page.locator("h1").inner_text()
        # Heading should contain a year (four digits)
        assert re.search(r"\d{4}", heading), f"No year found in heading: {heading!r}"

    def test_prev_next_buttons_present(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        expect(page.locator('a[href*="month="]').first).to_be_visible()

    def test_today_button_present(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        # "Today" link navigates to /calendar without query params
        today_link = page.locator('a[href="/calendar"]')
        expect(today_link.first).to_be_visible()


class TestCalendarNavigation:
    def test_next_month_navigation(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        heading_before = page.locator("h1").inner_text()

        # Click the next-month button (›)
        page.locator('a[href*="month="]').last.click()
        page.wait_for_load_state("networkidle")

        heading_after = page.locator("h1").inner_text()
        assert heading_before != heading_after, "Month heading did not change after navigation"

    def test_prev_month_navigation(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        heading_before = page.locator("h1").inner_text()

        # Click the prev-month button (‹) — first link with month= param
        page.locator('a[href*="month="]').first.click()
        page.wait_for_load_state("networkidle")

        heading_after = page.locator("h1").inner_text()
        assert heading_before != heading_after, "Month heading did not change after navigation"

    def test_today_button_returns_to_current_month(self, page: Page, live_server):
        # Navigate to a different month first
        page.goto(f"{live_server}/calendar?year=2030&month=1")
        page.wait_for_load_state("networkidle")

        page.locator('a[href="/calendar"]').first.click()
        page.wait_for_load_state("networkidle")

        heading = page.locator("h1").inner_text()
        # Current test year is 2026
        assert "2026" in heading, f"Expected current year in heading, got: {heading!r}"


class TestCalendarCapacity:
    def test_capacity_page_loads(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        expect(page.locator("h1")).to_be_visible()

    def test_capacity_page_shows_sprint_cards(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        # Sprint cards should be visible since sprint is configured in conftest
        expect(page.locator(".sprint-card").first).to_be_visible()

    def test_sprint_card_has_work_days(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        card = page.locator(".sprint-card").first
        expect(card.locator(".sprint-work-days")).to_be_visible()

    def test_sprint_name_is_visible(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        card = page.locator(".sprint-card").first
        expect(card.locator(".sprint-name")).to_be_visible()

    def test_capacity_page_year_navigation(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar/capacity")
        page.wait_for_load_state("networkidle")
        heading_before = page.locator("h1").inner_text()

        page.locator('a[href*="/calendar/capacity?year="]').last.click()
        page.wait_for_load_state("networkidle")

        heading_after = page.locator("h1").inner_text()
        assert heading_before != heading_after, "Year heading did not change after navigation"

    def test_capacity_button_visible_on_calendar(self, page: Page, live_server):
        page.goto(f"{live_server}/calendar")
        page.wait_for_load_state("networkidle")
        # The capacity link is shown when sprint is configured
        expect(page.locator('a[href="/calendar/capacity"]')).to_be_visible()
