"""Tests for Links module — storage and router."""

import os
import sys
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


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []

    def _pull(self):
        pass

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

    def list_committed(self, directory: str) -> list:
        import os

        full = os.path.join(self.local_path, directory)
        if not os.path.isdir(full):
            return []
        return os.listdir(full)


@pytest.fixture()
def link_storage(tmp_path):
    from modules.links.storage import LinkStorage

    return LinkStorage(FakeGit(tmp_path), "default")


def test_list_empty(link_storage):
    assert link_storage.list_links() == []


def test_create_and_list(link_storage):
    l = link_storage.create_link(
        {"title": "Grafana", "url": "https://grafana.example.com", "category": "Monitoring"}
    )
    assert l["title"] == "Grafana"
    assert l["url"] == "https://grafana.example.com"
    assert l["category"] == "Monitoring"
    links = link_storage.list_links()
    assert len(links) == 1


def test_get_link(link_storage):
    l = link_storage.create_link({"title": "Test", "url": "https://example.com"})
    assert link_storage.get_link(l["id"]) is not None


def test_get_link_missing(link_storage):
    assert link_storage.get_link("nope") is None


def test_update_link(link_storage):
    l = link_storage.create_link({"title": "Old", "url": "https://old.com"})
    updated = link_storage.update_link(l["id"], {"title": "New", "url": "https://new.com"})
    assert updated["title"] == "New"
    assert updated["url"] == "https://new.com"


def test_update_missing(link_storage):
    assert link_storage.update_link("ghost", {"title": "x", "url": "https://x.com"}) is None


def test_delete_link(link_storage):
    l = link_storage.create_link({"title": "Bye", "url": "https://bye.com"})
    assert link_storage.delete_link(l["id"]) is True
    assert link_storage.get_link(l["id"]) is None


def test_delete_missing(link_storage):
    assert link_storage.delete_link("ghost") is False


def test_search_title(link_storage):
    link_storage.create_link({"title": "Grafana", "url": "https://grafana.example.com"})
    link_storage.create_link({"title": "Jenkins", "url": "https://jenkins.example.com"})
    results = link_storage.list_links(query="grafana")
    assert len(results) == 1
    assert results[0]["title"] == "Grafana"


def test_search_description(link_storage):
    link_storage.create_link(
        {"title": "Docs", "url": "https://docs.example.com", "description": "internal wiki"}
    )
    link_storage.create_link(
        {"title": "Other", "url": "https://other.com", "description": "nothing"}
    )
    assert len(link_storage.list_links(query="wiki")) == 1


def test_filter_by_category(link_storage):
    link_storage.create_link({"title": "A", "url": "https://a.com", "category": "CI/CD"})
    link_storage.create_link({"title": "B", "url": "https://b.com", "category": "Monitoring"})
    results = link_storage.list_links(category="CI/CD")
    assert len(results) == 1
    assert results[0]["title"] == "A"


def test_get_categories(link_storage):
    link_storage.create_link({"title": "A", "url": "https://a.com", "category": "Monitoring"})
    link_storage.create_link({"title": "B", "url": "https://b.com", "category": "CI/CD"})
    link_storage.create_link({"title": "C", "url": "https://c.com", "category": "Monitoring"})
    cats = link_storage.get_categories()
    assert cats == ["CI/CD", "Monitoring"]


def test_sorted_by_category_then_title(link_storage):
    link_storage.create_link({"title": "Z Link", "url": "https://z.com", "category": "AAA"})
    link_storage.create_link({"title": "A Link", "url": "https://a.com", "category": "BBB"})
    link_storage.create_link({"title": "M Link", "url": "https://m.com", "category": "AAA"})
    links = link_storage.list_links()
    assert links[0]["category"] == "AAA"
    assert links[0]["title"] == "M Link"
    assert links[1]["title"] == "Z Link"
    assert links[2]["category"] == "BBB"


import main as _main_module


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
def client(isolated_settings):
    from fastapi.testclient import TestClient
    from core.state import reset_storage

    reset_storage()
    return TestClient(_main_module.app, raise_server_exceptions=False)


@pytest.fixture()
def client_with_storage(tmp_path, isolated_settings):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from core import settings_store

    reset_storage()

    # Auto-create default section so router doesn't hit settings_store
    cfg = settings_store.load()
    cfg["link_sections"] = [
        {
            "id": "default",
            "name": "Default",
            "floccus_enabled": False,
            "floccus_username": "",
            "floccus_password": "",
        }
    ]
    settings_store.save(cfg)

    fake_git = FakeGit(tmp_path)
    from modules.links.storage import LinkStorage

    real_storage = LinkStorage(fake_git, "default")

    with (
        patch("modules.links.router.get_storage"),
        patch("modules.links.router.get_primary_store", return_value=fake_git),
        patch("modules.links.router.get_module_stores", return_value=[fake_git]),
    ):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


def test_links_list_no_storage(client):
    resp = client.get("/links")
    assert resp.status_code == 200
    assert "No repository" in resp.text


def test_links_404_disabled(client):
    from core import settings_store

    cfg = settings_store.load()
    cfg["modules_enabled"]["links"] = False
    settings_store.save(cfg)
    assert client.get("/links").status_code == 404


def test_links_create(client_with_storage):
    c, storage = client_with_storage
    resp = c.post(
        "/links/new",
        data={"title": "Grafana", "url": "https://grafana.example.com", "category": "Monitoring"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert len(storage.list_links()) == 1


def test_links_edit_form(client_with_storage):
    c, storage = client_with_storage
    l = storage.create_link({"title": "Test", "url": "https://test.com"})
    resp = c.get(f"/links/{l['id']}/edit")
    assert resp.status_code == 200
    assert "Test" in resp.text


def test_links_update(client_with_storage):
    c, storage = client_with_storage
    l = storage.create_link({"title": "Old", "url": "https://old.com"})
    c.post(
        f"/links/{l['id']}/edit",
        data={"title": "New", "url": "https://new.com"},
        follow_redirects=True,
    )
    assert storage.get_link(l["id"])["title"] == "New"


def test_links_delete(client_with_storage):
    c, storage = client_with_storage
    l = storage.create_link({"title": "Del", "url": "https://del.com"})
    c.post(f"/links/{l['id']}/delete", follow_redirects=True)
    assert storage.get_link(l["id"]) is None


def test_links_search_filter(client_with_storage):
    c, storage = client_with_storage
    storage.create_link(
        {"title": "Grafana", "url": "https://grafana.com", "category": "Monitoring"}
    )
    storage.create_link({"title": "Jenkins", "url": "https://jenkins.com", "category": "CI/CD"})
    resp = c.get("/links?q=grafana")
    assert resp.status_code == 200
    assert "Grafana" in resp.text
    assert "Jenkins" not in resp.text


# ── Section + Migration tests ─────────────────────────────────────────────────


def test_storage_section_isolation(tmp_path):
    """Two LinkStorage instances for different sections are isolated."""
    from modules.links.storage import LinkStorage

    git = FakeGit(tmp_path)
    s1 = LinkStorage(git, "work")
    s2 = LinkStorage(git, "home")
    s1.create_link({"title": "Work", "url": "https://work.example.com"})
    assert len(s1.list_links()) == 1
    assert len(s2.list_links()) == 0


def test_migration_flat_to_section(tmp_path):
    """migrate_flat_to_section moves flat links/*.yaml to links/{section_id}/."""
    import yaml
    from modules.links.migration import migrate_flat_to_section

    git = FakeGit(tmp_path)
    flat_dir = tmp_path / "links"
    flat_dir.mkdir()
    link = {
        "id": "abc12345",
        "title": "Old",
        "url": "https://old.com",
        "category": "Dev",
        "description": "",
        "created": "2026-01-01",
    }
    (flat_dir / "abc12345.yaml").write_text(yaml.dump(link), encoding="utf-8")

    migrated = migrate_flat_to_section(git, "default")
    assert migrated is True
    assert not (flat_dir / "abc12345.yaml").exists()
    assert (flat_dir / "default" / "abc12345.yaml").exists()


def test_migration_noop_when_empty(tmp_path):
    """migrate_flat_to_section returns False when no flat files exist."""
    from modules.links.migration import migrate_flat_to_section

    git = FakeGit(tmp_path)
    assert migrate_flat_to_section(git, "default") is False


def test_migration_noop_when_already_in_section(tmp_path):
    """migrate_flat_to_section ignores files already in subdirectories."""
    import yaml
    from modules.links.migration import migrate_flat_to_section

    git = FakeGit(tmp_path)
    section_dir = tmp_path / "links" / "default"
    section_dir.mkdir(parents=True)
    link = {
        "id": "xyz",
        "title": "New",
        "url": "https://new.com",
        "category": "",
        "description": "",
        "created": "2026-01-01",
    }
    (section_dir / "xyz.yaml").write_text(yaml.dump(link), encoding="utf-8")

    migrated = migrate_flat_to_section(git, "default")
    assert migrated is False


def test_section_dropdown_shown_for_multiple_sections(client_with_storage):
    """Section select appears when more than one section is configured."""
    from core import settings_store

    cfg = settings_store.load()
    cfg["link_sections"].append(
        {
            "id": "work",
            "name": "Work",
            "floccus_enabled": False,
            "floccus_username": "",
            "floccus_password": "",
        }
    )
    settings_store.save(cfg)
    c, _ = client_with_storage
    resp = c.get("/links")
    assert resp.status_code == 200
    assert "section-select" in resp.text
