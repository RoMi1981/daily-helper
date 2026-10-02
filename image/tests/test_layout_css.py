"""Guards for layout rules whose behaviour is only observable in a browser.

The E2E suite proves these rules work, but it is skipped whenever the deploy key
for the test repo is missing. These checks keep the rules from being dropped
silently in the fast test job.
"""

import os
import re

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if not os.path.isdir(APP_DIR):
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STYLE_CSS = os.path.join(APP_DIR, "static", "style.css")


def _rule(selector: str) -> str:
    """Return the declarations of a single-line rule, e.g. '.content { … }'."""
    css = open(STYLE_CSS, encoding="utf-8").read()
    match = re.search(rf"^{re.escape(selector)}\s*\{{([^}}]*)\}}", css, re.MULTILINE)
    assert match, f"Rule for {selector} not found in style.css"
    return match.group(1)


def test_content_column_can_shrink():
    """.content needs min-width:0 to shrink inside the `220px 1fr` layout grid.

    A grid item defaults to min-width:auto, so without this the column grows to
    the min-content width of its contents — one `white-space: nowrap` snippet
    command pushed the whole page past the viewport, and `html { overflow-x: clip }`
    then cut it off at the right edge instead of scrolling.
    """
    assert "min-width: 0" in _rule(".content")


def test_search_snippets_break_long_tokens():
    """Search excerpts are up to 200 monospace chars and may be a single URL.

    Without a break rule such a snippet is wider than its card at common desktop
    widths and spills over the card's right edge.
    """
    assert "overflow-wrap: anywhere" in _rule(".result-snippet")
