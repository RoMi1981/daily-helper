"""Responsive layout tests — checks horizontal overflow and key element visibility
on both mobile and desktop for all main pages.

A page fails if:
- document.scrollWidth > window.innerWidth  (horizontal overflow / cut-off content)
- A defined key element is not visible

Two test classes:
- TestResponsiveLayout: visits pages with no content (fast, catches structural issues)
- TestResponsiveLayoutWithContent: visits /notes and /history with seeded long-string
  data to catch overflow bugs that only appear with real content
"""

import pytest
from playwright.sync_api import Page, expect

MOBILE = {"width": 390, "height": 844}
DESKTOP = {"width": 1920, "height": 1080}

VIEWPORTS = [
    pytest.param(MOBILE, id="mobile"),
    pytest.param(DESKTOP, id="desktop"),
]

# (path, description, key_selector_that_must_be_visible)
PAGES = [
    ("/", "Home", "h1, h2, .home-stat-card"),
    ("/tasks", "Tasks", "h1"),
    ("/tasks#new-form", "Tasks new form", "#new-form"),
    ("/notes", "Notes", "h1"),
    ("/notes/new", "Notes form", 'textarea[name="body"]'),
    ("/links", "Links", "h1"),
    ("/links/new", "Links form", 'input[name="url"]'),
    ("/knowledge", "Knowledge", "h1"),
    ("/runbooks", "Runbooks", "h1"),
    ("/snippets", "Snippets", "h1"),
    ("/mail-templates", "Mail Templates", "h1"),
    ("/memes", "Memes", "h1"),
    ("/ticket-templates", "Ticket Templates", "h1"),
    ("/vacations", "Vacations", "h1"),
    ("/appointments", "Appointments", "h1"),
    ("/calendar", "Calendar", ".calendar-grid, h1"),
    ("/history", "History", "h1"),
    ("/search", "Search", "#global-search-input"),
    ("/operations", "Operations", "h1"),
    ("/settings", "Settings", "h1"),
]


def _check_no_horizontal_overflow(page: Page, path: str, vp: dict) -> None:
    """Assert document has no horizontal scrollbar."""
    overflow = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 2")
    assert not overflow, (
        f"Horizontal overflow on {path} at {vp['width']}×{vp['height']} "
        f"(scrollWidth={page.evaluate('document.documentElement.scrollWidth')}, "
        f"innerWidth={vp['width']})"
    )


@pytest.mark.parametrize("viewport", VIEWPORTS)
class TestResponsiveLayout:
    @pytest.fixture(autouse=True)
    def set_viewport(self, page: Page, viewport: dict):
        page.set_viewport_size(viewport)

    @pytest.mark.parametrize("path,label,selector", PAGES)
    def test_no_horizontal_overflow(self, page: Page, live_server, viewport, path, label, selector):
        """No horizontal overflow on any page at this viewport."""
        page.goto(f"{live_server}{path}")
        page.wait_for_load_state("networkidle")
        _check_no_horizontal_overflow(page, path, viewport)

    @pytest.mark.parametrize("path,label,selector", PAGES)
    def test_key_element_visible(self, page: Page, live_server, viewport, path, label, selector):
        """Key element is visible at this viewport."""
        page.goto(f"{live_server}{path}")
        page.wait_for_load_state("networkidle")
        # Use first matching selector from comma-separated list
        for sel in selector.split(","):
            sel = sel.strip()
            el = page.locator(sel).first
            if el.count() > 0:
                expect(el).to_be_visible(timeout=10_000)
                return
        pytest.fail(f"No element matched '{selector}' on {path}")


# Pages that need real content to trigger potential overflow.
# seeded_overflow_content creates notes with long subjects and spaceless bodies,
# which also appear in /history as git commit subjects and audit-change entries.
SEEDED_PAGES = [
    ("/notes", "Notes with long content", "h1"),
    ("/tasks", "Tasks with long title", "h1"),
    ("/runbooks", "Runbooks with long title", "h1"),
    ("/history", "History with commits", "h1"),
]


@pytest.mark.parametrize("viewport", VIEWPORTS)
class TestResponsiveLayoutWithContent:
    """Overflow checks for pages whose layout only breaks with real long-string content."""

    @pytest.fixture(autouse=True)
    def set_viewport(self, page: Page, viewport: dict):
        page.set_viewport_size(viewport)

    @pytest.fixture(autouse=True)
    def _seed(self, seeded_overflow_content):
        """Ensure seed data exists before any test in this class runs."""

    @pytest.mark.parametrize("path,label,selector", SEEDED_PAGES)
    def test_no_horizontal_overflow_with_content(
        self, page: Page, live_server, viewport, path, label, selector
    ):
        """No horizontal overflow when the page contains real long-string data."""
        page.goto(f"{live_server}{path}")
        page.wait_for_load_state("networkidle")
        _check_no_horizontal_overflow(page, path, viewport)

    @pytest.mark.parametrize("path,label,selector", SEEDED_PAGES)
    def test_key_element_visible_with_content(
        self, page: Page, live_server, viewport, path, label, selector
    ):
        """Key element remains visible when page contains real long-string data."""
        page.goto(f"{live_server}{path}")
        page.wait_for_load_state("networkidle")
        for sel in selector.split(","):
            sel = sel.strip()
            el = page.locator(sel).first
            if el.count() > 0:
                expect(el).to_be_visible(timeout=10_000)
                return
        pytest.fail(f"No element matched '{selector}' on {path}")
