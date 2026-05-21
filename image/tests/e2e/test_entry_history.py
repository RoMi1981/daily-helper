"""E2E tests for per-entry version history (Tasks, Notes, Runbooks, Snippets)."""

import re
from playwright.sync_api import Page, expect


def _create_task(page: Page, base: str, title: str) -> str:
    """Create a task via the quick-create form and return its ID."""
    page.goto(f"{base}/tasks#new-form")
    page.fill('[name="title"]', title)
    page.locator('form [type="submit"]').first.click()
    page.wait_for_load_state("networkidle")
    # Wait for the task card to appear after git commit + page reload
    page.wait_for_selector(f'.task-card:has-text("{title}")', timeout=30000)
    # Find the task ID from the edit link
    edit_link = page.locator(f'.task-card:has-text("{title}") a[href*="/edit"]').first
    href = edit_link.get_attribute("href", timeout=20_000)
    return href.split("/tasks/")[1].split("/")[0]


def _create_note(page: Page, base: str, subject: str, body: str) -> str:
    """Create a note and return its detail URL."""
    page.goto(f"{base}/notes/new")
    page.fill('[name="subject"]', subject)
    page.fill('[name="body"]', body)
    page.click('button[type="submit"]')
    page.wait_for_url(re.compile(r"/notes/[a-f0-9]{8}$"), timeout=10_000)
    return page.url


def _create_runbook(page: Page, base: str, title: str) -> str:
    """Create a runbook and return its ID."""
    page.goto(f"{base}/runbooks/new")
    page.fill('[name="title"]', title)
    page.locator('button[type="submit"]').click()
    page.wait_for_url(re.compile(r"/runbooks/[a-f0-9]{8}$"), timeout=10_000)
    return page.url.split("/runbooks/")[1]


def _create_snippet(page: Page, base: str, title: str) -> str:
    """Create a snippet and return its ID."""
    page.goto(f"{base}/snippets/new")
    page.fill('[name="title"]', title)
    page.locator('textarea[name="step_cmd_0"]').first.fill("echo hello")
    page.locator('button[type="submit"]').click()
    page.wait_for_url(re.compile(r"/snippets/[a-f0-9]{8}$"), timeout=10_000)
    return page.url.split("/snippets/")[1]


class TestTaskHistory:
    def test_task_history_page_loads(self, page: Page, live_server):
        """Task history page renders with a commit list or 'No history' message."""
        task_id = _create_task(page, live_server, "E2E History Task")
        page.goto(f"{live_server}/tasks/{task_id}/history")
        page.wait_for_load_state("networkidle")
        assert page.locator(".history-commit").count() > 0 or "No history" in page.content()

    def test_task_history_link_in_edit_form(self, page: Page, live_server):
        """History button is visible in the task edit form."""
        task_id = _create_task(page, live_server, "E2E Task History Link")
        page.goto(f"{live_server}/tasks/{task_id}/edit")
        page.wait_for_load_state("networkidle")
        expect(page.locator(f'a[href="/tasks/{task_id}/history"]')).to_be_visible()

    def test_task_history_404_for_unknown(self, page: Page, live_server):
        """History page for nonexistent task returns 404."""
        resp = page.request.get(f"{live_server}/tasks/deadbeef/history")
        assert resp.status == 404


class TestNoteHistory:
    def test_note_history_page_loads(self, page: Page, live_server):
        """Note history page renders after creating a note."""
        detail_url = _create_note(page, live_server, "E2E History Note", "body text")
        note_id = detail_url.split("/notes/")[1]
        page.goto(f"{live_server}/notes/{note_id}/history")
        page.wait_for_load_state("networkidle")
        assert page.locator(".history-commit").count() > 0 or "No history" in page.content()

    def test_note_history_button_on_detail(self, page: Page, live_server):
        """History button is visible on note detail page."""
        detail_url = _create_note(page, live_server, "E2E Note History Btn", "body")
        page.goto(detail_url)
        expect(page.locator('a[href*="/history"]').first).to_be_visible()


class TestRunbookHistory:
    def test_runbook_history_page_loads(self, page: Page, live_server):
        """Runbook history page renders after creating a runbook."""
        rb_id = _create_runbook(page, live_server, "E2E History Runbook")
        page.goto(f"{live_server}/runbooks/{rb_id}/history")
        page.wait_for_load_state("networkidle")
        assert page.locator(".history-commit").count() > 0 or "No history" in page.content()

    def test_runbook_history_button_on_detail(self, page: Page, live_server):
        """History button is visible on runbook detail page."""
        rb_id = _create_runbook(page, live_server, "E2E Runbook Hist Btn")
        page.goto(f"{live_server}/runbooks/{rb_id}")
        page.wait_for_load_state("networkidle")
        expect(page.locator(f'a[href="/runbooks/{rb_id}/history"]')).to_be_visible()


class TestSnippetHistory:
    def test_snippet_history_page_loads(self, page: Page, live_server):
        """Snippet history page renders after creating a snippet."""
        sn_id = _create_snippet(page, live_server, "E2E History Snippet")
        page.goto(f"{live_server}/snippets/{sn_id}/history")
        page.wait_for_load_state("networkidle")
        assert page.locator(".history-commit").count() > 0 or "No history" in page.content()

    def test_snippet_history_button_on_detail(self, page: Page, live_server):
        """History button is visible on snippet detail page."""
        sn_id = _create_snippet(page, live_server, "E2E Snippet Hist Btn")
        page.goto(f"{live_server}/snippets/{sn_id}")
        page.wait_for_load_state("networkidle")
        expect(page.locator(f'a[href="/snippets/{sn_id}/history"]')).to_be_visible()
