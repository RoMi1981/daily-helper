"""E2E tests for Task Dependencies (blocked_by relation)."""

from playwright.sync_api import Page, expect


def _create_task(page: Page, base: str, title: str) -> None:
    page.goto(f"{base}/tasks#new-form")
    page.fill('[name="title"]', title)
    page.locator('form[action="/tasks"] [type="submit"]').click()
    page.wait_for_load_state("networkidle")


class TestTaskBlockedBy:
    def test_blocked_indicator_appears_after_setting_dependency(self, page: Page, live_server):
        """Marking a task as blocked by another shows the locked indicator in the list."""
        _create_task(page, live_server, "E2E Dep Blocker Alpha")
        _create_task(page, live_server, "E2E Dep Blocked Alpha")

        page.goto(f"{live_server}/tasks")
        page.wait_for_load_state("networkidle")

        # Open edit form for the blocked task
        blocked_card = page.locator(".task-card", has_text="E2E Dep Blocked Alpha").first
        blocked_card.wait_for(state="visible")
        blocked_card.locator('a[href*="/edit"]').click()
        page.wait_for_load_state("networkidle")

        # Check the checkbox for the blocker task
        blocker_label = page.locator('label', has_text="E2E Dep Blocker Alpha").first
        blocker_label.wait_for(state="visible")
        blocker_label.locator('input[type="checkbox"][name="blocked_by"]').check()

        page.locator('[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        # Verify the blocked indicator is visible on the task list
        page.goto(f"{live_server}/tasks")
        page.wait_for_load_state("networkidle")
        blocked_card = page.locator(".task-card", has_text="E2E Dep Blocked Alpha").first
        blocked_card.wait_for(state="visible")
        expect(blocked_card.locator(".task-blocked").first).to_be_visible()

    def test_non_blocked_task_has_no_indicator(self, page: Page, live_server):
        """A task without any blocked_by dependency shows no locked indicator."""
        _create_task(page, live_server, "E2E Dep Free Task")
        page.goto(f"{live_server}/tasks")
        page.wait_for_load_state("networkidle")
        free_card = page.locator(".task-card", has_text="E2E Dep Free Task").first
        free_card.wait_for(state="visible")
        expect(free_card.locator(".task-blocked")).to_have_count(0)

    def test_blocked_by_shown_in_edit_form(self, page: Page, live_server):
        """Edit form shows a 'Blocked by' checkbox list when open tasks exist."""
        _create_task(page, live_server, "E2E Dep Edit Check Task")
        page.goto(f"{live_server}/tasks")
        page.wait_for_load_state("networkidle")

        card = page.locator(".task-card", has_text="E2E Dep Edit Check Task").first
        card.wait_for(state="visible")
        card.locator('a[href*="/edit"]').click()
        page.wait_for_load_state("networkidle")

        # The blocked-by section should appear since other open tasks exist
        expect(page.locator('input[name="blocked_by"]').first).to_be_visible()
