"""Links are stored per section (links/{section_id}/).

LinkStorage defaults to the "default" section, so a caller that wants all of a
repo's links and just writes LinkStorage(store) silently sees only one section.
That defect shipped three times — global search, bookmarks widget, and the
category list of its settings popover — each time without an error message.
"""

import ast
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if not APP_DIR.is_dir():
    APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

# The links module itself resolves the section from the request, and the
# Floccus sync is per section by definition.
EXEMPT = {"modules/links/router.py", "modules/links/floccus_api.py", "modules/links/storage.py"}

# Callers that must walk every section — kept as a list so removing one from a
# module (rather than fixing it) is visible in the diff.
ALL_SECTION_CALLERS = ("core/global_search.py", "modules/widgets/loaders.py", "modules/operations/router.py")


def _single_section_constructions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "LinkStorage":
            if len(node.args) + len(node.keywords) < 2:
                found.append(f"{path.name}:{node.lineno}")
    return found


def _files_using_link_storage() -> list[Path]:
    """Application sources only — tests build their own fakes."""
    return sorted(
        p for p in APP_DIR.rglob("*.py") if "tests" not in p.parts and "LinkStorage(" in p.read_text(encoding="utf-8")
    )


def test_files_were_found():
    assert _files_using_link_storage(), "path resolution broken — the test would pass vacuously"


@pytest.mark.parametrize("path", _files_using_link_storage(), ids=lambda p: os.path.join(p.parent.name, p.name))
def test_no_caller_builds_only_the_default_section(path):
    if path.relative_to(APP_DIR).as_posix() in EXEMPT:
        pytest.skip("section comes from the request or is the storage itself")
    offenders = _single_section_constructions(path)
    assert offenders == [], "use link_storages(store) to cover every section: " + ", ".join(offenders)


def test_link_storages_returns_one_storage_per_configured_section():
    from modules.links.storage import link_storages

    with patch("core.settings_store.get_link_sections", return_value=[{"id": "default"}, {"id": "work"}]):
        storages = link_storages(MagicMock(local_path="/tmp"))
    assert [s._section_id for s in storages] == ["default", "work"]


def test_link_storages_falls_back_to_default_when_none_are_configured():
    """A fresh instance has no sections yet; returning nothing would make the
    links look lost rather than empty."""
    from modules.links.storage import link_storages

    with patch("core.settings_store.get_link_sections", return_value=[]):
        storages = link_storages(MagicMock(local_path="/tmp"))
    assert [s._section_id for s in storages] == ["default"]


@pytest.mark.parametrize("rel_path", ALL_SECTION_CALLERS)
def test_known_callers_use_the_helper(rel_path):
    """These three read *all* of a repo's links; if one stops using
    link_storages() it is back to seeing only the default section."""
    source = (APP_DIR / rel_path).read_text(encoding="utf-8")
    assert "link_storages(" in source
