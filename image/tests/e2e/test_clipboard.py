"""E2E tests for clipboard copy buttons — Mail Templates and Links."""

from playwright.sync_api import Page, expect


def _create_mail_template(
    page: Page, base: str, name: str, to: str, subject: str, body: str
) -> None:
    page.goto(f"{base}/mail-templates/new")
    page.fill('[name="name"]', name)
    page.fill('[name="to"]', to)
    page.fill('[name="subject"]', subject)
    page.fill('[name="body"]', body)
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")


def _create_link(page: Page, base: str, title: str, url: str) -> None:
    page.goto(f"{base}/links/new")
    page.fill('[name="title"]', title)
    page.fill('[name="url"]', url)
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")


class TestMailTemplateClipboard:
    def test_copy_to_puts_address_in_clipboard(self, page: Page, live_server):
        """Clicking the To copy button copies the address to clipboard."""
        _create_mail_template(
            page,
            live_server,
            "E2E Clipboard Template",
            to="recipient@example.com",
            subject="E2E Subject",
            body="E2E Body text",
        )
        page.goto(f"{live_server}/mail-templates")
        page.wait_for_load_state("networkidle")

        # Click the 📋 button next to "To:"
        card = page.locator(".card", has_text="E2E Clipboard Template").first
        card.wait_for(state="visible")
        card.locator('button[title="Copy"]').first.click()
        page.wait_for_timeout(300)

        clipboard_text = page.evaluate("navigator.clipboard.readText()")
        assert clipboard_text == "recipient@example.com", (
            f"Expected email in clipboard, got: {clipboard_text!r}"
        )

    def test_copy_subject_puts_subject_in_clipboard(self, page: Page, live_server):
        """Clicking the Subject copy button copies the subject line."""
        _create_mail_template(
            page,
            live_server,
            "E2E Subject Template",
            to="x@example.com",
            subject="E2E Unique Subject 12345",
            body="body",
        )
        page.goto(f"{live_server}/mail-templates")

        card = page.locator(".card", has_text="E2E Subject Template").first
        # Subject button is the third copy button (To, CC if present, Subject)
        subject_btn = card.locator('button[title="Copy"]').nth(1)
        subject_btn.click()
        page.wait_for_timeout(300)

        clipboard_text = page.evaluate("navigator.clipboard.readText()")
        assert "E2E Unique Subject 12345" in clipboard_text, (
            f"Subject not in clipboard: {clipboard_text!r}"
        )


class TestLinkUrlClipboard:
    def test_copy_url_button_copies_link_url(self, page: Page, live_server):
        """Clicking 📋 on a link card copies the URL to clipboard."""
        _create_link(page, live_server, "E2E Clipboard Link", "https://clipboard-test.example.com")
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")

        card = page.locator(".card", has_text="E2E Clipboard Link").first
        card.wait_for(state="visible")
        card.locator('button[title="Copy URL"]').click()
        page.wait_for_timeout(300)

        clipboard_text = page.evaluate("navigator.clipboard.readText()")
        assert clipboard_text == "https://clipboard-test.example.com", (
            f"Expected URL in clipboard, got: {clipboard_text!r}"
        )
