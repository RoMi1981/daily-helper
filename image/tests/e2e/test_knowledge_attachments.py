"""E2E tests for Knowledge file attachments."""

from playwright.sync_api import Page, expect


def _create_entry(page: Page, base: str, title: str, category: str = "E2E-Attach") -> str:
    page.goto(f"{base}/knowledge/new")
    cat = page.locator("#category")
    options = cat.locator("option").all()
    existing = [o.get_attribute("value") for o in options]
    if category in existing:
        cat.select_option(category)
    else:
        cat.select_option("__new__")
        page.fill('[name="new_category"]', category)
    page.fill('[name="title"]', title)
    page.fill('[name="content"]', "Content for attachment test.")
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    return page.url


def _upload_file(page: Page, filename: str, content: bytes = b"test content"):
    """Upload a file via the hidden file input (auto-submits on change)."""
    # Unhide the input so Playwright can interact with it
    page.evaluate("document.querySelector('input[name=\"file\"]').style.display = 'block'")
    file_input = page.locator('input[name="file"]')
    file_input.set_input_files(
        {
            "name": filename,
            "mimeType": "text/plain",
            "buffer": content,
        }
    )
    page.wait_for_load_state("networkidle")


class TestKnowledgeAttachments:
    def test_attachment_section_visible_on_detail(self, page: Page, live_server):
        """Entry detail page shows an attachments section."""
        url = _create_entry(page, live_server, "E2E Attach Section Entry")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("Attachments").first).to_be_visible()

    def test_upload_file_shows_download_link(self, page: Page, live_server):
        """Uploading a file creates a download link on the detail page."""
        url = _create_entry(page, live_server, "E2E Upload Entry")
        page.goto(url)
        _upload_file(page, "hello.txt")
        expect(page.get_by_role("link", name="hello.txt").first).to_be_visible()

    def test_delete_attachment_removes_link(self, page: Page, live_server):
        """Clicking × on an attachment removes it from the page."""
        url = _create_entry(page, live_server, "E2E Delete Attach Entry")
        page.goto(url)
        _upload_file(page, "removeme.txt")
        expect(page.get_by_role("link", name="removeme.txt").first).to_be_visible()

        # Click the × delete button (auto-confirms dialog)
        page.once("dialog", lambda d: d.accept())
        page.locator(".btn-danger").last.click()
        page.wait_for_load_state("networkidle")

        expect(page.get_by_role("link", name="removeme.txt")).not_to_be_visible()
