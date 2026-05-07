"""E2E tests for the Vacations module — create, status change, account summary, mail template."""

import pytest
from pathlib import Path
from playwright.sync_api import Page, expect


def _create_vacation(page: Page, base: str, start: str, end: str, note: str = "") -> None:
    """Submit the new vacation request form."""
    page.goto(f"{base}/vacations#new-form")
    page.fill('[name="start_date"]', start)
    page.fill('[name="end_date"]', end)
    if note:
        page.fill('[name="note"]', note)
    page.locator('form[action="/vacations"] [type="submit"]').click()
    page.wait_for_load_state("networkidle")


class TestVacationCreate:
    def test_vacation_appears_in_list(self, page: Page, live_server):
        """A newly created vacation request appears in the list."""
        _create_vacation(page, live_server, "2026-08-01", "2026-08-05", "E2E Summer")
        page.goto(f"{live_server}/vacations")
        expect(page.get_by_text("E2E Summer").first).to_be_visible()

    def test_vacation_shows_date_range(self, page: Page, live_server):
        """The created entry shows the correct start date."""
        _create_vacation(page, live_server, "2026-09-10", "2026-09-12", "E2E Conference")
        page.goto(f"{live_server}/vacations")
        expect(page.get_by_text("2026-09-10").first).to_be_visible()

    def test_vacation_default_status_is_planned(self, page: Page, live_server):
        """New vacation requests start with 'planned' status."""
        _create_vacation(page, live_server, "2026-10-01", "2026-10-03", "E2E Status Check")
        page.goto(f"{live_server}/vacations")
        card = page.locator(".vacation-card", has_text="E2E Status Check").first
        expect(card.get_by_text("Planned").first).to_be_visible()


class TestVacationStatusChange:
    def test_status_can_be_changed_to_approved(self, page: Page, live_server):
        """Status dropdown change to Approved reloads page with updated badge."""
        _create_vacation(page, live_server, "2026-11-01", "2026-11-03", "E2E Approve Me")
        page.goto(f"{live_server}/vacations")

        card = page.locator(".vacation-card", has_text="E2E Approve Me").first
        card.locator('select[name="status"]').select_option("approved")
        page.wait_for_load_state("networkidle")

        # After form submit, page reloads — card should show Approved
        updated_card = page.locator(".vacation-card", has_text="E2E Approve Me").first
        expect(updated_card.get_by_text("Approved").first).to_be_visible()


def _configure_mail_template(page: Page, base: str) -> None:
    """Save a vacation mail template via the settings form."""
    page.goto(f"{base}/settings")
    page.wait_for_load_state("networkidle")
    page.fill('[name="vacation_mail_to"]', "manager@example.com")
    page.fill('[name="vacation_mail_cc"]', "hr@example.com")
    page.fill('[name="vacation_mail_subject"]', "Urlaub {{from}} bis {{to}}")
    page.fill('[name="vacation_mail_body"]', "Hallo,\n\nUrlaub vom {{from}} bis {{to}} ({{working_days}} Werktage).\n\nGrüße")
    page.locator('form[action="/settings/vacation-mail"] [type="submit"]').click()
    page.wait_for_load_state("networkidle")


class TestVacationMailTemplate:
    def test_mail_template_settings_saved(self, page: Page, live_server):
        """Mail template fields are saved and page redirects back to vacation section."""
        _configure_mail_template(page, live_server)
        expect(page.locator(".alert-success").first).to_be_visible()

    def test_mail_button_visible_on_card(self, page: Page, live_server):
        """After configuring mail template, the 📧 button appears on vacation cards."""
        _configure_mail_template(page, live_server)
        _create_vacation(page, live_server, "2026-05-05", "2026-05-06", "E2E Mail Button")
        page.goto(f"{live_server}/vacations")
        card = page.locator(".vacation-card", has_text="E2E Mail Button").first
        expect(card.locator('a[href*="/mail"]')).to_be_visible()

    def test_mail_page_shows_filled_placeholders(self, page: Page, live_server):
        """Mail preview page replaces {{from}}/{{to}}/{{working_days}} with real values."""
        _configure_mail_template(page, live_server)
        _create_vacation(page, live_server, "2026-06-02", "2026-06-06", "E2E Mail Preview")
        page.goto(f"{live_server}/vacations")
        card = page.locator(".vacation-card", has_text="E2E Mail Preview").first
        card.locator('a[href*="/mail"]').click()
        page.wait_for_load_state("networkidle")
        # Subject placeholder replaced
        expect(page.locator('#mail-subject')).to_have_value("Urlaub 2026-06-02 bis 2026-06-06")
        # Body shows dates (plain text hidden textarea)
        body = page.locator('#mail-body-plain').input_value()
        assert "2026-06-02" in body
        assert "2026-06-06" in body

    def test_eml_download(self, page: Page, live_server):
        """EML download returns a file ending in .eml."""
        _configure_mail_template(page, live_server)
        _create_vacation(page, live_server, "2026-07-07", "2026-07-11", "E2E EML Download")
        page.goto(f"{live_server}/vacations")
        card = page.locator(".vacation-card", has_text="E2E EML Download").first
        card.locator('a[href*="/mail"]').click()
        page.wait_for_load_state("networkidle")
        with page.expect_download() as dl_info:
            page.locator('a[download]').click()
        assert dl_info.value.suggested_filename.endswith(".eml")


class TestVacationAccountSummary:
    def test_account_stats_are_visible(self, page: Page, live_server):
        """The account summary (Total / Used / Remaining) is rendered."""
        page.goto(f"{live_server}/vacations")
        expect(page.locator(".vacation-stat-label", has_text="Total")).to_be_visible()
        expect(page.locator(".vacation-stat-label", has_text="Remaining")).to_be_visible()

    def test_account_total_is_numeric(self, page: Page, live_server):
        """Total days shown is a valid number (int or decimal for half-day carryover)."""
        page.goto(f"{live_server}/vacations")
        stats = page.locator(".vacation-stat-value").all()
        assert len(stats) > 0
        for stat in stats:
            val = stat.inner_text().strip()
            try:
                float(val)
            except ValueError:
                assert False, f"Expected number, got: {val!r}"
