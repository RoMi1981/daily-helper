"""E2E test for Settings → Module Repositories: every module (including EOL
Tracker, which was previously unreachable here) must have a repo-assignment
checkbox row and be persistable via POST /settings/module-repos."""

from playwright.sync_api import Page, expect


class TestEolModuleRepoAssignment:
    def test_eol_checkbox_row_visible(self, page: Page, live_server):
        page.goto(f"{live_server}/settings#module-repos")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.getElementById('module-repos').scrollIntoView()")

        form = page.locator('form[action="/settings/module-repos"]')
        expect(form).to_be_visible()
        expect(form.get_by_text("EOL Tracker")).to_be_visible()
        expect(form.locator('input[name="eol_repos"]').first).to_be_attached()
        expect(form.locator('select[name="eol_primary"]')).to_be_attached()

    def test_eol_repo_assignment_persists(self, page: Page, live_server):
        page.goto(f"{live_server}/settings#module-repos")
        page.wait_for_load_state("networkidle")

        eol_checkboxes = page.locator('input[name="eol_repos"]')
        first_value = eol_checkboxes.first.get_attribute("value")

        # Uncheck all but the first assigned repo, then save.
        count = eol_checkboxes.count()
        for i in range(count):
            cb = eol_checkboxes.nth(i)
            if cb.get_attribute("value") != first_value and cb.is_checked():
                cb.uncheck()

        page.locator('form[action="/settings/module-repos"] button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/settings#module-repos")
        page.wait_for_load_state("networkidle")
        reloaded = page.locator(f'input[name="eol_repos"][value="{first_value}"]')
        expect(reloaded).to_be_checked()
