"""Every write to a repo must sit inside that repo's write lock.

A missing lock is invisible: the code works, the tests pass, and only two
concurrent requests lose an update. So the guarantee is checked statically over
the whole source tree rather than per call site — the first version of the
lock rollout missed six delete paths exactly because they commit in one method
and pull in another.
"""

import ast
import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if not APP_DIR.is_dir():
    APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

WRITE_CALLS = ("_pull", "_commit_and_push")


def _locked_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            items = " ".join(ast.unparse(item.context_expr) for item in node.items)
            if "write_lock()" in items:
                ranges.append((node.lineno, node.end_lineno))
    return ranges


def _unlocked_writes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    ranges = _locked_ranges(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in WRITE_CALLS and not any(a <= node.lineno <= b for a, b in ranges):
                found.append(f"{path.name}:{node.lineno} {node.func.attr}()")
    return found


# storage.py defines the primitives themselves, yaml_dir_storage._delete pulls
# on behalf of a caller that holds the lock, and favorites._save documents the
# same contract in its docstring.
EXEMPT = {"core/storage.py", "core/yaml_dir_storage.py", "core/favorites.py"}


def _source_files() -> list[Path]:
    """Application sources only — the tests build their own fakes."""
    return sorted(
        p
        for p in APP_DIR.rglob("*.py")
        if "tests" not in p.parts and "_commit_and_push" in p.read_text(encoding="utf-8")
    )


def test_source_files_were_found():
    """A broken path would make every other test in here vacuously pass."""
    assert len(_source_files()) > 5


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: os.path.join(p.parent.name, p.name))
def test_no_write_outside_the_lock(path):
    if path.relative_to(APP_DIR).as_posix() in EXEMPT:
        pytest.skip(f"{path.name} defines or delegates the primitives themselves")
    unlocked = _unlocked_writes(path)
    assert unlocked == [], "write outside write_lock(): " + ", ".join(unlocked)
