"""Tests for EolStorage."""

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


@pytest.fixture()
def storage(tmp_path):
    from modules.eol.storage import EolStorage
    return EolStorage(FakeGit(tmp_path))


# ── list_entries ───────────────────────────────────────────────────────────

def test_list_empty(storage):
    assert storage.list_entries() == []


def test_list_returns_entries(storage):
    storage.create_entry("Ubuntu", "22.04", "Ubuntu 22.04 LTS")
    storage.create_entry("Python", "3.9", "Python 3.9")
    entries = storage.list_entries()
    assert len(entries) == 2


def test_list_sorted_by_product_then_cycle(storage):
    storage.create_entry("Ubuntu", "22.04", "Ubuntu 22.04")
    storage.create_entry("Python", "3.9", "Python 3.9")
    storage.create_entry("Python", "3.8", "Python 3.8")
    entries = storage.list_entries()
    assert entries[0]["product"] == "Python"
    assert entries[0]["cycle"] == "3.8"
    assert entries[1]["product"] == "Python"
    assert entries[1]["cycle"] == "3.9"
    assert entries[2]["product"] == "Ubuntu"


def test_list_skips_invalid_yaml(storage, tmp_path):
    eol_dir = tmp_path / "eol"
    eol_dir.mkdir(parents=True, exist_ok=True)
    (eol_dir / "broken.yaml").write_text("- this is a list not a dict", encoding="utf-8")
    storage.create_entry("Valid", "1.0", "Valid 1.0")
    entries = storage.list_entries()
    assert len(entries) == 1
    assert entries[0]["product"] == "Valid"


# ── get_entry ──────────────────────────────────────────────────────────────

def test_get_entry(storage):
    e = storage.create_entry("Debian", "11", "Debian Bullseye")
    fetched = storage.get_entry(e["id"])
    assert fetched is not None
    assert fetched["product"] == "Debian"
    assert fetched["cycle"] == "11"
    assert fetched["label"] == "Debian Bullseye"


def test_get_entry_missing(storage):
    assert storage.get_entry("doesnotexist") is None


# ── create_entry ───────────────────────────────────────────────────────────

def test_create_entry_fields(storage):
    e = storage.create_entry("Node.js", "18", "Node.js 18 LTS", notes="LTS until 2025")
    assert e["product"] == "Node.js"
    assert e["cycle"] == "18"
    assert e["label"] == "Node.js 18 LTS"
    assert e["notes"] == "LTS until 2025"
    assert "id" in e
    assert "created" in e


def test_create_entry_default_notes(storage):
    e = storage.create_entry("Redis", "7", "Redis 7")
    assert e["notes"] == ""


def test_create_entry_writes_yaml_file(storage, tmp_path):
    e = storage.create_entry("MySQL", "8.0", "MySQL 8.0")
    yaml_path = tmp_path / "eol" / f"{e['id']}.yaml"
    assert yaml_path.exists()


def test_create_entry_commits(storage):
    storage.create_entry("Alpine", "3.18", "Alpine Linux 3.18")
    assert any("eol: track Alpine 3.18" in m for m in storage._git._committed)


# ── update_notes ───────────────────────────────────────────────────────────

def test_update_notes(storage):
    e = storage.create_entry("OpenSSL", "1.1", "OpenSSL 1.1")
    updated = storage.update_notes(e["id"], "  EOL Sep 2023  ")
    assert updated is not None
    assert updated["notes"] == "EOL Sep 2023"


def test_update_notes_only_changes_notes(storage):
    e = storage.create_entry("Nginx", "1.20", "Nginx 1.20", notes="old note")
    storage.update_notes(e["id"], "new note")
    fetched = storage.get_entry(e["id"])
    assert fetched["product"] == "Nginx"
    assert fetched["cycle"] == "1.20"
    assert fetched["label"] == "Nginx 1.20"
    assert fetched["notes"] == "new note"


def test_update_notes_missing_entry(storage):
    assert storage.update_notes("ghost", "some notes") is None


def test_update_notes_commits(storage):
    e = storage.create_entry("MariaDB", "10.6", "MariaDB 10.6")
    storage._git._committed.clear()
    storage.update_notes(e["id"], "updated")
    assert any("eol: update notes" in m for m in storage._git._committed)


# ── delete_entry ───────────────────────────────────────────────────────────

def test_delete_entry(storage):
    e = storage.create_entry("PHP", "7.4", "PHP 7.4")
    result = storage.delete_entry(e["id"])
    assert result is True
    assert storage.get_entry(e["id"]) is None


def test_delete_entry_removes_file(storage, tmp_path):
    e = storage.create_entry("Ruby", "2.7", "Ruby 2.7")
    yaml_path = tmp_path / "eol" / f"{e['id']}.yaml"
    assert yaml_path.exists()
    storage.delete_entry(e["id"])
    assert not yaml_path.exists()


def test_delete_entry_missing(storage):
    assert storage.delete_entry("doesnotexist") is False


def test_delete_entry_commits(storage):
    e = storage.create_entry("Go", "1.19", "Go 1.19")
    storage._git._committed.clear()
    storage.delete_entry(e["id"])
    assert any("eol: remove tracked entry" in m for m in storage._git._committed)


# ── is_tracked ─────────────────────────────────────────────────────────────

def test_is_tracked_true(storage):
    storage.create_entry("CentOS", "7", "CentOS 7")
    assert storage.is_tracked("CentOS", "7") is True


def test_is_tracked_false_wrong_cycle(storage):
    storage.create_entry("CentOS", "7", "CentOS 7")
    assert storage.is_tracked("CentOS", "8") is False


def test_is_tracked_false_wrong_product(storage):
    storage.create_entry("CentOS", "7", "CentOS 7")
    assert storage.is_tracked("RHEL", "7") is False


def test_is_tracked_false_empty(storage):
    assert storage.is_tracked("Anything", "1.0") is False
