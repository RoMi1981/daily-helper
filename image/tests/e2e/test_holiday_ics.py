"""E2E tests for Holiday ICS Profiles — settings CRUD and calendar download."""

import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import Page, expect


def _create_holiday_ics_profile(live_server: str, name: str) -> None:
    """Create a holiday ICS profile via the settings API."""
    data = urllib.parse.urlencode({
        "name": name,
        "show_as": "free",
        "subject": "{name}",
        "body": "",
        "recipients_required": "",
        "recipients_optional": "",
        "category": "",
        "no_online_meeting": "",
    }).encode()
    req = urllib.request.Request(
        f"{live_server}/settings/holiday-ics-profiles",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError:
        pass  # 303 redirect — expected


class TestHolidayIcsSettings:
    def test_profile_appears_in_settings_after_create(self, page: Page, live_server):
        """A newly created holiday ICS profile is visible on the settings page."""
        _create_holiday_ics_profile(live_server, "E2E Holiday Settings Profile")
        page.goto(f"{live_server}/settings#holiday-ics-profiles")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Holiday Settings Profile").first).to_be_visible()


class TestHolidayIcsCalendarDownload:
    def test_download_button_appears_on_holiday_when_profile_configured(
        self, page: Page, live_server
    ):
        """When a holiday ICS profile exists, the download button is shown on holiday rows."""
        _create_holiday_ics_profile(live_server, "E2E Holiday Btn Profile")
        # January always contains New Year's Day (Neujahr) in Germany (default state BY)
        page.goto(f"{live_server}/calendar?year=2026&month=1")
        page.wait_for_load_state("networkidle")
        # Look for the ICS download button next to a holiday entry
        dl_button = page.locator('button[title="Download ICS"]').first
        dl_button.wait_for(state="visible", timeout=10000)
        expect(dl_button).to_be_visible()

    def test_holiday_ics_download_triggers_file(self, page: Page, live_server):
        """Clicking the holiday ICS download button produces a .ics file."""
        _create_holiday_ics_profile(live_server, "E2E Holiday DL Profile")
        page.goto(f"{live_server}/calendar?year=2026&month=1")
        page.wait_for_load_state("networkidle")

        with page.expect_download(timeout=15000) as dl_info:
            page.locator('button[title="Download ICS"]').first.click()

        dl = dl_info.value
        assert dl.suggested_filename.endswith(".ics"), (
            f"Expected .ics download, got: {dl.suggested_filename!r}"
        )
