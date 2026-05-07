"""E2E tests for the Tasks module — create, toggle (HTMX), search."""

import pytest
from playwright.sync_api import Page, expect


def _create_task(page: Page, base: str, title: str, due_date: str = "") -> None:
    """Fill the new-task form and submit.
    Navigate to /tasks#new-form so CSS :target makes the form visible.
    """
    page.goto(f"{base}/tasks#new-form")
    page.fill('[name="title"]', title)
    if due_date:
        page.fill('[name="due_date"]', due_date)
    # Submit the quick-create form (the first submit button on the page)
    page.locator('form [type="submit"]').first.click()
    page.wait_for_load_state("networkidle")


class TestTaskCreate:
    def test_task_appears_in_list(self, page: Page, live_server):
        _create_task(page, live_server, "E2E Task Bravo")
        page.goto(f"{live_server}/tasks")
        expect(page.get_by_text("E2E Task Bravo").first).to_be_visible()

    def test_task_with_due_date_shows_date(self, page: Page, live_server):
        _create_task(page, live_server, "E2E Dated Task", "2030-06-15")
        page.goto(f"{live_server}/tasks")
        expect(page.get_by_text("E2E Dated Task").first).to_be_visible()
        expect(page.get_by_text("2030-06-15").first).to_be_visible()


class TestTaskToggle:
    def test_checkbox_marks_task_done(self, page: Page, live_server):
        """Checking the HTMX checkbox moves the task to the done section."""
        _create_task(page, live_server, "E2E Toggle Task")
        page.goto(f"{live_server}/tasks")

        row = page.locator(".task-card", has_text="E2E Toggle Task").first
        checkbox = row.locator('input[type="checkbox"]')
        expect(checkbox).not_to_be_checked()

        checkbox.click()
        page.wait_for_load_state("networkidle")

        # Reload to get full page with done section rendered server-side
        page.goto(f"{live_server}/tasks")
        page.wait_for_load_state("networkidle")

        details = page.locator("details.task-done-section")
        details.locator("summary").click()
        page.wait_for_timeout(200)
        expect(details.get_by_text("E2E Toggle Task").first).to_be_visible()


class TestTaskSearch:
    def test_search_filters_list(self, page: Page, live_server):
        """Search query shows only matching tasks."""
        _create_task(page, live_server, "E2E Quokka Task")
        page.goto(f"{live_server}/tasks?q=Quokka")
        page.wait_for_load_state("networkidle")

        expect(page.get_by_text("E2E Quokka Task").first).to_be_visible()

    def test_empty_search_shows_all(self, page: Page, live_server):
        """Empty search shows all tasks (open or done section present)."""
        page.goto(f"{live_server}/tasks?q=")
        page.wait_for_load_state("networkidle")
        # At least the tasks we created exist
        expect(page.locator(".task-card").first).to_be_visible()
