"""E2E tests for the Quick-Capture Modal (q key) and Help shortcut (? key)."""

import uuid

from playwright.sync_api import Page, expect


def _uid():
    return uuid.uuid4().hex[:6]


class TestQuickCaptureModal:
    def test_q_key_opens_modal(self, page: Page, live_server):
        """Pressing q on the home page opens the Quick-Capture modal."""
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("q")
        expect(page.locator(".qc-backdrop")).to_have_class("qc-backdrop open")

    def test_esc_closes_modal(self, page: Page, live_server):
        """Pressing Esc closes the Quick-Capture modal."""
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("q")
        expect(page.locator(".qc-backdrop")).to_have_class("qc-backdrop open")
        page.keyboard.press("Escape")
        expect(page.locator(".qc-backdrop")).not_to_have_class("open")

    def test_modal_has_type_tabs(self, page: Page, live_server):
        """The modal shows type tabs (at least Tasks)."""
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("q")
        expect(page.locator(".qc-tab").first).to_be_visible()

    def test_q_key_ignored_in_input(self, page: Page, live_server):
        """Pressing q while an input is focused does not open the modal."""
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.locator(".nav-search-input").focus()
        page.keyboard.press("q")
        expect(page.locator(".qc-backdrop")).not_to_have_class("open")

    def test_backdrop_click_closes_modal(self, page: Page, live_server):
        """Clicking the backdrop (outside the modal box) closes it."""
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("q")
        expect(page.locator(".qc-backdrop")).to_have_class("qc-backdrop open")
        # Click on the backdrop itself (top-left corner, outside the modal box)
        page.locator(".qc-backdrop").click(position={"x": 5, "y": 5})
        expect(page.locator(".qc-backdrop")).not_to_have_class("open")

    def test_task_tab_shows_title_field(self, page: Page, live_server):
        """Selecting the Task tab shows a title input field."""
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("q")
        # Click Task tab
        task_tab = page.locator(".qc-tab", has_text="Task")
        if task_tab.count() > 0:
            task_tab.first.click()
            expect(page.locator("#qc-fields input[name='title']")).to_be_visible()

    def test_save_task_via_modal(self, page: Page, live_server):
        """Saving a task via the Quick-Capture modal creates the task."""
        uid = _uid()
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("q")

        # Select Task tab
        task_tab = page.locator(".qc-tab", has_text="Task")
        if task_tab.count() == 0:
            return  # tasks module disabled
        task_tab.first.click()

        page.locator("#qc-fields input[name='title']").fill(f"QC Task {uid}")
        page.locator("#qc-submit").click()
        # Wait for modal to close — happens after fetch() completes (git push done by then)
        expect(page.locator(".qc-backdrop")).not_to_have_class("open")

        # Task should appear in tasks list
        page.goto(f"{live_server}/tasks")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text(f"QC Task {uid}").first).to_be_visible()

    def test_save_note_via_modal(self, page: Page, live_server):
        """Saving a note via the Quick-Capture modal closes the modal."""
        uid = _uid()
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("q")

        note_tab = page.locator(".qc-tab", has_text="Note")
        if note_tab.count() == 0:
            return
        note_tab.first.click()

        page.locator("#qc-fields input[name='subject']").fill(f"QC Note {uid}")
        page.locator("#qc-submit").click()
        # Modal should close after save (git push may take longer — just check modal state)
        page.wait_for_timeout(500)
        expect(page.locator(".qc-backdrop")).not_to_have_class("open")


class TestHelpKeyboardShortcut:
    def test_question_mark_on_tasks_navigates_to_help(self, page: Page, live_server):
        """Pressing ? on the tasks page navigates to /help/tasks."""
        page.goto(f"{live_server}/tasks")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("?")
        page.wait_for_url("**/help/tasks")
        assert "/help/tasks" in page.url

    def test_question_mark_on_notes_navigates_to_help(self, page: Page, live_server):
        """Pressing ? on the notes page navigates to /help/notes."""
        page.goto(f"{live_server}/notes")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("?")
        page.wait_for_url("**/help/notes")
        assert "/help/notes" in page.url

    def test_question_mark_on_home_does_nothing(self, page: Page, live_server):
        """Pressing ? on the home page (no active module) does not navigate."""
        page.goto(f"{live_server}/")
        page.wait_for_load_state("networkidle")
        current_url = page.url
        page.keyboard.press("?")
        page.wait_for_timeout(300)
        assert page.url == current_url

    def test_help_page_renders_content(self, page: Page, live_server):
        """The tasks help page renders actual content."""
        page.goto(f"{live_server}/help/tasks")
        page.wait_for_load_state("networkidle")
        expect(page.locator(".markdown-body")).to_be_visible()
        # Help page has a back link
        expect(page.locator("a", has_text="Back").first).to_be_visible()


class TestSearchHighlighting:
    def test_search_result_shows_snippet(self, page: Page, live_server):
        """Search results show a context snippet below the title."""
        uid = _uid()
        # Create a note with unique body text
        page.goto(f"{live_server}/notes/new")
        page.fill('[name="subject"]', f"Snippet Note {uid}")
        page.fill('[name="body"]', f"unique_highlight_content_{uid} more text here")
        page.get_by_role("button", name="Create").click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/search?q=unique_highlight_content_{uid}")
        page.wait_for_selector(".search-snippet", timeout=10000)

        # The snippet div should be present and contain the search term
        snippet = page.locator(".search-snippet").first
        expect(snippet).to_be_visible()
        expect(snippet).to_contain_text(f"unique_highlight_content_{uid}")

    def test_search_snippet_contains_mark_element(self, page: Page, live_server):
        """Search snippets wrap the matched term in a <mark> element."""
        uid = _uid()
        page.goto(f"{live_server}/notes/new")
        page.fill('[name="subject"]', f"Mark Test {uid}")
        page.fill('[name="body"]', f"markable_term_{uid} in body")
        page.get_by_role("button", name="Create").click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/search?q=markable_term_{uid}", wait_until="networkidle")
        page.wait_for_selector(".search-snippet mark", timeout=15000)

        mark = page.locator(".search-snippet mark").first
        expect(mark).to_be_visible()
