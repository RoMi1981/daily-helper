"""Tests for the Picture of the Day (PotD) module — ID-based collection."""

import os
import sys
from datetime import date
from unittest.mock import patch

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = (
    _candidate
    if os.path.isdir(_candidate)
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"

import main as _main_module


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
        import pathlib

        full = pathlib.Path(self.local_path) / path
        return full.read_bytes() if full.exists() else None

    def list_committed(self, directory: str) -> list:
        import pathlib

        full = pathlib.Path(self.local_path) / directory
        return [f.name for f in full.iterdir()] if full.is_dir() else []


# ── _list_files ───────────────────────────────────────────────────────────────


def test_list_files_empty(tmp_path):
    from modules.potd.router import _list_files

    assert _list_files(FakeGit(tmp_path)) == []


def test_list_files_returns_image_entries(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc12345.jpg").write_bytes(b"a")
    (potd_dir / "def67890.png").write_bytes(b"b")

    entries = _list_files(git)
    assert len(entries) == 2
    ids = {e["id"] for e in entries}
    assert ids == {"abc12345", "def67890"}


def test_list_files_sorted_by_id(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "zzz.jpg").write_bytes(b"z")
    (potd_dir / "aaa.png").write_bytes(b"a")
    (potd_dir / "mmm.webp").write_bytes(b"m")

    entries = _list_files(git)
    assert [e["id"] for e in entries] == ["aaa", "mmm", "zzz"]


def test_list_files_skips_unknown_extensions(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc.jpg").write_bytes(b"img")
    (potd_dir / "xyz.mp4").write_bytes(b"video")
    (potd_dir / "foo.txt").write_bytes(b"text")

    entries = _list_files(git)
    assert len(entries) == 1
    assert entries[0]["ext"] == "jpg"


def test_list_files_normalises_extension(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc.JPG").write_bytes(b"img")

    entries = _list_files(git)
    assert entries[0]["ext"] == "jpg"


def test_list_files_skips_files_without_extension(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "noextension").write_bytes(b"x")
    (potd_dir / "abc.png").write_bytes(b"ok")

    entries = _list_files(git)
    assert len(entries) == 1


def test_list_files_pdf_with_sidecar_reads_page(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc.pdf").write_bytes(b"%PDF")
    (potd_dir / "abc.yaml").write_bytes(b"page: 7\n")

    entries = _list_files(git)
    assert len(entries) == 1
    assert entries[0]["page"] == 7


def test_list_files_includes_virtual_entries(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "src001.pdf").write_bytes(b"%PDF")
    (potd_dir / "pg0001.yaml").write_bytes(b"source: src001.pdf\npage: 1\n")
    (potd_dir / "pg0002.yaml").write_bytes(b"source: src001.pdf\npage: 2\n")
    (potd_dir / "pg0003.yaml").write_bytes(b"source: src001.pdf\npage: 3\n")

    entries = _list_files(git)
    assert len(entries) == 4  # PDF itself + 3 virtual entries


def test_list_files_virtual_entry_uses_source_filename(tmp_path):
    from modules.potd.router import _list_files

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "src001.pdf").write_bytes(b"%PDF")
    (potd_dir / "pg0002.yaml").write_bytes(b"source: src001.pdf\npage: 2\n")

    entries = _list_files(git)
    virtual = next(e for e in entries if e["id"] == "pg0002")
    assert virtual["filename"] == "src001.pdf"
    assert virtual["page"] == 2
    assert virtual["source"] == "src001.pdf"


# ── get_daily ─────────────────────────────────────────────────────────────────


def test_get_daily_none_when_empty(tmp_path):
    from modules.potd.router import get_daily

    assert get_daily(FakeGit(tmp_path)) is None


def test_get_daily_returns_entry(tmp_path):
    from modules.potd.router import get_daily

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc.jpg").write_bytes(b"img")

    result = get_daily(git)
    assert result is not None
    assert result["id"] == "abc"


def test_get_daily_deterministic(tmp_path):
    from modules.potd.router import get_daily

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    for name in ["aaa.jpg", "bbb.png", "ccc.webp"]:
        (potd_dir / name).write_bytes(b"x")

    r1 = get_daily(git, offset=0)
    r2 = get_daily(git, offset=0)
    assert r1["id"] == r2["id"]


def test_get_daily_offset_changes_result(tmp_path):
    from modules.potd.router import get_daily

    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    for name in ["aaa.jpg", "bbb.png", "ccc.webp", "ddd.gif", "eee.jpg"]:
        (potd_dir / name).write_bytes(b"x")

    results = {get_daily(git, offset=i)["id"] for i in range(5)}
    assert len(results) > 1


# ── Router isolation ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib
    from core import settings_store

    importlib.reload(settings_store)
    from core import settings_store as ss

    _main_module.settings_store = ss
    yield
    from core.state import reset_storage

    reset_storage()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


@pytest.fixture()
def client_with_store(tmp_path, isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    git = FakeGit(tmp_path)
    with (
        patch("modules.potd.router._get_store", return_value=git),
        patch("modules.potd.router.get_module_stores", return_value=[git]),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), git, tmp_path


# ── GET /potd ─────────────────────────────────────────────────────────────────


def test_list_no_storage(client):
    assert client.get("/potd").status_code == 200


def test_list_empty(client_with_store):
    client, _, _ = client_with_store
    assert client.get("/potd").status_code == 200


def test_list_shows_entries(client_with_store):
    client, _, tmp_path = client_with_store
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc12345.jpg").write_bytes(b"\xff\xd8\xff")

    resp = client.get("/potd")
    assert resp.status_code == 200
    assert b"abc12345" in resp.content


def test_list_saved_banner(client_with_store):
    client, _, _ = client_with_store
    resp = client.get("/potd?saved=1")
    assert b"saved" in resp.content.lower()


# ── POST /potd/upload ─────────────────────────────────────────────────────────


def test_upload_jpg(client_with_store):
    client, git, tmp_path = client_with_store
    resp = client.post(
        "/potd/upload",
        files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0test", "image/jpeg")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    potd_dir = tmp_path / "potd"
    jpegs = list(potd_dir.glob("*.jpg"))
    assert len(jpegs) == 1
    assert any("add" in c for c in git._committed)


def test_upload_png(client_with_store):
    client, _, tmp_path = client_with_store
    client.post(
        "/potd/upload",
        files={"file": ("img.png", b"\x89PNG\r\n", "image/png")},
        follow_redirects=False,
    )
    assert len(list((tmp_path / "potd").glob("*.png"))) == 1


def test_upload_invalid_extension(client_with_store):
    client, _, _ = client_with_store
    resp = client.post(
        "/potd/upload",
        files={"file": ("video.mp4", b"data", "video/mp4")},
    )
    assert resp.status_code == 400


def test_upload_no_storage(client):
    resp = client.post(
        "/potd/upload",
        files={"file": ("img.jpg", b"data", "image/jpeg")},
    )
    assert resp.status_code == 503


def test_upload_one_commit_per_image(client_with_store):
    client, git, _ = client_with_store
    before = len(git._committed)
    client.post(
        "/potd/upload",
        files={"file": ("photo.jpg", b"data", "image/jpeg")},
        follow_redirects=False,
    )
    assert len(git._committed) - before == 1


def test_upload_pdf_creates_sidecars(client_with_store):
    client, git, tmp_path = client_with_store

    import io
    from pypdf import PdfWriter

    buf = io.BytesIO()
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=200, height=200)
    w.write(buf)
    pdf_bytes = buf.getvalue()

    resp = client.post(
        "/potd/upload",
        files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    potd_dir = tmp_path / "potd"
    pdfs = list(potd_dir.glob("*.pdf"))
    yamls = list(potd_dir.glob("*.yaml"))
    assert len(pdfs) == 1
    assert len(yamls) == 3


def test_upload_pdf_one_commit(client_with_store):
    import io
    from pypdf import PdfWriter

    client, git, _ = client_with_store
    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(buf)

    before = len(git._committed)
    client.post(
        "/potd/upload",
        files={"file": ("doc.pdf", buf.getvalue(), "application/pdf")},
        follow_redirects=False,
    )
    assert len(git._committed) - before == 1


# ── GET /potd/{id}/raw ────────────────────────────────────────────────────────


def test_serve_image(client_with_store):
    client, _, tmp_path = client_with_store
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    img_data = b"\xff\xd8\xff\xe0" + b"x" * 100
    (potd_dir / "abc12345.jpg").write_bytes(img_data)

    resp = client.get("/potd/abc12345/raw")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == img_data


def test_serve_pdf(client_with_store):
    client, _, tmp_path = client_with_store
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc12345.pdf").write_bytes(b"%PDF-1.4")

    resp = client.get("/potd/abc12345/raw")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]


def test_serve_not_found(client_with_store):
    client, _, _ = client_with_store
    assert client.get("/potd/doesnotexist/raw").status_code == 404


def test_serve_no_storage(client):
    assert client.get("/potd/abc12345/raw").status_code == 503


def test_serve_virtual_entry_uses_source_file(client_with_store):
    client, _, tmp_path = client_with_store
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    pdf_data = b"%PDF-1.4 source"
    (potd_dir / "src001.pdf").write_bytes(pdf_data)
    (potd_dir / "pg0002.yaml").write_bytes(b"source: src001.pdf\npage: 2\n")

    resp = client.get("/potd/pg0002/raw")
    assert resp.status_code == 200
    assert resp.content == pdf_data


# ── POST /potd/{id}/delete ────────────────────────────────────────────────────


def test_delete_existing(client_with_store):
    client, git, tmp_path = client_with_store
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    target = potd_dir / "abc12345.jpg"
    target.write_bytes(b"img")

    resp = client.post("/potd/abc12345/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert not target.exists()
    assert any("delete" in c for c in git._committed)


def test_delete_not_found(client_with_store):
    client, _, _ = client_with_store
    assert client.post("/potd/doesnotexist/delete").status_code == 404


def test_delete_no_storage(client):
    assert client.post("/potd/abc12345/delete").status_code == 503


def test_delete_removes_sidecar(client_with_store):
    client, _, tmp_path = client_with_store
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc12345.pdf").write_bytes(b"%PDF")
    (potd_dir / "abc12345.yaml").write_bytes(b"page: 4\n")

    resp = client.post("/potd/abc12345/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert not (potd_dir / "abc12345.pdf").exists()
    assert not (potd_dir / "abc12345.yaml").exists()


def test_delete_virtual_removes_only_sidecar(client_with_store):
    client, _, tmp_path = client_with_store
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "src001.pdf").write_bytes(b"%PDF")
    (potd_dir / "pg0002.yaml").write_bytes(b"source: src001.pdf\npage: 2\n")

    resp = client.post("/potd/pg0002/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert not (potd_dir / "pg0002.yaml").exists()
    assert (potd_dir / "src001.pdf").exists()


# ── /api/home/potd ────────────────────────────────────────────────────────────


def test_home_potd_widget_empty(client_with_store):
    client, _, _ = client_with_store
    resp = client.get("/api/home/potd")
    assert resp.status_code == 200
    assert b"<img" not in resp.content
    assert b"<iframe" not in resp.content


def test_home_potd_widget_shows_image(tmp_path, isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc12345.jpg").write_bytes(b"\xff\xd8\xff")

    with (
        patch("modules.potd.router._get_store", return_value=git),
        patch("modules.potd.router.get_module_stores", return_value=[git]),
    ):
        client = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = client.get("/api/home/potd")
    assert resp.status_code == 200
    assert b"<img" in resp.content


def test_home_potd_widget_shows_pdf(tmp_path, isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    git = FakeGit(tmp_path)
    potd_dir = tmp_path / "potd"
    potd_dir.mkdir()
    (potd_dir / "abc12345.pdf").write_bytes(b"%PDF")

    with (
        patch("modules.potd.router._get_store", return_value=git),
        patch("modules.potd.router.get_module_stores", return_value=[git]),
    ):
        client = TestClient(_main_module.app, raise_server_exceptions=False)
        resp = client.get("/api/home/potd")
    assert resp.status_code == 200
    assert b"<iframe" in resp.content


def test_home_potd_widget_disabled_module(tmp_path, isolated_settings):
    from fastapi.testclient import TestClient
    from core import settings_store
    from core.state import reset_storage

    reset_storage()
    cfg = settings_store.load()
    cfg.setdefault("modules_enabled", {})["potd"] = False
    settings_store.save(cfg)

    client = TestClient(_main_module.app, raise_server_exceptions=False)
    resp = client.get("/api/home/potd")
    assert resp.status_code == 200
    assert resp.content == b""
