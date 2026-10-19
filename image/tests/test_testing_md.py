"""Every test file is listed in TESTING.md.

TESTING.md used to describe tests one by one; it covered 22 of 61 unit test
files and still described home-page tests that had long been rewritten. It now
holds one line per file, and this check keeps the list complete.

TESTING.md is read from the repository (local runs) or from TESTING_MD, which
the CI test job fills: the file is not part of the test image.
"""

import os
from pathlib import Path

import pytest

_here = Path(__file__).resolve().parent


def _testing_md() -> str:
    content = os.environ.get("TESTING_MD")
    if content:
        return content
    repo_copy = _here.parent.parent / "TESTING.md"
    if repo_copy.is_file():
        return repo_copy.read_text(encoding="utf-8")
    pytest.skip("TESTING.md not available (set TESTING_MD when running inside the test image)")


def test_every_test_file_is_listed():
    text = _testing_md()
    files = sorted(p.name for d in (_here, _here / "e2e") for p in d.glob("test_*.py"))
    missing = [f for f in files if f"`{f}`" not in text]
    assert not missing, "Add these files to TESTING.md:\n" + "\n".join(missing)
