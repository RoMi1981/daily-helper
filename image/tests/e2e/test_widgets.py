"""E2E tests for the widget dashboard."""

import json
import urllib.request

import pytest
from playwright.sync_api import Page, expect

MOBILE = {"width": 390, "height": 844}
DESKTOP = {"width": 1920, "height": 1080}


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
        """Dashboard page renders the widget grid (even when empty).

        Also verifies _packWidgets() runs to completion on a widget-less grid
        without throwing (which would leave the grid permanently hidden,
        since it's hidden until the first pack finishes to avoid a layout
        flash).
        """
        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")
        expect(page.locator("#widget-grid")).to_be_attached()
        expect(page.locator("h1")).to_be_visible()
        page.wait_for_function("document.getElementById('widget-grid').style.visibility !== 'hidden'")

    def test_widgets_have_visible_height(self, page: Page, live_server: str) -> None:
        """Active widgets must have positive height after masonry layout runs.

        Regression test: masonry ran on DOMContentLoaded (too early) and
        measured height 0, collapsing every widget to a single row.
        """
        _set_widgets(live_server, ["app_version", "stats_knowledge"])

        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")
        # Explicitly re-run masonry after full render to get accurate heights
        page.evaluate("if (typeof _packWidgets === 'function') _packWidgets()")
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

    def test_fit_all_resizes_every_widget_and_persists(self, page: Page, live_server: str) -> None:
        """'Fit All' shrinks every widget back to its content width and saves the layout.

        The first widget is force-widened (simulating a manual resize) before
        clicking "Fit All" so the test has a deterministic, content-independent
        signal that fitting actually ran on it too, not just relying on the
        server-rendered default already matching the fitted width.
        """
        _set_widgets(live_server, ["app_version", "stats_knowledge"])

        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")

        page.locator("#edit-toggle-btn").click()
        widgets = page.locator("#widget-grid .widget")
        first = widgets.nth(0)
        first.evaluate("el => { el.style.gridColumn = 'span 24'; el.dataset.cols = '24'; }")
        assert int(first.get_attribute("data-cols")) == 24

        page.locator("#fit-all-btn").click()
        page.wait_for_timeout(200)

        after_cols = [int(widgets.nth(i).get_attribute("data-cols")) for i in range(widgets.count())]
        assert after_cols[0] < 24, "Fit All did not shrink the force-widened widget back down"
        assert all(2 <= c <= 24 for c in after_cols)

        page.reload()
        page.wait_for_load_state("load")
        reloaded = page.locator("#widget-grid .widget")
        persisted_cols = [int(reloaded.nth(i).get_attribute("data-cols")) for i in range(reloaded.count())]
        assert persisted_cols == after_cols, "Fit All layout was not persisted after reload"

    @pytest.mark.parametrize("viewport", [pytest.param(MOBILE, id="mobile"), pytest.param(DESKTOP, id="desktop")])
    def test_fit_all_button_usable_on_mobile_and_desktop(self, page: Page, live_server: str, viewport: dict) -> None:
        """'Fit All' button is visible, clickable and causes no horizontal overflow."""
        page.set_viewport_size(viewport)
        _set_widgets(live_server, ["app_version", "stats_knowledge"])

        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")

        page.locator("#edit-toggle-btn").click()
        expect(page.locator("#fit-all-btn")).to_be_visible()

        page.locator("#fit-all-btn").click()
        page.wait_for_timeout(200)

        overflow = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 2")
        assert not overflow, f"Horizontal overflow after Fit All at {viewport['width']}x{viewport['height']}"

    def test_masonry_fills_gap_under_shorter_widget(self, page: Page, live_server: str) -> None:
        """True masonry: a widget stacks under whichever same-column neighbor
        leaves the least unused vertical space, instead of being pushed below
        a much taller widget sharing the row.

        Regression test for the old edit-mode algorithm, which packed widgets
        into equal-height "shelves" by column width alone and ignored actual
        content height, so short widgets left permanent gaps.
        """
        _set_widgets(live_server, ["app_version", "stats_knowledge", "stats_tasks"])
        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")

        widgets = page.locator("#widget-grid .widget")
        # Two half-width widgets side by side: one short, one tall. A third
        # half-width widget should then stack under the short one, not the tall one.
        widgets.nth(0).evaluate(
            "el => { el.dataset.cols = '12'; el.style.gridColumn = 'span 12'; el.style.height = '60px'; }"
        )
        widgets.nth(1).evaluate(
            "el => { el.dataset.cols = '12'; el.style.gridColumn = 'span 12'; el.style.height = '300px'; }"
        )
        widgets.nth(2).evaluate(
            "el => { el.dataset.cols = '12'; el.style.gridColumn = 'span 12'; el.style.height = '60px'; }"
        )

        page.evaluate("_packWidgets()")

        rows = [int(widgets.nth(i).evaluate("el => getComputedStyle(el).gridRowStart")) for i in range(3)]
        assert rows[0] == rows[1], "The two half-width widgets should start in the same row"
        assert rows[2] > rows[0], "The third widget must stack below the short widget it shares columns with"
        assert rows[2] < 10, (
            f"Third widget landed at row {rows[2]}, suggesting it was pushed below the "
            "300px-tall widget instead of filling the gap under the 60px-tall one"
        )

    def test_packing_respects_mobile_breakpoint(self, page: Page, live_server: str) -> None:
        """On a narrow viewport, _packWidgets() must widen widget-third/-half
        widgets to full width, matching the CSS media-query rules in
        style.css — not keep the desktop column span baked in as an inline
        style, which would otherwise always win over the class-based rule.
        """
        page.set_viewport_size(MOBILE)
        _set_widgets(live_server, ["app_version", "stats_knowledge"])

        page.goto(f"{live_server}/widgets")
        page.wait_for_load_state("load")
        page.evaluate("_packWidgets()")

        widgets = page.locator("#widget-grid .widget")
        grid_box = page.locator("#widget-grid").bounding_box()
        for i in range(widgets.count()):
            w = widgets.nth(i)
            box = w.bounding_box()
            assert box["width"] >= grid_box["width"] - 20, (
                f"Widget {i} did not widen to full width on mobile viewport "
                f"(width={box['width']:.0f}, grid width={grid_box['width']:.0f})"
            )
