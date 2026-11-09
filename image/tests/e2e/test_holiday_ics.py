"""E2E tests for Holiday ICS Profiles — settings CRUD and calendar download."""

import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import Page, expect


def _create_holiday_ics_profile(live_server: str, name: str) -> None:
    """Create a holiday ICS profile via the settings API."""
    data = urllib.parse.urlencode(
        {
            "name": name,
            "show_as": "free",
            "subject": "{name}",
            "body": "",
            "recipients_required": "",
            "recipients_optional": "",
            "category": "",
            "no_online_meeting": "",
        }
    ).encode()
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
    def test_download_button_appears_on_holiday_when_profile_configured(self, page: Page, live_server):
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
        assert dl.suggested_filename.endswith(".ics"), f"Expected .ics download, got: {dl.suggested_filename!r}"


class TestHolidayIcsLikeVacations:
    def test_plain_download_button_produces_holiday_file(self, page: Page, live_server):
        """Without holiday profiles, every holiday has a plain "Download for
        Outlook" button instead of the profile button, as vacations do."""
        import re

        # Earlier tests in this session created profiles; remove them all.
        page.goto(f"{live_server}/settings")
        for pid in set(re.findall(r"/settings/holiday-ics-profiles/([^/\"]+)/delete", page.content())):
            page.request.post(f"{live_server}/settings/holiday-ics-profiles/{pid}/delete", max_redirects=0)
        page.goto(f"{live_server}/calendar?year=2026&month=1")
        page.wait_for_load_state("networkidle")

        with page.expect_download(timeout=15000) as dl_info:
            page.locator('a[title="Download for Outlook"][href*="date=2026-01-01"]').click()

        name = dl_info.value.suggested_filename
        assert name.startswith("holiday_2026-01-01_") and name.endswith(".ics"), name
        expect(page.locator('button[title="Download ICS"]')).to_have_count(0)

    def test_own_blocker_created_in_settings_is_exported_with_times(self, page: Page, live_server):
        """Create the own blocker through the form (uncheck "all day", set times)
        and check that the holiday export carries those times."""
        import re
        import uuid

        name = f"E2E Own Blocker {uuid.uuid4().hex[:6]}"
        page.goto(f"{live_server}/settings#holiday-ics-profiles")
        page.wait_for_load_state("networkidle")
        page.locator("#holiday-ics-profiles").get_by_role("button", name="Add profile").first.click()
        form = page.locator("#new-hol-ics-profile-form form")
        form.locator('input[name="name"]').fill(name)
        form.locator('select[name="show_as"]').select_option("oof")
        allday = form.locator("#hol-ics-new-allday")
        expect(allday).to_be_checked()  # same default as the vacation form
        allday.uncheck()
        form.locator('input[name="start_time"]').fill("08:05")
        form.locator('input[name="end_time"]').fill("17:00")
        form.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        card = page.locator(".template-card", has=page.get_by_text(name, exact=True))
        expect(card.locator(".hint").first).to_contain_text("08:05–17:00")
        profile_id = re.search(r"toggleHolIcsEditForm\('([^']+)'\)", card.inner_html()).group(1)

        resp = page.request.get(f"{live_server}/calendar/holiday.ics?date=2026-01-01&name=Neujahr&profile={profile_id}")
        assert resp.ok
        ics = resp.text()
        assert "DTSTART;TZID=Europe/Berlin:20260101T080500" in ics
        assert "DTEND;TZID=Europe/Berlin:20260101T170000" in ics
        assert "X-MICROSOFT-CDO-BUSYSTATUS:OOF" in ics

        # With a profile in place the calendar offers the profile button, not the plain one.
        page.goto(f"{live_server}/calendar?year=2026&month=1")
        page.wait_for_load_state("networkidle")
        expect(page.locator('button[title="Download ICS"]').first).to_be_visible()
        expect(page.locator('a[title="Download for Outlook"][href*="holiday.ics"]')).to_have_count(0)

        page.request.post(f"{live_server}/settings/holiday-ics-profiles/{profile_id}/delete", max_redirects=0)
