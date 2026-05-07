"""E2E tests for the Snippets module — create, search, copy button."""

from playwright.sync_api import Page, expect


def _create_snippet(
    page: Page,
    base: str,
    title: str,
    description: str = "",
    steps: list[tuple[str, str]] | None = None,
) -> str:
    """Create a snippet and return the detail page URL.

    Step 0 is pre-rendered on the new-snippet form; subsequent steps require
    clicking '+ Add Command' first.
    """
    page.goto(f"{base}/snippets/new")
    page.fill('[name="title"]', title)
    if description:
        page.fill('[name="description"]', description)
    if not steps:
        steps = [("", f"echo {title}")]
    for i, (desc, cmd) in enumerate(steps):
        if i > 0:
            page.locator('button:has-text("+ Add Command")').last.click()
        if desc:
            page.locator(f'[name="step_desc_{i}"]').fill(desc)
        page.locator(f'[name="step_cmd_{i}"]').fill(cmd)
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    return page.url


class TestSnippetCreate:
    def test_snippet_appears_in_list(self, page: Page, live_server):
        """A newly created snippet appears in the snippets list."""
        _create_snippet(page, live_server, "E2E Snippet Alpha")
        page.goto(f"{live_server}/snippets")
        expect(page.get_by_text("E2E Snippet Alpha").first).to_be_visible()

    def test_snippet_shows_step_count(self, page: Page, live_server):
        """A snippet with steps shows the step count in the list."""
        _create_snippet(
            page,
            live_server,
            "E2E Snippet Beta",
            steps=[
                ("List containers", "docker ps -a"),
                ("Remove stopped", "docker container prune -f"),
            ],
        )
        page.goto(f"{live_server}/snippets")
        expect(
            page.locator(".card", has_text="E2E Snippet Beta").get_by_text("2 steps").first
        ).to_be_visible()

    def test_snippet_command_visible_in_list(self, page: Page, live_server):
        """Commands are shown as code previews in the list."""
        _create_snippet(
            page,
            live_server,
            "E2E Snippet Gamma",
            steps=[
                ("", "git log --oneline"),
            ],
        )
        page.goto(f"{live_server}/snippets")
        expect(page.get_by_text("git log --oneline").first).to_be_visible()


class TestSnippetDetail:
    def test_detail_shows_command(self, page: Page, live_server):
        """Detail page renders the command in a code block."""
        url = _create_snippet(
            page,
            live_server,
            "E2E Detail Snippet",
            steps=[
                ("Check disk", "df -h"),
            ],
        )
        page.goto(url)
        expect(page.get_by_text("df -h").first).to_be_visible()

    def test_detail_shows_step_description(self, page: Page, live_server):
        """Step description is rendered above the command."""
        url = _create_snippet(
            page,
            live_server,
            "E2E Desc Snippet",
            steps=[
                ("Show disk usage", "df -h"),
            ],
        )
        page.goto(url)
        expect(page.get_by_text("Show disk usage").first).to_be_visible()

    def test_copy_button_present(self, page: Page, live_server):
        """Each command has a copy button."""
        _create_snippet(
            page,
            live_server,
            "E2E Copy Snippet",
            steps=[
                ("", "echo hello"),
            ],
        )
        # Already on the detail page after creation redirect
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator('button[title="Copy command"]').first).to_be_visible()


class TestSnippetNewForm:
    def test_first_command_field_pre_rendered(self, page: Page, live_server):
        """New snippet form shows step #0 command textarea without clicking Add."""
        page.goto(f"{live_server}/snippets/new")
        expect(page.locator('[name="step_cmd_0"]')).to_be_visible()

    def test_add_command_button_below_last_step(self, page: Page, live_server):
        """+ Add Command button is present below the last step row."""
        page.goto(f"{live_server}/snippets/new")
        # There should be at least one Add Command button visible
        expect(page.locator('button:has-text("+ Add Command")').last).to_be_visible()


class TestSnippetSearch:
    def test_search_by_title(self, page: Page, live_server):
        """Search by title returns matching snippet."""
        _create_snippet(page, live_server, "E2E Kubectl Snippet")
        page.goto(f"{live_server}/snippets?q=Kubectl")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Kubectl Snippet").first).to_be_visible()

    def test_search_by_command(self, page: Page, live_server):
        """Search by command text returns matching snippet."""
        _create_snippet(
            page,
            live_server,
            "E2E Grep Snippet",
            steps=[
                ("", "grep -r 'TODO' ."),
            ],
        )
        page.goto(f"{live_server}/snippets?q=TODO")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Grep Snippet").first).to_be_visible()


class TestSnippetListActions:
    def test_edit_button_present_in_list(self, page: Page, live_server):
        """List cards show an edit button that links to the edit form."""
        _create_snippet(page, live_server, "E2E Edit Button Snippet")
        page.goto(f"{live_server}/snippets")
        card = page.locator(".mod-card").filter(has_text="E2E Edit Button Snippet").first
        edit_link = card.locator('a[href*="/edit"]').first
        expect(edit_link).to_be_visible()

    def test_edit_button_navigates_to_form(self, page: Page, live_server):
        """Clicking the edit button opens the edit form for the correct snippet."""
        _create_snippet(page, live_server, "E2E Edit Nav Snippet")
        page.goto(f"{live_server}/snippets")
        card = page.locator(".mod-card").filter(has_text="E2E Edit Nav Snippet").first
        card.locator('a[href*="/edit"]').first.click()
        page.wait_for_load_state("networkidle")
        expect(page.locator('[name="title"]')).to_have_value("E2E Edit Nav Snippet")

    def test_delete_button_present_in_list(self, page: Page, live_server):
        """List cards show a delete button."""
        _create_snippet(page, live_server, "E2E Delete Button Snippet")
        page.goto(f"{live_server}/snippets")
        card = page.locator(".mod-card").filter(has_text="E2E Delete Button Snippet").first
        expect(card.locator('button[type="submit"].btn-danger').first).to_be_visible()
