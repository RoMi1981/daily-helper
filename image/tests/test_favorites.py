"""Tests for core/favorites.py — cross-module favorites."""

import os
import sys

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []
        self._pulled = 0

    def _pull(self):
        self._pulled += 1

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def read_committed(self, path: str):
        import os
        full = os.path.join(self.local_path, path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None


class FakeStorage:
    def __init__(self, git):
        self._stores = {"default": git}


@pytest.fixture()
def git(tmp_path):
    return FakeGit(tmp_path)


@pytest.fixture(autouse=True)
def patch_storage(git, monkeypatch):
    fake_storage = FakeStorage(git)
    monkeypatch.setattr("core.state.get_storage", lambda: fake_storage)
    import importlib
    import core.favorites as fav_mod
    importlib.reload(fav_mod)
    yield fav_mod


# ── list_favorites ────────────────────────────────────────────────────────────

def test_list_favorites_empty(patch_storage):
    assert patch_storage.list_favorites() == []


def test_list_favorites_no_storage(monkeypatch):
    monkeypatch.setattr("core.state.get_storage", lambda: None)
    import core.favorites as fav_mod
    assert fav_mod.list_favorites() == []


def test_list_favorites_malformed_yaml(git, patch_storage, tmp_path):
    (tmp_path / "favorites.yaml").write_text("not: a: list", encoding="utf-8")
    result = patch_storage.list_favorites()
    assert result == []


# ── toggle_favorite ───────────────────────────────────────────────────────────

def test_toggle_add(patch_storage):
    added = patch_storage.toggle_favorite("notes", "abc123", "My Note", "/notes/abc123")
    assert added is True
    favorites = patch_storage.list_favorites()
    assert len(favorites) == 1
    assert favorites[0]["module"] == "notes"
    assert favorites[0]["id"] == "abc123"
    assert favorites[0]["title"] == "My Note"
    assert favorites[0]["url"] == "/notes/abc123"
    assert "pinned_at" in favorites[0]


def test_toggle_remove(patch_storage):
    patch_storage.toggle_favorite("notes", "abc123", "My Note", "/notes/abc123")
    removed = patch_storage.toggle_favorite("notes", "abc123", "My Note", "/notes/abc123")
    assert removed is False
    assert patch_storage.list_favorites() == []


def test_toggle_different_modules_independent(patch_storage):
    patch_storage.toggle_favorite("notes", "id1", "Note", "/notes/id1")
    patch_storage.toggle_favorite("tasks", "id1", "Task", "/tasks/id1")
    favorites = patch_storage.list_favorites()
    assert len(favorites) == 2


def test_toggle_remove_only_matching_module(patch_storage):
    patch_storage.toggle_favorite("notes", "id1", "Note", "/notes/id1")
    patch_storage.toggle_favorite("tasks", "id1", "Task", "/tasks/id1")
    patch_storage.toggle_favorite("notes", "id1", "Note", "/notes/id1")  # remove notes
    favorites = patch_storage.list_favorites()
    assert len(favorites) == 1
    assert favorites[0]["module"] == "tasks"


def test_toggle_no_storage(monkeypatch):
    monkeypatch.setattr("core.state.get_storage", lambda: None)
    import core.favorites as fav_mod
    result = fav_mod.toggle_favorite("notes", "x", "title", "/url")
    assert result is False


def test_toggle_commits_to_git(git, patch_storage):
    patch_storage.toggle_favorite("notes", "id1", "Note", "/notes/id1")
    assert any("favorites" in msg for msg in git._committed)


def test_toggle_pulls_before_write(git, patch_storage):
    patch_storage.toggle_favorite("notes", "id1", "Note", "/notes/id1")
    assert git._pulled >= 1


def test_toggle_multiple_entries(patch_storage):
    patch_storage.toggle_favorite("notes", "a", "A", "/notes/a")
    patch_storage.toggle_favorite("notes", "b", "B", "/notes/b")
    patch_storage.toggle_favorite("links", "c", "C", "/links/c")
    favorites = patch_storage.list_favorites()
    assert len(favorites) == 3


# ── is_favorite ───────────────────────────────────────────────────────────────

def test_is_favorite_false_when_empty(patch_storage):
    assert patch_storage.is_favorite("notes", "x") is False


def test_is_favorite_true_after_add(patch_storage):
    patch_storage.toggle_favorite("notes", "id1", "N", "/notes/id1")
    assert patch_storage.is_favorite("notes", "id1") is True


def test_is_favorite_false_after_remove(patch_storage):
    patch_storage.toggle_favorite("notes", "id1", "N", "/notes/id1")
    patch_storage.toggle_favorite("notes", "id1", "N", "/notes/id1")
    assert patch_storage.is_favorite("notes", "id1") is False


def test_is_favorite_no_storage(monkeypatch):
    monkeypatch.setattr("core.state.get_storage", lambda: None)
    import core.favorites as fav_mod
    assert fav_mod.is_favorite("notes", "x") is False


def test_is_favorite_module_specific(patch_storage):
    patch_storage.toggle_favorite("notes", "id1", "N", "/notes/id1")
    assert patch_storage.is_favorite("tasks", "id1") is False
    assert patch_storage.is_favorite("notes", "id1") is True
