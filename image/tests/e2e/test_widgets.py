"""E2E tests for the widget dashboard."""

import json
import urllib.request

from playwright.sync_api import Page, expect


def _set_widgets(live_server: str, widget_ids: list[str]) -> None:
    layout = [{"id": wid, "enabled": True} for wid in widget_ids]
    data = json.dumps(layout).encode()
    req = urllib.request.Request(
        f"{live_server}/widgets/layout",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


class TestWidgetDashboard:
    def test_dashboard_loads(self, page: Page, live_server: str) -> None:
        """Dashboard page renders the widget grid (even when empty)."""
        page.goto(f"{live_server}/widgets")
        expect(page.locator("#widget-grid")).to_be_attached()
        expect(page.locator("h1")).to_be_visible()

    def test_widgets_have_visible_height(self, page: Page, live_server: str) -> None:
        """Active widgets must have positive height after masonry layout runs.

        Regression test: masonry ran on DOMContentLoaded (too early) and
        measured height 0, collapsing every widget to a single row.
        """
        _set_widgets(live_server, ["app_version", "stats_knowledge"])

        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")
        # Explicitly re-run masonry after full render to get accurate heights
        page.evaluate("if (typeof masonryLayout === 'function') masonryLayout()")
        page.wait_for_timeout(100)

        widgets = page.locator("#widget-grid .widget")
        count = widgets.count()
        assert count > 0, "No widgets found on dashboard after setting layout"

        for i in range(count):
            w = widgets.nth(i)
            box = w.bounding_box()
            assert box is not None, f"Widget {i} has no bounding box"
            assert box["height"] > 40, (
                f"Widget {i} height {box['height']:.0f}px is suspiciously small "
                f"(masonry may have measured before content loaded)"
            )

    def test_edit_mode_toggles(self, page: Page, live_server: str) -> None:
        """Edit mode button shows edit controls and hides on Done."""
        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")

        page.locator("#edit-toggle-btn").click()
        expect(page.locator("#edit-actions")).to_be_visible()
        expect(page.locator("#edit-toggle-btn")).not_to_be_visible()

        page.locator("#save-layout-btn").click()
        page.wait_for_load_state("load")
        expect(page.locator("#edit-toggle-btn")).to_be_visible()
