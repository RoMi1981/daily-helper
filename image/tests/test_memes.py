"""Tests for the Memes module router."""

import io
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = (
    _candidate
    if os.path.isdir(_candidate)
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ.setdefault("REDIS_URL", "redis://localhost:9999")
os.environ.setdefault("DATA_DIR", "/tmp")

import main as _main_module
from starlette.testclient import TestClient


class FakeGit:
    def __init__(self, path):
        import pathlib
        self.local_path = str(path)
        self._committed = []

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def read_committed(self, path: str):
        import pathlib
        full = pathlib.Path(self.local_path) / path
        return full.read_bytes() if full.exists() else None

    def list_committed(self, directory: str) -> list:
        import pathlib
        full = pathlib.Path(self.local_path) / directory
        return [f.name for f in full.iterdir()] if full.is_dir() else []


_PIXEL_PNG = bytes([
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
    0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41,
    0x54, 0x08, 0xd7, 0x63, 0xf8, 0xcf, 0xc0, 0x00,
    0x00, 0x00, 0x02, 0x00, 0x01, 0xe2, 0x21, 0xbc,
    0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e,
    0x44, 0xae, 0x42, 0x60, 0x82,
])


@pytest.fixture()
def client_with_storage(tmp_path):
    from core.state import reset_storage
    reset_storage()
    fake_git = FakeGit(tmp_path)
    memes_dir = tmp_path / "memes"
    memes_dir.mkdir()
    (memes_dir / "abc12345.png").write_bytes(_PIXEL_PNG)

    with (
        patch("modules.memes.router.get_storage"),
        patch("modules.memes.router.get_primary_store", return_value=fake_git),
        patch("modules.memes.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app), fake_git, tmp_path


@pytest.fixture()
def client_no_storage(tmp_path):
    from core.state import reset_storage
    reset_storage()
    with (
        patch("modules.memes.router.get_storage"),
        patch("modules.memes.router.get_primary_store", return_value=None),
        patch("modules.memes.router.get_module_stores", return_value=[]),
    ):
        yield TestClient(_main_module.app)


# ── _list_files ───────────────────────────────────────────────────────────────


def test_list_files_empty(tmp_path):
    from modules.memes.router import _list_files
    assert _list_files(FakeGit(tmp_path)) == []


def test_list_files_returns_entries(tmp_path):
    from modules.memes.router import _list_files
    git = FakeGit(tmp_path)
    d = tmp_path / "memes"
    d.mkdir()
    (d / "abc12345.jpg").write_bytes(b"x")
    (d / "def67890.png").write_bytes(b"y")
    entries = _list_files(git)
    assert len(entries) == 2
    assert {e["id"] for e in entries} == {"abc12345", "def67890"}


def test_list_files_ignores_unknown_extensions(tmp_path):
    from modules.memes.router import _list_files
    git = FakeGit(tmp_path)
    d = tmp_path / "memes"
    d.mkdir()
    (d / "abc12345.txt").write_bytes(b"x")
    (d / "def67890.pdf").write_bytes(b"y")
    (d / "xyz11111.png").write_bytes(b"z")
    entries = _list_files(git)
    assert len(entries) == 1
    assert entries[0]["id"] == "xyz11111"


def test_list_files_sorted_by_id(tmp_path):
    from modules.memes.router import _list_files
    git = FakeGit(tmp_path)
    d = tmp_path / "memes"
    d.mkdir()
    (d / "zzz99999.jpg").write_bytes(b"z")
    (d / "aaa00000.png").write_bytes(b"a")
    entries = _list_files(git)
    assert entries[0]["id"] == "aaa00000"
    assert entries[1]["id"] == "zzz99999"


# ── list route ────────────────────────────────────────────────────────────────


def test_list_returns_200(client_with_storage):
    client, _, _ = client_with_storage
    r = client.get("/memes")
    assert r.status_code == 200
    assert "abc12345" in r.text


def test_list_no_storage_shows_warning(client_no_storage):
    r = client_no_storage.get("/memes")
    assert r.status_code == 200
    assert "No repository" in r.text


# ── upload ────────────────────────────────────────────────────────────────────


def test_upload_png_redirects(client_with_storage):
    client, fake_git, tmp_path = client_with_storage
    r = client.post(
        "/memes/upload",
        files={"file": ("test.png", _PIXEL_PNG, "image/png")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "saved=1" in r.headers["location"]
    assert fake_git._committed


def test_upload_unsupported_extension_400(client_with_storage):
    client, _, _ = client_with_storage
    r = client.post(
        "/memes/upload",
        files={"file": ("test.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 400


def test_upload_no_storage_503(client_no_storage):
    r = client_no_storage.post(
        "/memes/upload",
        files={"file": ("test.png", _PIXEL_PNG, "image/png")},
    )
    assert r.status_code == 503


# ── serve raw ─────────────────────────────────────────────────────────────────


def test_serve_raw_returns_image(client_with_storage):
    client, _, _ = client_with_storage
    r = client.get("/memes/abc12345/raw")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == _PIXEL_PNG


def test_serve_raw_not_found_404(client_with_storage):
    client, _, _ = client_with_storage
    r = client.get("/memes/nonexistent/raw")
    assert r.status_code == 404


def test_serve_no_storage_503(client_no_storage):
    r = client_no_storage.get("/memes/abc12345/raw")
    assert r.status_code == 503


# ── delete ────────────────────────────────────────────────────────────────────


def test_delete_redirects(client_with_storage):
    client, fake_git, tmp_path = client_with_storage
    r = client.post("/memes/abc12345/delete", follow_redirects=False)
    assert r.status_code == 303
    assert fake_git._committed


def test_delete_not_found_404(client_with_storage):
    client, _, _ = client_with_storage
    r = client.post("/memes/nonexistent/delete")
    assert r.status_code == 404


def test_delete_no_storage_503(client_no_storage):
    r = client_no_storage.post("/memes/abc12345/delete")
    assert r.status_code == 503


# ── next (HTMX) ───────────────────────────────────────────────────────────────


def test_next_returns_html(client_with_storage):
    client, _, _ = client_with_storage
    with patch("modules.memes.router._increment_offset", return_value=1):
        r = client.post("/memes/next")
    assert r.status_code == 200


def test_next_no_storage_returns_empty(client_no_storage):
    r = client_no_storage.post("/memes/next")
    assert r.status_code == 200
