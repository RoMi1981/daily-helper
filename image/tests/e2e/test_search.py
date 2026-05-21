"""E2E tests for the global search — /search?q= across all modules."""

from playwright.sync_api import Page, expect


class TestGlobalSearchNavbar:
    def test_search_input_visible_in_navbar(self, page: Page, live_server):
        """The global search input is visible in the navbar on desktop."""
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{live_server}/")
        expect(page.locator(".nav-search-input")).to_be_visible()

    def test_search_navigates_to_results_page(self, page: Page, live_server):
        """Submitting the navbar search form navigates to /search."""
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{live_server}/")
        page.locator(".nav-search-input").fill("E2E")
        page.locator(".nav-search-input").press("Enter")
        page.wait_for_load_state("networkidle")
        assert "/search" in page.url
        assert "q=E2E" in page.url

    def test_slash_key_focuses_search(self, page: Page, live_server):
        """Pressing / focuses the global search input."""
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{live_server}/")
        page.keyboard.press("/")
        focused = page.evaluate("document.activeElement.id")
        assert focused == "global-search-nav"


class TestGlobalSearchResults:
    def test_empty_query_shows_form(self, page: Page, live_server):
        """/search without a query shows the search form."""
        page.goto(f"{live_server}/search")
        expect(page.locator('input[name="q"]').first).to_be_visible()

    def test_no_results_message(self, page: Page, live_server):
        """A query with no matches shows 'No results for' message."""
        page.goto(f"{live_server}/search?q=xyzzy_no_match_ever")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("No results for").first).to_be_visible()

    def test_finds_snippet(self, page: Page, live_server):
        """Global search finds a snippet by title."""
        # Create a snippet first
        page.goto(f"{live_server}/snippets/new")
        page.fill('[name="title"]', "E2E GlobalSearch Snippet")
        page.locator('[name="step_cmd_0"]').fill("echo globalsearch")
        page.locator('[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/search?q=GlobalSearch+Snippet")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("Snippets").first).to_be_visible()
        expect(page.get_by_text("E2E GlobalSearch Snippet").first).to_be_visible()

    def test_finds_note(self, page: Page, live_server):
        """Global search finds a note by subject."""
        # Create a note first
        page.goto(f"{live_server}/notes/new")
        page.fill('[name="subject"]', "E2E GlobalSearch Note")
        page.fill('[name="body"]', "searchable content")
        page.locator('[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        # Verify note detail loaded (confirms creation + git commit completed)
        page.wait_for_selector(".note-view-wrap", state="attached", timeout=10000)

        page.goto(f"{live_server}/search?q=GlobalSearch+Note")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("Notes").first).to_be_visible()
        expect(page.get_by_text("E2E GlobalSearch Note").first).to_be_visible()

    def test_result_count_shown(self, page: Page, live_server):
        """Result summary line shows count and module count."""
        page.goto(f"{live_server}/snippets/new")
        page.fill('[name="title"]', "E2E Count Snippet Unique99")
        page.locator('[name="step_cmd_0"]').fill("ls")
        page.locator('[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/search?q=Unique99")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("result").first).to_be_visible()

    def test_view_all_link_present(self, page: Page, live_server):
        """Each result group has a 'View all →' link."""
        page.goto(f"{live_server}/snippets/new")
        page.fill('[name="title"]', "E2E ViewAll Snippet")
        page.locator('[name="step_cmd_0"]').fill("pwd")
        page.locator('[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/search?q=ViewAll")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("View all →").first).to_be_visible()
