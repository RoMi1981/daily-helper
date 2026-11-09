"""Guard for copy buttons that show a short ✓ and then restore themselves.

Copy buttons are icon-only (`<i data-lucide>` rendered to an `<svg>`), so their
`textContent` is empty. Saving and restoring `textContent` therefore wipes the
icon and the button shrinks to its padding after the first click. This happened
in ticket templates and runbooks while five sibling handlers already saved
`innerHTML`. The E2E tests cover the two fixed buttons; this scan keeps the
pattern out of every template in the fast test job.
"""

import os
import re

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if not os.path.isdir(APP_DIR):
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# `var orig = btn.textContent` and friends — saving text to put it back later.
_SAVED_TEXT = re.compile(r"(?:var|const|let)\s+\w+\s*=\s*[A-Za-z_$][\w$.]*\.textContent\b")


def _templates():
    root = os.path.join(APP_DIR, "templates")
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name.endswith(".html"):
                yield os.path.join(dirpath, name)


def test_no_template_restores_a_button_from_text_content():
    offenders = []
    for path in _templates():
        for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
            if _SAVED_TEXT.search(line):
                offenders.append(f"{os.path.relpath(path, APP_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Save innerHTML, not textContent, before showing copy feedback — "
        "icon-only buttons have empty textContent:\n" + "\n".join(offenders)
    )


def test_scan_finds_the_old_pattern():
    """The regex must match the exact lines that caused the bug."""
    assert _SAVED_TEXT.search("    const orig = btn.textContent;")
    assert _SAVED_TEXT.search("      var orig = btn.textContent;")
    assert not _SAVED_TEXT.search("    const orig = btn.innerHTML;")
