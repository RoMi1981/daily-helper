"""Write routes must not run their git sequence on the event loop.

A write is pull → change files → commit → push, and the push alone can take up
to 15 s when the remote is slow. uvicorn runs a single worker, so a write that
runs inside an `async def` route freezes every other request for that time —
the page of a second browser tab simply hangs. The routes therefore hand the
sequence to a worker thread via `asyncio.to_thread`.

Like a missing lock, a missing `to_thread` is invisible: the route works and
only a slow remote shows the difference. So the guarantee is checked twice —
statically over the whole source tree, and per module by running a route and
looking at the thread the storage call landed on.
"""

import ast
import asyncio
import importlib
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if not APP_DIR.is_dir():
    APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))


# ── Static: no lock-holding call directly inside an async def ────────────────


def _takes_write_lock(node: ast.AST) -> bool:
    return isinstance(node, ast.With) and any("write_lock()" in ast.unparse(i.context_expr) for i in node.items)


def _source_trees() -> dict[Path, ast.AST]:
    """Application sources only — the tests build their own fakes."""
    return {
        p: ast.parse(p.read_text(encoding="utf-8")) for p in sorted(APP_DIR.rglob("*.py")) if "tests" not in p.parts
    }


def _writer_names(trees: dict[Path, ast.AST]) -> set[str]:
    """Names of all synchronous functions that take a repo's write lock."""
    return {
        fn.name
        for tree in trees.values()
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef) and any(_takes_write_lock(n) for n in ast.walk(fn))
    }


def _on_loop(fn: ast.AsyncFunctionDef):
    """Nodes that execute on the event loop: nested sync functions and lambdas
    are skipped, they only run where they are called."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


# Same name, different function: neither of these touches a repo.
NOT_A_WRITE = {"asyncio.create_task", "settings_store.delete_template"}


def _writes_on_loop(tree: ast.AST, writers: set[str]) -> list[str]:
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        for node in _on_loop(fn):
            if _takes_write_lock(node):
                found.append(f"{fn.name}:{node.lineno} with write_lock()")
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
                if name in writers and ast.unparse(node.func) not in NOT_A_WRITE:
                    found.append(f"{fn.name}:{node.lineno} {ast.unparse(node.func)}()")
    return found


_TREES = _source_trees()
_WRITERS = _writer_names(_TREES)
_ASYNC_FILES = [p for p, t in _TREES.items() if any(isinstance(n, ast.AsyncFunctionDef) for n in ast.walk(t))]


def test_sources_and_writers_were_found():
    """A broken path would make every other test in here vacuously pass."""
    assert len(_ASYNC_FILES) > 15
    assert {"create_note", "delete_entry", "toggle_favorite", "_do_copy_move"} <= _WRITERS


@pytest.mark.parametrize("path", _ASYNC_FILES, ids=lambda p: os.path.join(p.parent.name, p.name))
def test_no_write_on_the_event_loop(path):
    on_loop = _writes_on_loop(_TREES[path], _WRITERS)
    assert on_loop == [], "write runs on the event loop, wrap it in asyncio.to_thread: " + ", ".join(on_loop)


def test_the_check_recognises_a_write_on_the_loop():
    """The check itself must fail on the pattern it exists for."""
    blocking = ast.parse("async def route(ns):\n    ns.create_note({})\n")
    threaded = ast.parse("async def route(ns):\n    await asyncio.to_thread(ns.create_note, {})\n")
    locked = ast.parse("async def route(store):\n    with store.write_lock():\n        pass\n")
    assert _writes_on_loop(blocking, {"create_note"}) == ["route:2 ns.create_note()"]
    assert _writes_on_loop(threaded, {"create_note"}) == []
    assert _writes_on_loop(locked, set()) == ["route:2 with write_lock()"]


# ── Behaviour: the storage call lands on a worker thread ─────────────────────


class _Probe:
    """Stands in for a storage object and records the thread of every call."""

    def __init__(self, local_path=None):
        self.local_path = str(local_path) if local_path else ""
        self.threads: dict[str, int] = {}
        self._lock = threading.RLock()

    def write_lock(self):
        return self._lock

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.threads[name] = threading.get_ident()
            return True

        return call


def _run(module: str, route: str, patches: dict, **kwargs) -> None:
    mod = importlib.import_module(module)
    with patch.multiple(mod, **patches):
        asyncio.run(getattr(mod, route)(**kwargs))


# (module, route, getter that hands the route its storage, storage method, route kwargs)
SIMPLE = [
    ("appointments", "delete_appointment", "_find_storage", "delete_entry", {"entry_id": "x"}),
    ("eol", "eol_delete", "_find_storage", "delete_entry", {"request": None, "entry_id": "x"}),
    ("mail_templates", "delete_template", "_find_storage", "delete_template", {"template_id": "x"}),
    ("motd", "delete_motd", "_find_storage", "delete_entry", {"motd_id": "x"}),
    ("notes", "delete_note", "_find_storage", "delete_note", {"note_id": "x"}),
    ("rss", "delete_feed", "_find_store", "delete_feed", {"feed_id": "x"}),
    ("runbooks", "delete_runbook", "_find_storage", "delete_runbook", {"runbook_id": "x"}),
    ("snippets", "delete_snippet", "_find_storage", "delete_snippet", {"snippet_id": "x"}),
    ("tasks", "delete_task", "_find_task_storage", "delete_task", {"task_id": "x"}),
    ("ticket_templates", "delete_template", "_find_storage", "delete_template", {"template_id": "x"}),
    ("vacations", "delete_vacation", "_find_storage", "delete_entry", {"entry_id": "x"}),
]


@pytest.mark.parametrize("module,route,getter,method,kwargs", SIMPLE, ids=[row[0] for row in SIMPLE])
def test_storage_write_runs_off_the_loop(module, route, getter, method, kwargs):
    probe = _Probe()
    patches = {getter: lambda *a, **k: probe}
    if module == "mail_templates":  # refuses with 503 before it looks the template up
        patches["_get_all_storages"] = lambda: [probe]
    _run(f"modules.{module}.router", route, patches, **kwargs)
    assert probe.threads[method] != threading.get_ident()


def test_links_write_runs_off_the_loop():
    probe = _Probe()
    section = {"id": "s"}
    _run(
        "modules.links.router",
        "delete_link",
        {
            "_ensure_default_section": lambda: [section],
            "_resolve_section": lambda sections, param: section,
            "_find_link_storage": lambda section_id, link_id: probe,
        },
        link_id="x",
        section="s",
    )
    assert probe.threads["delete_link"] != threading.get_ident()


def test_knowledge_write_runs_off_the_loop():
    probe = _Probe()
    mod = importlib.import_module("modules.knowledge.router")
    with (
        patch.object(mod, "get_storage", lambda: probe),
        patch.object(mod.settings_store, "get_repo", lambda repo_id: {"permissions": {"write": True}}),
    ):
        asyncio.run(mod.delete_entry(repo_id="r", category="c", slug="s"))
    assert probe.threads["delete_entry"] != threading.get_ident()


@pytest.mark.parametrize("module,route", [("memes", "delete_meme"), ("potd", "delete_potd")])
def test_inline_write_sequence_runs_off_the_loop(module, route, tmp_path):
    """These routes carry the pull/commit sequence themselves instead of a storage class."""
    probe = _Probe(tmp_path)
    entry = {"id": "x", "filename": "x.png", "_store": probe}
    _run(
        f"modules.{module}.router",
        route,
        {"get_module_stores": lambda *a: [probe], "get_storage": lambda: None, "_list_files_all": lambda: [entry]},
        entry_id="x",
    )
    loop_thread = threading.get_ident()
    assert probe.threads["_pull"] != loop_thread
    assert probe.threads["_commit_and_push"] != loop_thread


def test_operations_copy_runs_off_the_loop():
    seen: list[int] = []

    def copy_move(*args):
        seen.append(threading.get_ident())
        return 1, []

    _run(
        "modules.operations.router",
        "execute_operation",
        {"get_storage": lambda: object(), "_do_copy_move": copy_move},
        request=None,
        src_repo="a",
        dst_repo="b",
        content_type="knowledge",
        action="copy",
        items=["x"],
    )
    assert seen and seen[0] != threading.get_ident()
