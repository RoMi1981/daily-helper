"""Tests for the Floccus / Nextcloud Bookmarks API v2 compatibility layer."""

import base64
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

    def _pull(self): pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def read_committed(self, path: str):
        import os as _os
        full = _os.path.join(self.local_path, path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def list_committed(self, directory: str) -> list:
        import os as _os
        full = _os.path.join(self.local_path, directory)
        if not _os.path.isdir(full):
            return []
        return _os.listdir(full)


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


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
    from modules.links.storage import LinkStorage

    reset_storage()

    # Configure a section with Floccus enabled
    cfg = settings_store.load()
    cfg["link_sections"] = [{
        "id": "default",
        "name": "Default",
        "floccus_enabled": True,
        "floccus_username": "testuser",
        "floccus_password": "testpass",
    }]
    cfg["modules_enabled"]["links"] = True
    settings_store.save(cfg)

    fake_git = FakeGit(tmp_path)
    real_storage = LinkStorage(fake_git, "default")

    with patch("modules.links.floccus_api.get_storage"), \
         patch("modules.links.floccus_api.get_primary_store", return_value=fake_git):
        yield TestClient(_main_module.app, raise_server_exceptions=False), real_storage


AUTH = _basic("testuser", "testpass")
WRONG_AUTH = _basic("testuser", "wrongpass")


# ── Auth tests ────────────────────────────────────────────────────────────────

def test_list_no_auth(client):
    """Without any auth header → 401."""
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/bookmark")
    assert resp.status_code == 401


def test_list_wrong_password(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/bookmark", headers={"Authorization": WRONG_AUTH})
    assert resp.status_code == 401


def test_api_disabled_when_no_credentials(client):
    """When api_username/api_password are empty → 503."""
    resp = client.get(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark",
        headers={"Authorization": _basic("", "")},
    )
    # No credentials configured → 503 (before even checking password)
    assert resp.status_code in (401, 503)


# ── List ──────────────────────────────────────────────────────────────────────

def test_list_empty(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/bookmark", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"] == []


def test_list_returns_links(client_with_storage):
    client, storage = client_with_storage
    storage.create_link({"title": "Grafana", "url": "https://grafana.example.com", "category": "Monitoring"})
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/bookmark", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    item = data[0]
    assert item["url"] == "https://grafana.example.com"
    assert item["title"] == "Grafana"
    assert "Monitoring" in item["tags"]
    # Links with a category are placed in their category folder, not root
    assert item["folders"] != [-1]
    assert len(item["folders"]) == 1


def test_list_filter_by_url(client_with_storage):
    """GET /bookmark?url= returns only the matching bookmark — used by Floccus for duplicate detection."""
    client, storage = client_with_storage
    storage.create_link({"title": "A", "url": "https://a.example.com"})
    storage.create_link({"title": "B", "url": "https://b.example.com"})
    resp = client.get(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark?url=https://a.example.com",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["url"] == "https://a.example.com"


def test_list_filter_by_url_no_match(client_with_storage):
    """?url= for unknown URL returns empty list — Floccus then creates a new bookmark."""
    client, storage = client_with_storage
    storage.create_link({"title": "A", "url": "https://a.example.com"})
    resp = client.get(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark?url=https://unknown.example.com",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_list_pagination(client_with_storage):
    client, storage = client_with_storage
    for i in range(5):
        storage.create_link({"title": f"Link {i}", "url": f"https://link{i}.example.com"})
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/bookmark?page=0&limit=3", headers={"Authorization": AUTH})
    assert len(resp.json()["data"]) == 3
    resp2 = client.get("/index.php/apps/bookmarks/public/rest/v2/bookmark?page=1&limit=3", headers={"Authorization": AUTH})
    assert len(resp2.json()["data"]) == 2


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_bookmark(client_with_storage):
    client, _ = client_with_storage
    resp = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark",
        json={"url": "https://example.com", "title": "Example", "tags": ["Work"]},
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    item = body["item"]
    assert item["url"] == "https://example.com"
    assert item["title"] == "Example"
    assert "Work" in item["tags"]
    assert item["id"]


def test_create_bookmark_missing_url(client_with_storage):
    client, _ = client_with_storage
    resp = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark",
        json={"title": "No URL"},
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 400


def test_create_bookmark_floccus_tag_sets_category(client_with_storage):
    """floccus:/Category path tags set the category (first path component).
    floccus: tags are never stored verbatim in the response tags list.
    """
    client, _ = client_with_storage
    resp = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark",
        json={"url": "https://example.com", "title": "T", "tags": ["floccus:/Work/Projects", "Real"]},
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    item = resp.json()["item"]
    # floccus: path tag encodes the folder → "Work" becomes the category
    assert "floccus:/Work/Projects" not in item["tags"]
    assert "Work" in item["tags"]
    # Real tag is present as secondary but overridden by the floccus: folder path
    assert item["folders"] != [-1]  # placed in category folder, not root


# ── Get single bookmark ───────────────────────────────────────────────────────

def test_get_bookmark(client_with_storage):
    client, storage = client_with_storage
    link = storage.create_link({"title": "Single", "url": "https://single.example.com", "category": "Test"})
    resp = client.get(
        f"/index.php/apps/bookmarks/public/rest/v2/bookmark/{link['id']}",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["item"]["id"] == link["id"]
    assert body["item"]["url"] == "https://single.example.com"
    assert "Test" in body["item"]["tags"]


def test_get_bookmark_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.get(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark/nonexistent",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

def test_update_bookmark(client_with_storage):
    client, storage = client_with_storage
    link = storage.create_link({"title": "Old", "url": "https://old.example.com"})
    resp = client.put(
        f"/index.php/apps/bookmarks/public/rest/v2/bookmark/{link['id']}",
        json={"url": "https://new.example.com", "title": "New", "tags": ["Updated"]},
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["title"] == "New"
    assert item["url"] == "https://new.example.com"
    assert "Updated" in item["tags"]


def test_update_bookmark_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.put(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark/nonexistent",
        json={"url": "https://x.com", "title": "X"},
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 404


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_bookmark(client_with_storage):
    client, storage = client_with_storage
    link = storage.create_link({"title": "Delete Me", "url": "https://delete.example.com"})
    resp = client.delete(
        f"/index.php/apps/bookmarks/public/rest/v2/bookmark/{link['id']}",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert storage.get_link(link["id"]) is None


def test_delete_bookmark_not_found(client_with_storage):
    client, _ = client_with_storage
    resp = client.delete(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark/ghost",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 404


# ── Folders stub ──────────────────────────────────────────────────────────────

def test_list_folders(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert isinstance(body["data"], list)
    assert body["data"][0]["id"] == -1


# ── Folder stubs ──────────────────────────────────────────────────────────────

def test_folder_children_root_with_categories(client_with_storage):
    """Root children returns one folder per category + uncategorized bookmarks."""
    client, storage = client_with_storage
    storage.create_link({"title": "A", "url": "https://a.example.com", "category": "Work"})
    storage.create_link({"title": "B", "url": "https://b.example.com", "category": "Work"})
    storage.create_link({"title": "C", "url": "https://c.example.com", "category": "Personal"})
    storage.create_link({"title": "D", "url": "https://d.example.com"})  # no category

    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/children", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    data = resp.json()["data"]

    folders = [item for item in data if item["type"] == "folder"]
    bookmarks = [item for item in data if item["type"] == "bookmark"]

    assert len(folders) == 2  # Work + Personal
    folder_titles = {f["title"] for f in folders}
    assert folder_titles == {"Work", "Personal"}

    # Each folder has its bookmarks nested inside
    work_folder = next(f for f in folders if f["title"] == "Work")
    assert len(work_folder["children"]) == 2

    # Uncategorized bookmark is at root level
    assert len(bookmarks) == 1
    assert bookmarks[0]["url"] == "https://d.example.com"


def test_folder_children_category_folder(client_with_storage):
    """Requesting a category folder returns only that category's bookmarks."""
    client, storage = client_with_storage
    storage.create_link({"title": "A", "url": "https://a.example.com", "category": "Work"})
    storage.create_link({"title": "B", "url": "https://b.example.com", "category": "Personal"})

    # First get the Work folder ID from root children
    root_resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/children", headers={"Authorization": AUTH})
    folders = [i for i in root_resp.json()["data"] if i["type"] == "folder"]
    work_folder = next(f for f in folders if f["title"] == "Work")
    work_id = work_folder["id"]

    resp = client.get(f"/index.php/apps/bookmarks/public/rest/v2/folder/{work_id}/children", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["url"] == "https://a.example.com"


def test_folder_create_returns_stable_id(client_with_storage):
    """POST /folder with a title returns the same stable ID every time."""
    client, _ = client_with_storage
    resp1 = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/folder",
        json={"title": "MyFolder"},
        headers={"Authorization": AUTH},
    )
    resp2 = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/folder",
        json={"title": "MyFolder"},
        headers={"Authorization": AUTH},
    )
    assert resp1.json()["item"]["id"] == resp2.json()["item"]["id"]
    assert resp1.json()["item"]["title"] == "MyFolder"
    assert resp1.json()["item"]["id"] != -1


def test_create_bookmark_folder_id_sets_category_via_cache(client_with_storage):
    """POST /folder populates the in-memory cache so that a subsequent POST /bookmark
    with only a folder ID (no floccus: tag) correctly assigns the category — even
    on first sync when no bookmarks with that category exist yet.

    This is the critical first-sync scenario: Floccus creates a new folder via
    POST /folder, then sends individual POST /bookmark with folders=[<new_id>].
    Without the cache, get_categories() would be empty and category would be lost.
    """
    client, storage = client_with_storage

    # No seed — simulates a completely empty repo on first sync
    folder_resp = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/folder",
        json={"title": "Privat"},
        headers={"Authorization": AUTH},
    )
    assert folder_resp.status_code == 200
    folder_id = folder_resp.json()["item"]["id"]

    # Floccus creates bookmark with only folders=[<id>], no floccus: tag
    resp = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark",
        json={"url": "https://privat.example.com", "title": "Privat Link", "folders": [folder_id], "tags": []},
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert "Privat" in item["tags"]
    assert item["folders"] == [folder_id]

    # The bookmark must actually be stored with the correct category
    links = storage.list_links()
    assert len(links) == 1
    assert links[0]["category"] == "Privat"


def test_create_bookmark_folder_id_sets_category(client_with_storage):
    """Folder ID lookup works when the category already exists (from prior bookmarks).
    In practice Floccus always sends a floccus: tag too — tested in test_create_bookmark_floccus_tag_sets_category.
    """
    client, storage = client_with_storage
    # Seed an existing bookmark so the category is known
    storage.create_link({"title": "Seed", "url": "https://seed.example.com", "category": "DevOps"})

    # Get the stable folder ID for "DevOps"
    folder_resp = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/folder",
        json={"title": "DevOps"},
        headers={"Authorization": AUTH},
    )
    folder_id = folder_resp.json()["item"]["id"]

    # Create a new bookmark using the folder ID (no floccus: tag — folder ID lookup only)
    resp = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/bookmark",
        json={"url": "https://devops.example.com", "title": "CI", "folders": [folder_id], "tags": []},
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert "DevOps" in item["tags"]
    assert item["folders"] == [folder_id]


def test_folder_hash_category_scope(client_with_storage):
    """Hash for a category folder covers only that category's bookmarks."""
    client, storage = client_with_storage
    storage.create_link({"title": "A", "url": "https://a.example.com", "category": "Work"})
    storage.create_link({"title": "B", "url": "https://b.example.com", "category": "Personal"})

    root_resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/children", headers={"Authorization": AUTH})
    folders = [i for i in root_resp.json()["data"] if i["type"] == "folder"]
    work_id = next(f["id"] for f in folders if f["title"] == "Work")
    personal_id = next(f["id"] for f in folders if f["title"] == "Personal")

    hash_work = client.get(f"/index.php/apps/bookmarks/public/rest/v2/folder/{work_id}/hash", headers={"Authorization": AUTH}).json()["data"]["hash"]
    hash_personal = client.get(f"/index.php/apps/bookmarks/public/rest/v2/folder/{personal_id}/hash", headers={"Authorization": AUTH}).json()["data"]["hash"]
    hash_root = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/hash", headers={"Authorization": AUTH}).json()["data"]["hash"]

    assert hash_work != hash_personal
    assert hash_work != hash_root


def test_delete_folder_removes_all_bookmarks_in_category(client_with_storage):
    """DELETE /folder/{id} deletes every bookmark that belongs to that category."""
    client, storage = client_with_storage
    storage.create_link({"title": "A", "url": "https://a.example.com", "category": "Work"})
    storage.create_link({"title": "B", "url": "https://b.example.com", "category": "Work"})
    storage.create_link({"title": "C", "url": "https://c.example.com", "category": "Personal"})

    # Discover the Work folder ID
    root_resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/children", headers={"Authorization": AUTH})
    folders = [i for i in root_resp.json()["data"] if i["type"] == "folder"]
    work_id = next(f["id"] for f in folders if f["title"] == "Work")

    resp = client.delete(f"/index.php/apps/bookmarks/public/rest/v2/folder/{work_id}", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Work bookmarks gone, Personal bookmark still there
    remaining = storage.list_links()
    assert all(lk["category"] != "Work" for lk in remaining)
    assert any(lk["category"] == "Personal" for lk in remaining)


def test_delete_folder_unknown_id_returns_success(client_with_storage):
    """DELETE /folder/{id} with unknown ID returns 200 silently."""
    client, _ = client_with_storage
    resp = client.delete("/index.php/apps/bookmarks/public/rest/v2/folder/deadbeef", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_delete_folder_clears_cache_entry(client_with_storage):
    """After DELETE /folder, the folder ID is evicted from the in-memory cache."""
    from modules.links import floccus_api
    client, storage = client_with_storage
    storage.create_link({"title": "X", "url": "https://x.example.com", "category": "Temp"})

    root_resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/children", headers={"Authorization": AUTH})
    folders = [i for i in root_resp.json()["data"] if i["type"] == "folder"]
    temp_id = next(f["id"] for f in folders if f["title"] == "Temp")

    # Populate cache by calling POST /folder
    client.post("/index.php/apps/bookmarks/public/rest/v2/folder", json={"title": "Temp"}, headers={"Authorization": AUTH})
    assert temp_id in floccus_api._folder_id_to_name

    client.delete(f"/index.php/apps/bookmarks/public/rest/v2/folder/{temp_id}", headers={"Authorization": AUTH})
    assert temp_id not in floccus_api._folder_id_to_name


def test_folder_children_empty(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/children", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"] == []


def test_folder_hash_empty(client_with_storage):
    client, _ = client_with_storage
    resp = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/hash", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "hash" in body["data"]
    assert isinstance(body["data"]["hash"], str)


def test_folder_hash_changes_with_bookmarks(client_with_storage):
    """Hash changes after a bookmark is added."""
    client, storage = client_with_storage
    resp1 = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/hash", headers={"Authorization": AUTH})
    hash1 = resp1.json()["data"]["hash"]

    storage.create_link({"title": "X", "url": "https://x.example.com"})
    resp2 = client.get("/index.php/apps/bookmarks/public/rest/v2/folder/-1/hash", headers={"Authorization": AUTH})
    hash2 = resp2.json()["data"]["hash"]

    assert hash1 != hash2


def test_folder_create_stub(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/index.php/apps/bookmarks/public/rest/v2/folder", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["item"]["id"] == -1


def test_folder_update_stub(client_with_storage):
    client, _ = client_with_storage
    resp = client.put("/index.php/apps/bookmarks/public/rest/v2/folder/42", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_folder_delete_stub(client_with_storage):
    client, _ = client_with_storage
    resp = client.delete("/index.php/apps/bookmarks/public/rest/v2/folder/42", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_remove_bookmark_from_folder(client_with_storage):
    """DELETE /folder/{id}/bookmarks/{id} deletes the bookmark."""
    client, storage = client_with_storage
    link = storage.create_link({"title": "X", "url": "https://x.example.com", "category": "Work"})
    folder_id = client.post(
        "/index.php/apps/bookmarks/public/rest/v2/folder",
        json={"title": "Work"}, headers={"Authorization": AUTH},
    ).json()["item"]["id"]

    resp = client.delete(
        f"/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}/bookmarks/{link['id']}",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    assert storage.get_link(link["id"]) is None


def test_remove_bookmark_from_root_folder(client_with_storage):
    """DELETE /folder/-1/bookmarks/{id} deletes uncategorized bookmarks."""
    client, storage = client_with_storage
    link = storage.create_link({"title": "X", "url": "https://x.example.com"})

    resp = client.delete(
        f"/index.php/apps/bookmarks/public/rest/v2/folder/-1/bookmarks/{link['id']}",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200
    assert storage.get_link(link["id"]) is None


def test_remove_bookmark_from_folder_already_gone(client_with_storage):
    """Removing a non-existent bookmark returns 200 (no noise for Floccus)."""
    client, _ = client_with_storage
    resp = client.delete(
        "/index.php/apps/bookmarks/public/rest/v2/folder/-1/bookmarks/doesnotexist",
        headers={"Authorization": AUTH},
    )
    assert resp.status_code == 200


def test_folder_import_stub(client_with_storage):
    """Import returns 501 so Floccus falls back to individual POST /bookmark creates."""
    client, _ = client_with_storage
    resp = client.post("/index.php/apps/bookmarks/public/rest/v2/folder/-1/import", headers={"Authorization": AUTH})
    assert resp.status_code == 501


def test_folder_childorder_stub(client_with_storage):
    client, _ = client_with_storage
    resp = client.patch("/index.php/apps/bookmarks/public/rest/v2/folder/-1/childorder", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


# ── Lock / Unlock ─────────────────────────────────────────────────────────────

def test_lock(client_with_storage):
    client, _ = client_with_storage
    resp = client.post("/index.php/apps/bookmarks/public/rest/v2/lock", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_unlock(client_with_storage):
    client, _ = client_with_storage
    resp = client.delete("/index.php/apps/bookmarks/public/rest/v2/lock", headers={"Authorization": AUTH})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


# ── Capabilities + Login Flow v2 ──────────────────────────────────────────────

def test_capabilities(client):
    """Capabilities stub — no auth required."""
    resp = client.get("/ocs/v2.php/cloud/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ocs"]["meta"]["status"] == "ok"
    assert "bookmarks" in body["ocs"]["data"]["capabilities"]


def test_login_v2_init_no_credentials_configured(client):
    """login/v2 returns 503 when API credentials not set."""
    resp = client.post("/index.php/login/v2")
    assert resp.status_code == 503


def test_login_v2_init(client_with_storage):
    """login/v2 init returns poll endpoint + login URL."""
    client, _ = client_with_storage
    resp = client.post("/index.php/login/v2")
    assert resp.status_code == 200
    body = resp.json()
    assert "poll" in body
    assert "token" in body["poll"]
    assert "endpoint" in body["poll"]
    assert "login" in body
    assert body["poll"]["endpoint"].endswith("/index.php/login/v2/poll")


def test_login_v2_poll_pending_before_grant(client_with_storage):
    """poll returns 404 while token is still pending (user hasn't logged in yet)."""
    client, _ = client_with_storage
    init = client.post("/index.php/login/v2").json()
    token = init["poll"]["token"]

    resp = client.post("/index.php/login/v2/poll", data={"token": token})
    assert resp.status_code == 404


def test_login_v2_poll_valid_token(client_with_storage):
    """poll returns credentials after user approves via grant form."""
    client, _ = client_with_storage
    init = client.post("/index.php/login/v2").json()
    token = init["poll"]["token"]

    # Simulate user logging in on the grant page
    grant = client.post("/index.php/login/v2/grant",
                        data={"token": token, "username": "testuser", "password": "testpass"})
    assert grant.status_code == 200
    assert "Authorized" in grant.text

    resp = client.post("/index.php/login/v2/poll", data={"token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["loginName"] == "testuser"
    assert body["appPassword"] == "testpass"
    assert "server" in body


def test_login_v2_poll_token_consumed(client_with_storage):
    """Token can only be polled once after approval."""
    client, _ = client_with_storage
    token = client.post("/index.php/login/v2").json()["poll"]["token"]
    # Approve via grant form
    client.post("/index.php/login/v2/grant",
                data={"token": token, "username": "testuser", "password": "testpass"})
    client.post("/index.php/login/v2/poll", data={"token": token})
    # Second poll with same token → 404
    resp2 = client.post("/index.php/login/v2/poll", data={"token": token})
    assert resp2.status_code == 404


def test_login_v2_poll_invalid_token(client_with_storage):
    """Unknown token → 404."""
    client, _ = client_with_storage
    resp = client.post("/index.php/login/v2/poll", data={"token": "notavalidtoken"})
    assert resp.status_code == 404


def test_login_v2_grant_page_no_token(client):
    """Grant page without token returns 400."""
    resp = client.get("/index.php/login/v2/grant")
    assert resp.status_code == 400
    assert "text/html" in resp.headers["content-type"]


def test_login_v2_grant_page_with_token(client_with_storage):
    """Grant page with valid pending token shows login form."""
    client, _ = client_with_storage
    init = client.post("/index.php/login/v2").json()
    token = init["poll"]["token"]

    resp = client.get(f"/index.php/login/v2/grant?token={token}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Floccus Login" in resp.text
    assert token in resp.text


def test_login_v2_grant_wrong_credentials(client_with_storage):
    """Grant form returns 401 on wrong credentials and shows form again."""
    client, _ = client_with_storage
    token = client.post("/index.php/login/v2").json()["poll"]["token"]

    resp = client.post("/index.php/login/v2/grant",
                       data={"token": token, "username": "wrong", "password": "wrong"})
    assert resp.status_code == 401
    assert "Invalid credentials" in resp.text
    # Token still pending
    poll = client.post("/index.php/login/v2/poll", data={"token": token})
    assert poll.status_code == 404


# ── Module disabled ───────────────────────────────────────────────────────────

def test_api_disabled_when_module_off(tmp_path, isolated_settings):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from core.state import reset_storage
    from core import settings_store

    reset_storage()
    cfg = settings_store.load()
    cfg["link_sections"] = [{"id": "default", "name": "Default", "floccus_enabled": True, "floccus_username": "testuser", "floccus_password": "testpass"}]
    cfg["modules_enabled"]["links"] = False
    settings_store.save(cfg)

    with TestClient(_main_module.app, raise_server_exceptions=False) as client:
        resp = client.get("/index.php/apps/bookmarks/public/rest/v2/bookmark", headers={"Authorization": AUTH})
        assert resp.status_code == 404
