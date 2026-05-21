"""E2E tests for the Operations module — copy and move content between repos."""

from playwright.sync_api import Page, expect
from .conftest import E2E_REPO_ID, E2E_REPO_ID_2


def _create_note(page: Page, base: str, subject: str, body: str) -> None:
    page.goto(f"{base}/notes/new")
    page.fill('[name="subject"]', subject)
    page.fill('[name="body"]', body)
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")


def _submit_ops_form(page: Page) -> None:
    """Submit the operations form, accepting the confirm() dialog."""
    page.on("dialog", lambda d: d.accept())
    page.get_by_role("button", name="Execute").click()
    page.wait_for_load_state("networkidle")


class TestOperationsPage:
    def test_operations_page_shows_both_repos(self, page: Page, live_server):
        """Operations page lists both configured repos as source options."""
        page.goto(f"{live_server}/operations")
        src_select = page.locator('#src-select')
        # Use exact value attributes to avoid partial-text strict mode violations
        expect(src_select.locator(f'option[value="{E2E_REPO_ID}"]')).to_be_attached()
        expect(src_select.locator(f'option[value="{E2E_REPO_ID_2}"]')).to_be_attached()

    def test_content_type_tabs_visible(self, page: Page, live_server):
        """Content type filter tabs are shown when a source repo is selected."""
        page.goto(f"{live_server}/operations?src={E2E_REPO_ID}&type=notes")
        page.wait_for_load_state("networkidle")
        # Use ops-form scope to avoid matching sidebar nav links
        ops_form = page.locator('#ops-form')
        expect(ops_form.locator('a', has_text="Notes")).to_be_visible()
        expect(ops_form.locator('a', has_text="Links")).to_be_visible()

    def test_select_all_checks_all_items(self, page: Page, live_server):
        """'Select all' button checks all item checkboxes."""
        _create_note(page, live_server, "E2E Select All Note", "For select-all test.")
        page.goto(f"{live_server}/operations?src={E2E_REPO_ID}&type=notes")
        page.wait_for_load_state("networkidle")

        # Deselect first, then select — use exact=True to avoid matching "Deselect all"
        page.get_by_role("button", name="Deselect all", exact=True).click()
        page.get_by_role("button", name="Select all", exact=True).click()

        checkboxes = page.locator('input[name="items"]').all()
        assert len(checkboxes) > 0
        for cb in checkboxes:
            expect(cb).to_be_checked()

    def test_deselect_all_unchecks_all_items(self, page: Page, live_server):
        """'Deselect all' button unchecks all item checkboxes."""
        _create_note(page, live_server, "E2E Deselect Note", "For deselect-all test.")
        page.goto(f"{live_server}/operations?src={E2E_REPO_ID}&type=notes")
        page.wait_for_load_state("networkidle")

        page.get_by_role("button", name="Deselect all", exact=True).click()

        checkboxes = page.locator('input[name="items"]').all()
        assert len(checkboxes) > 0
        for cb in checkboxes:
            expect(cb).not_to_be_checked()


class TestOperationsCopy:
    def test_copy_note_to_second_repo(self, page: Page, live_server):
        """A note can be copied from repo 1 to repo 2 with a success message."""
        _create_note(page, live_server, "E2E Ops Copy Note", "Content for cross-repo copy.")

        page.goto(f"{live_server}/operations?src={E2E_REPO_ID}&type=notes")
        page.wait_for_load_state("networkidle")

        # Deselect all, then select only our note via its label
        page.get_by_role("button", name="Deselect all", exact=True).click()
        page.locator('label', has_text="E2E Ops Copy Note").first.click()

        # Set destination repo and action
        page.locator('[name="dst_repo"]').select_option(E2E_REPO_ID_2)
        page.locator('input[name="action"][value="copy"]').check()

        # Accept the confirm() dialog and submit
        _submit_ops_form(page)

        expect(page.locator(".alert-success")).to_be_visible()
        expect(page.locator(".alert-success")).to_contain_text("copied successfully")

    def test_copy_with_no_items_selected_shows_error(self, page: Page, live_server):
        """Submitting with nothing selected shows an error message."""
        _create_note(page, live_server, "E2E Ops Empty Note", "Should not be copied.")

        page.goto(f"{live_server}/operations?src={E2E_REPO_ID}&type=notes")
        page.wait_for_load_state("networkidle")

        page.get_by_role("button", name="Deselect all", exact=True).click()
        page.locator('[name="dst_repo"]').select_option(E2E_REPO_ID_2)

        _submit_ops_form(page)

        # Router returns "0 item(s) copied" result + "Nothing to copy" error
        expect(page.locator(".alert-error").first).to_be_visible()


class TestOperationsZip:
    def test_export_zip_returns_zip_content(self, page: Page, live_server):
        """GET /operations/export returns application/zip with correct filename."""
        resp = page.request.get(
            f"{live_server}/operations/export",
            params={"repo_id": E2E_REPO_ID},
        )
        assert resp.status == 200
        assert "application/zip" in resp.headers.get("content-type", "")
        cd = resp.headers.get("content-disposition", "")
        assert "daily-helper_" in cd
        assert ".zip" in cd

    def test_import_section_visible(self, page: Page, live_server):
        """Import form with repo select, file input and mode radios is visible."""
        page.goto(f"{live_server}/operations")
        page.wait_for_load_state("networkidle")
        expect(page.locator('input[type="file"][name="file"]').first).to_be_attached()
        expect(page.locator('input[name="mode"][value="merge"]').first).to_be_attached()
        expect(page.locator('input[name="mode"][value="overwrite"]').first).to_be_attached()
