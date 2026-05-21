"""E2E tests for the Runbooks module — create, checklist interaction, progress bar, reset."""

from playwright.sync_api import Page, expect


def _create_runbook(page: Page, base: str, title: str, steps: list[tuple[str, str]] | None = None) -> str:
    """Create a runbook and return the URL of the detail page."""
    page.goto(f"{base}/runbooks/new")
    page.fill('[name="title"]', title)
    if steps:
        for i, (step_title, step_body) in enumerate(steps):
            page.locator('button:has-text("+ Add Step")').click()
            page.locator(f'[name="step_title_{i}"]').fill(step_title)
            if step_body:
                page.locator(f'[name="step_body_{i}"]').fill(step_body)
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    return page.url


class TestRunbookCreate:
    def test_runbook_appears_in_list(self, page: Page, live_server):
        """A newly created runbook appears in the runbooks list."""
        _create_runbook(page, live_server, "E2E Runbook Alpha")
        page.goto(f"{live_server}/runbooks")
        expect(page.get_by_text("E2E Runbook Alpha").first).to_be_visible()

    def test_runbook_with_steps_shows_step_count(self, page: Page, live_server):
        """A runbook with steps shows the step count in the list."""
        _create_runbook(page, live_server, "E2E Runbook Beta", [
            ("Step One", "echo hello"),
            ("Step Two", "echo world"),
        ])
        page.goto(f"{live_server}/runbooks")
        # Step count badge: "2 steps"
        expect(page.locator(".card", has_text="E2E Runbook Beta").get_by_text("2 steps").first).to_be_visible()


class TestRunbookChecklist:
    def test_checkbox_updates_progress_bar(self, page: Page, live_server):
        """Checking a step updates the progress bar and label."""
        url = _create_runbook(page, live_server, "E2E Checklist Runbook", [
            ("Deploy", "kubectl apply -f deploy.yml"),
            ("Verify", "kubectl get pods"),
        ])
        page.goto(url)

        # Initial state: 0 / 2
        expect(page.locator("#progress-label")).to_have_text("0 / 2")

        # Check first step
        page.locator(".step-check").first.click()

        # Progress should update: 1 / 2
        expect(page.locator("#progress-label")).to_have_text("1 / 2")

        # Progress bar should be 50% wide
        bar_width = page.evaluate(
            "document.getElementById('progress-bar').style.width"
        )
        assert bar_width == "50%", f"Expected 50%, got {bar_width!r}"

    def test_checked_step_gets_strikethrough(self, page: Page, live_server):
        """A checked step title gets a strikethrough style."""
        url = _create_runbook(page, live_server, "E2E Strike Runbook", [
            ("Strike This", "rm -f /tmp/test"),
        ])
        page.goto(url)

        page.locator(".step-check").first.click()
        step_title = page.locator(".step-title").first
        text_decoration = page.evaluate(
            "getComputedStyle(document.querySelector('.step-title')).textDecoration"
        )
        assert "line-through" in text_decoration, f"Expected line-through, got {text_decoration!r}"

    def test_reset_unchecks_all_steps(self, page: Page, live_server):
        """Reset button clears all checkboxes and resets progress to 0."""
        url = _create_runbook(page, live_server, "E2E Reset Runbook", [
            ("Step A", ""),
            ("Step B", ""),
            ("Step C", ""),
        ])
        page.goto(url)

        # Check all steps
        for cb in page.locator(".step-check").all():
            cb.click()
        expect(page.locator("#progress-label")).to_have_text("3 / 3")

        # Reset
        page.locator('button:has-text("↺ Reset")').click()
        expect(page.locator("#progress-label")).to_have_text("0 / 3")

        # All checkboxes unchecked
        for cb in page.locator(".step-check").all():
            expect(cb).not_to_be_checked()

    def test_step_body_is_visible(self, page: Page, live_server):
        """The step body (command) is rendered on the detail page."""
        url = _create_runbook(page, live_server, "E2E Body Runbook", [
            ("Run tests", "pytest tests/ -v"),
        ])
        page.goto(url)
        expect(page.get_by_text("pytest tests/ -v")).to_be_visible()
