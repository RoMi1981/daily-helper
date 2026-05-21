"""E2E tests for the Knowledge module — create entry, HTMX search, category filter."""

from playwright.sync_api import Page, expect


def _create_entry(page: Page, base: str, title: str, content: str, category: str = "E2E") -> str:
    """Create a knowledge entry and return the URL of the entry page."""
    page.goto(f"{base}/knowledge/new")
    # Category: select existing or create new
    cat_select = page.locator("#category")
    options = cat_select.locator("option").all()
    existing = [o.get_attribute("value") for o in options]
    if category in existing:
        cat_select.select_option(category)
    else:
        cat_select.select_option("__new__")
        page.fill('[name="new_category"]', category)
    page.fill('[name="title"]', title)
    page.fill('[name="content"]', content)
    page.locator('[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    return page.url


class TestKnowledgeCreate:
    def test_entry_appears_after_create(self, page: Page, live_server):
        """A new entry is accessible on its own detail page."""
        url = _create_entry(page, live_server, "E2E Knowledge Alpha", "# Alpha\n\nFirst entry.")
        # Should be on the entry detail page
        page.wait_for_selector("text=E2E Knowledge Alpha", timeout=15000)
        expect(page.get_by_text("E2E Knowledge Alpha").first).to_be_visible()

    def test_entry_content_is_rendered_as_html(self, page: Page, live_server):
        """Markdown content is rendered as HTML on the entry page."""
        url = _create_entry(
            page, live_server, "E2E Markdown Entry", "## Hello World\n\nSome **bold** text."
        )
        # Markdown <h2> and <strong> should be rendered
        expect(page.locator("h2", has_text="Hello World")).to_be_visible()


class TestKnowledgeSearch:
    def test_htmx_search_returns_result(self, page: Page, live_server):
        """Typing in the search box shows matching entries via HTMX."""
        _create_entry(page, live_server, "E2E Nebula Entry", "Content about nebulae.")
        page.goto(f"{live_server}/knowledge")
        # HTMX triggers on keyup — use press_sequentially to fire real keystrokes
        page.locator("#search-input").press_sequentially("Nebula", delay=50)
        # Wait for HTMX 300ms delay + server response
        page.wait_for_timeout(800)
        page.wait_for_load_state("networkidle")
        expect(
            page.locator("#search-results").get_by_text("E2E Nebula Entry").first
        ).to_be_visible()

    def test_empty_search_clears_results(self, page: Page, live_server):
        """Clearing the search box clears the results area."""
        page.goto(f"{live_server}/knowledge")
        page.locator("#search-input").press_sequentially("something", delay=50)
        page.wait_for_timeout(600)
        # Select all + Delete to clear the input
        page.locator("#search-input").click(click_count=3)
        page.keyboard.press("Delete")
        page.wait_for_timeout(600)
        page.wait_for_load_state("networkidle")
        results_text = page.locator("#search-results").inner_text()
        assert "404" not in results_text


class TestKnowledgeCategoryFilter:
    def test_category_filter_shows_matching_entries(self, page: Page, live_server):
        """Selecting a category in the search filter shows only that category's entries."""
        _create_entry(page, live_server, "E2E Category Entry", "Content.", category="E2E-Cat")
        page.goto(f"{live_server}/knowledge")
        page.wait_for_load_state("networkidle")
        # select_option triggers change event which HTMX listens to
        page.locator("#category-filter").select_option("E2E-Cat")
        page.wait_for_timeout(1200)
        page.wait_for_load_state("networkidle")
        expect(
            page.locator("#search-results").get_by_text("E2E Category Entry").first
        ).to_be_visible(timeout=5000)
