"""E2E tests for the Notes module — create, view, encrypt/decrypt."""

import re
import uuid
import pytest
from playwright.sync_api import Page, expect


def _uid() -> str:
    """Short unique suffix to avoid collisions with data from previous runs."""
    return uuid.uuid4().hex[:6]


def _create_note(page: Page, base: str, subject: str, body: str, encrypt: bool = False) -> str:
    """Create a note and return the detail URL."""
    page.goto(f"{base}/notes/new")
    page.fill('[name="subject"]', subject)
    page.fill('[name="body"]', body)
    if encrypt:
        page.check('[name="encrypt"]')
    page.click('button[type="submit"]')
    # Note IDs are 8-char hex — wait for redirect away from /notes/new
    page.wait_for_url(re.compile(r"/notes/[a-f0-9]{8}$"), timeout=10000)
    return page.url


class TestNoteCreateAndView:
    def test_note_appears_in_list(self, page: Page, live_server):
        _create_note(page, live_server, "E2E Plain Note", "Plain body content")
        page.goto(f"{live_server}/notes")
        expect(page.get_by_text("E2E Plain Note").first).to_be_visible()

    def test_note_detail_shows_body(self, page: Page, live_server):
        url = _create_note(page, live_server, "E2E Detail Note", "Detail body here")
        page.goto(url)
        expect(page.get_by_text("Detail body here")).to_be_visible()

    def test_cursor_at_end_on_edit(self, page: Page, live_server):
        """Textarea cursor is positioned at the end when opening edit form."""
        detail_url = _create_note(page, live_server, "E2E Edit Cursor", "Some body text")
        edit_url = detail_url.rstrip("/") + "/edit"
        page.goto(edit_url)

        # The JS runs focus+setSelectionRange on load — wait for it
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(200)

        cursor_at_end = page.evaluate("""() => {
            const ta = document.querySelector('textarea[name="body"]');
            if (!ta) return false;
            ta.focus();
            return ta.selectionStart === ta.value.length;
        }""")
        assert cursor_at_end, "Cursor should be at end of textarea on edit"


class TestNoteEncryption:
    def test_encrypted_note_body_visible_in_detail(self, page: Page, live_server):
        """Body of an encrypted note is shown as plaintext in the detail view."""
        url = _create_note(page, live_server, "E2E Encrypted Note", "Top secret text", encrypt=True)
        page.goto(url)
        expect(page.get_by_text("Top secret text")).to_be_visible()
        assert "enc:" not in page.content(), "Raw ciphertext must not be visible in frontend"

    def test_encrypted_note_searchable(self, page: Page, live_server):
        """Encrypted notes are findable via search (transparent decrypt)."""
        _create_note(page, live_server, "E2E Searchable Secret", "classified payload", encrypt=True)
        page.goto(f"{live_server}/notes?q=classified+payload")
        expect(page.get_by_text("E2E Searchable Secret")).to_be_visible()


class TestNoteArchive:
    def test_archive_button_visible_on_detail(self, page: Page, live_server):
        """Archive button is shown on note detail page."""
        url = _create_note(page, live_server, "E2E Archive Button", "body text")
        page.goto(url)
        expect(page.get_by_role("button", name="Archive")).to_be_visible()

    def test_archive_moves_note_to_archive(self, page: Page, live_server):
        """Archiving a note removes it from active list and shows it in archive."""
        title = f"E2E Archive Me {_uid()}"
        url = _create_note(page, live_server, title, "some content")

        # Archive directly from detail page
        page.goto(url)
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="Archive").click()
        page.wait_for_url(re.compile(r"/notes$"), timeout=10000)

        # Unique title — no old copies, so not_to_be_visible is reliable
        expect(page.get_by_text(title)).not_to_be_visible()

    def test_archived_note_appears_in_archive_page(self, page: Page, live_server):
        """Archived note is listed on /notes/archive."""
        title = f"E2E In Archive {_uid()}"
        url = _create_note(page, live_server, title, "archived body")
        page.goto(url)
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="Archive").click()
        page.wait_for_url(re.compile(r"/notes$"), timeout=10000)

        page.goto(f"{live_server}/notes/archive")
        expect(page.get_by_text(title).first).to_be_visible()

    def test_restore_moves_note_back(self, page: Page, live_server):
        """Restoring an archived note brings it back to active list."""
        title = f"E2E Restore Me {_uid()}"
        url = _create_note(page, live_server, title, "restore content")
        page.goto(url)
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="Archive").click()
        page.wait_for_url(re.compile(r"/notes$"), timeout=10000)

        # Go to archive and restore the specific note by its unique title
        page.goto(f"{live_server}/notes/archive")
        page.locator(f'.card:has-text("{title}") button:has-text("Restore")').click()
        page.wait_for_url(re.compile(r"/notes/archive$"), timeout=10000)

        # Unique title — no old copies
        expect(page.get_by_text(title)).not_to_be_visible()

        # Active notes should have it back
        page.goto(f"{live_server}/notes")
        expect(page.get_by_text(title).first).to_be_visible()

    def test_archive_link_visible_on_notes_list(self, page: Page, live_server):
        """Archive navigation link is shown on notes list page."""
        page.goto(f"{live_server}/notes")
        expect(page.get_by_role("link", name="Archive").first).to_be_visible()


class TestNoteDblClick:
    def test_dblclick_on_detail_navigates_to_edit(self, page: Page, live_server):
        """Double-clicking the note body on the detail page navigates to edit."""
        detail_url = _create_note(page, live_server, f"E2E DblClick {_uid()}", "click test body")
        page.goto(detail_url)
        page.wait_for_load_state("networkidle")

        page.locator("#note-body").dblclick()
        page.wait_for_url(re.compile(r"/notes/[a-f0-9]{8}/edit$"), timeout=10_000)
        expect(page.locator('textarea[name="body"]')).to_be_visible()

    def test_single_click_on_list_opens_detail(self, page: Page, live_server):
        """Single click on note card in list opens the detail page, not edit."""
        title = f"E2E SingleClick {_uid()}"
        _create_note(page, live_server, title, "single click body")

        page.goto(f"{live_server}/notes")
        page.wait_for_load_state("networkidle")

        page.locator(f'a[href*="/notes/"]', has_text=title).first.click()
        page.wait_for_url(re.compile(r"/notes/[a-f0-9]{8}$"), timeout=10_000)
        assert "/edit" not in page.url
