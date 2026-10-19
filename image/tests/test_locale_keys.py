"""Every t("…") key used in the code must exist in the locale files.

`core/i18n.t()` falls back to the key itself when it is missing, so a typo
or a forgotten entry renders the raw key into the UI instead of raising —
that is how `t('action.next')` shipped, showing a literal "action.next" as
the meme button's tooltip. Nothing else in the stack notices.
"""

import json
import re
from pathlib import Path

import pytest

_here = Path(__file__).resolve().parent
APP = next(p for p in (_here.parent / "app", _here.parent) if (p / "locales").is_dir())

# The project's keys are dotted lowercase; this shape avoids matching
# unrelated one-letter calls like `.split(...)` or JS helpers in templates.
_KEY_CALL = re.compile(r"""\bt\(\s*["']([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)["']""")


def _locale(name: str) -> dict:
    return json.loads((APP / "locales" / f"{name}.json").read_text(encoding="utf-8"))


def _used_keys() -> dict[str, list[str]]:
    """key -> files referencing it."""
    used: dict[str, list[str]] = {}
    for path in list(APP.rglob("templates/**/*.html")) + list(APP.rglob("*.py")):
        # In the test image the app is copied to the root, so tests/ sits
        # inside APP — skip it: test_i18n.py deliberately looks up a missing
        # key to assert the fallback behaviour.
        if "tests" in path.parts:
            continue
        for key in _KEY_CALL.findall(path.read_text(encoding="utf-8")):
            used.setdefault(key, []).append(path.name)
    return used


def test_every_used_key_is_defined():
    en = _locale("en")
    missing = {k: v for k, v in _used_keys().items() if k not in en}
    assert not missing, "t() keys used in the code but missing from locales/en.json: " + ", ".join(
        f"{k} (in {', '.join(sorted(set(f)))})" for k, f in sorted(missing.items())
    )


@pytest.mark.parametrize("lang", ["de"])
def test_locales_have_the_same_keys(lang):
    """A key present in one locale but not the other silently falls back to
    English for that language, which reads as a half-translated page."""
    en, other = set(_locale("en")), set(_locale(lang))
    assert not en - other, f"missing in {lang}.json: {sorted(en - other)}"
    assert not other - en, f"missing in en.json: {sorted(other - en)}"
