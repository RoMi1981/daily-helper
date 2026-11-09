"""Quick-Capture in base.html: real POST targets, Esc from a field, no silent failure.

The modal posted notes, links and snippets to /notes, /links and /snippets,
while the create routes are /notes/new, /links/new and /snippets/new. The 405
went into an empty .catch, the modal stayed open and the entry was lost without
a word. Only tasks (POST /tasks) worked.

Two more faults hid behind the same broken E2E assertion: Esc did nothing,
because the modal focuses its first field and the keydown handler returns early
while an input has focus; and a failed save left the modal open without a word.

The E2E suite covers each type end to end, but it is skipped without a deploy
key; these checks run in every unit test job.
"""

import os
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
APP_DIR = next(p for p in (_here.parent / "app", _here.parent) if (p / "main.py").is_file())
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)
os.environ.setdefault("REDIS_URL", "redis://localhost:9999")
os.environ.setdefault("DATA_DIR", "/tmp/daily-helper-test")

_ACTION = re.compile(r"action:'([^']+)',\s*method:'POST'")


def _base() -> str:
    return (APP_DIR / "templates" / "base.html").read_text(encoding="utf-8")


def _qc_actions() -> list[str]:
    return _ACTION.findall(_base())


def _shortcut_handler() -> str:
    src = _base()
    start = src.index("// Keyboard shortcuts")
    return src[start : src.index("});", start)]


def _submit_handler() -> str:
    src = _base()
    start = src.index("getElementById('qc-form').addEventListener('submit'")
    return src[start : src.index("window.qcOpen", start)]


def _post_paths() -> set[str]:
    import main

    return {r.path for r in main.app.routes if "POST" in getattr(r, "methods", set())}


def test_actions_are_found():
    # Guard the regex: if the QC_TYPES format changes, the check below must not pass empty.
    assert len(_qc_actions()) >= 4


def test_every_action_is_a_post_route():
    missing = [a for a in _qc_actions() if a not in _post_paths()]
    assert not missing, f"Quick-Capture posts to routes that do not exist: {missing}"


def test_esc_closes_modal_before_the_input_guard():
    handler = _shortcut_handler()
    esc = re.search(
        r"e\.key === 'Escape' && document\.getElementById\('qc-backdrop'\)\.classList\.contains\('open'\)",
        handler,
    )
    guard = handler.find("tag === 'INPUT'")
    assert esc, "no Escape branch for the open Quick-Capture modal in the shortcut handler"
    assert esc.start() < guard, "Escape must be handled before the input-focus guard, or Esc is ignored in the modal"


def test_failed_save_shows_the_error():
    handler = _submit_handler()
    assert 'id="qc-error"' in _base()
    assert not re.search(r"\.catch\(function\(\)\s*\{\s*\}\)", handler), "an empty .catch hides failed saves"
    # Both a non-ok response and a network error must reveal the notice.
    assert handler.count("qcError.hidden = false") >= 2
