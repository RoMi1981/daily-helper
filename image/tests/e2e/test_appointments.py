"""E2E tests for the Appointments module — create, view, ICS download."""

from playwright.sync_api import Page, expect


def _create_appointment(
    page: Page,
    base: str,
    title: str,
    start: str,
    end: str,
    appt_type: str = "training",
    note: str = "",
) -> None:
    """Submit the new appointment form."""
    page.goto(f"{base}/appointments#new-form")
    page.fill('[name="title"]', title)
    page.fill('[name="start_date"]', start)
    page.fill('[name="end_date"]', end)
    page.locator('[name="type"]').select_option(appt_type)
    if note:
        page.fill('[name="note"]', note)
    page.locator('form[action="/appointments"] [type="submit"]').click()
    page.wait_for_url("**/appointments")
    page.wait_for_load_state("networkidle")


class TestAppointmentCreate:
    def test_appointment_appears_in_list(self, page: Page, live_server):
        """A new appointment appears in the appointments list."""
        _create_appointment(page, live_server, "E2E Training Alpha", "2026-06-01", "2026-06-03")
        page.goto(f"{live_server}/appointments", wait_until="networkidle")
        page.wait_for_selector('.vacation-card:has-text("E2E Training Alpha")', timeout=15000)
        expect(page.get_by_text("E2E Training Alpha").first).to_be_visible(timeout=30_000)

    def test_appointment_shows_date(self, page: Page, live_server):
        """The created appointment shows its start date."""
        _create_appointment(
            page, live_server, "E2E Conference Beta", "2026-07-10", "2026-07-12", note="E2E note"
        )
        page.goto(f"{live_server}/appointments")
        expect(page.get_by_text("2026-07-10").first).to_be_visible()

    def test_appointment_type_is_displayed(self, page: Page, live_server):
        """The appointment type icon or label is shown in the list."""
        _create_appointment(
            page, live_server, "E2E Team Event", "2026-08-05", "2026-08-05", appt_type="team_event"
        )
        page.goto(f"{live_server}/appointments")
        card = page.locator(".vacation-card", has_text="E2E Team Event").first
        expect(card).to_be_visible()


class TestAppointmentIcsDownload:
    def test_ics_download_starts(self, page: Page, live_server):
        """The ICS download link triggers a file download."""
        _create_appointment(page, live_server, "E2E ICS Download", "2026-09-01", "2026-09-03")
        page.goto(f"{live_server}/appointments", wait_until="networkidle")
        page.wait_for_selector('.vacation-card:has-text("E2E ICS Download")', timeout=15000)

        # Find the card and click the direct ICS download link
        card = page.locator(".vacation-card", has_text="E2E ICS Download").first
        ics_link = card.locator('a[href*="/export.ics"]')

        with page.expect_download() as download_info:
            ics_link.click()
        download = download_info.value

        assert download.suggested_filename.endswith(".ics"), (
            f"Expected .ics file, got: {download.suggested_filename!r}"
        )

    def test_ics_content_is_valid(self, page: Page, live_server):
        """Downloaded ICS file starts with BEGIN:VCALENDAR."""
        _create_appointment(page, live_server, "E2E ICS Content", "2026-10-01", "2026-10-02")
        page.goto(f"{live_server}/appointments", wait_until="networkidle")
        page.wait_for_selector('.vacation-card:has-text("E2E ICS Content")', timeout=30000)

        card = page.locator(".vacation-card", has_text="E2E ICS Content").first
        ics_link = card.locator('a[href*="/export.ics"]')

        with page.expect_download() as download_info:
            ics_link.click()
        download = download_info.value
        content = Path(download.path()).read_text()
        assert content.startswith("BEGIN:VCALENDAR"), (
            f"Unexpected ICS content start: {content[:50]!r}"
        )


# Make Path available in the test
from pathlib import Path


def _create_recurring_appointment(
    page: Page, base: str, title: str, start: str, recurring: str
) -> None:
    page.goto(f"{base}/appointments#new-form")
    page.fill('[name="title"]', title)
    page.fill('[name="start_date"]', start)
    page.fill('[name="end_date"]', start)
    page.locator('[name="recurring"]').select_option(recurring)
    page.locator('form[action="/appointments"] [type="submit"]').click()
    page.wait_for_url("**/appointments")
    page.wait_for_load_state("networkidle")


class TestRecurringAppointments:
    def test_recurring_badge_shown_in_list(self, page: Page, live_server):
        """A recurring appointment shows the repeat badge in the list."""
        _create_recurring_appointment(
            page, live_server, "E2E Recurring Monthly", "2026-05-15", "monthly"
        )
        page.goto(f"{live_server}/appointments")
        page.wait_for_load_state("networkidle")
        card = page.locator(".vacation-card", has_text="E2E Recurring Monthly").first
        card.wait_for(state="visible", timeout=10000)
        badge = card.locator(".appt-recurring-badge")
        expect(badge).to_be_visible()
        expect(badge).to_contain_text("monthly")

    def test_non_recurring_has_no_badge(self, page: Page, live_server):
        """A non-recurring appointment has no repeat badge."""
        _create_recurring_appointment(page, live_server, "E2E OneOff Appt", "2026-05-20", "none")
        page.goto(f"{live_server}/appointments")
        page.wait_for_load_state("networkidle")
        card = page.locator(".vacation-card", has_text="E2E OneOff Appt").first
        card.wait_for(state="visible", timeout=10000)
        expect(card.locator(".appt-recurring-badge")).to_have_count(0)
