"""docs/api.md must match the application's routes, in both directions.

The reference had drifted badly: eight entries named routes that did not exist
(four `/api/home/*` endpoints, `toggle-pin` instead of `pin`, `GET` for a
`POST`), and about eighty routes were missing — the whole EOL module among them.
Descriptions stay hand-written; this test only guarantees that every route is
listed with its method and that nothing listed is gone.

The file is read from the repository (local runs) or from API_DOC_MD, which the
CI test job fills: docs/ is not part of the test image.
"""

import os
import re
import sys
from pathlib import Path

import pytest

_here = Path(__file__).resolve().parent
APP = next(p for p in (_here.parent / "app", _here.parent) if (p / "main.py").is_file())
sys.path.insert(0, str(APP))
os.environ.setdefault("REDIS_URL", "redis://localhost:9999")

_ROW = re.compile(r"^\|\s*([A-Z]+)\s*\|\s*`([^`]+)`\s*\|")
_SKIP = ("/static", "/openapi", "/docs", "/redoc")


def _api_md() -> str:
    content = os.environ.get("API_DOC_MD")
    if content:
        return content
    repo_copy = _here.parent.parent / "docs" / "api.md"
    if repo_copy.is_file():
        return repo_copy.read_text(encoding="utf-8")
    pytest.skip("docs/api.md not available (set API_DOC_MD when running inside the test image)")


def _documented() -> set[tuple[str, str]]:
    return {(m.group(1), m.group(2)) for line in _api_md().splitlines() if (m := _ROW.match(line))}


def _routes() -> set[tuple[str, str]]:
    import main

    found = set()
    for r in main.app.routes:
        path = getattr(r, "path", None)
        if not path or path.startswith(_SKIP):
            continue
        for method in getattr(r, "methods", None) or ():
            if method != "HEAD":
                found.add((method, path))
    return found


def test_every_route_is_documented():
    missing = sorted(_routes() - _documented())
    assert not missing, "Routes missing from docs/api.md:\n" + "\n".join(f"  {m} {p}" for m, p in missing)


def test_every_documented_route_exists():
    stale = sorted(_documented() - _routes())
    assert not stale, "docs/api.md lists routes the app does not have:\n" + "\n".join(f"  {m} {p}" for m, p in stale)
