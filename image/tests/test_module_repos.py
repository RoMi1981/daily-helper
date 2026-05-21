"""Tests for core/module_repos.py — store resolution per module."""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core import module_repos


def _make_storage(store_ids: list[str], cfg_repos: list[dict] | None = None) -> MagicMock:
    storage = MagicMock()
    storage._stores = {rid: MagicMock(name=f"store-{rid}") for rid in store_ids}
    storage._cfg = {"repos": cfg_repos or [{"id": rid} for rid in store_ids]}
    return storage


class TestGetModuleStores:
    def test_returns_all_stores_when_no_assignment(self):
        storage = _make_storage(["r1", "r2"])
        with patch("core.module_repos._assigned_ids", return_value=[]):
            result = module_repos.get_module_stores("tasks", storage)
        assert set(result) == set(storage._stores.values())

    def test_returns_only_assigned_stores(self):
        storage = _make_storage(["r1", "r2", "r3"])
        with patch("core.module_repos._assigned_ids", return_value=["r1", "r3"]):
            result = module_repos.get_module_stores("tasks", storage)
        assert result == [storage._stores["r1"], storage._stores["r3"]]

    def test_returns_empty_when_assigned_repo_does_not_exist(self):
        storage = _make_storage(["r1"])
        with patch("core.module_repos._assigned_ids", return_value=["r99"]):
            result = module_repos.get_module_stores("tasks", storage)
        assert result == []

    def test_returns_empty_when_no_storage(self):
        result = module_repos.get_module_stores("tasks", None)
        assert result == []


class TestGetPrimaryStore:
    def test_returns_explicit_primary(self):
        storage = _make_storage(["r1", "r2"], [
            {"id": "r1", "permissions": {"write": True}},
            {"id": "r2", "permissions": {"write": True}},
        ])
        with patch("core.module_repos._assigned_ids", return_value=["r1", "r2"]), \
             patch("core.module_repos._primary_id", return_value="r2"):
            result = module_repos.get_primary_store("tasks", storage)
        assert result is storage._stores["r2"]

    def test_falls_back_to_first_writable(self):
        storage = _make_storage(["r1", "r2"], [
            {"id": "r1", "permissions": {"write": False}},
            {"id": "r2", "permissions": {"write": True}},
        ])
        with patch("core.module_repos._assigned_ids", return_value=["r1", "r2"]), \
             patch("core.module_repos._primary_id", return_value=""):
            result = module_repos.get_primary_store("tasks", storage)
        assert result is storage._stores["r2"]

    def test_falls_back_to_first_assigned_when_no_writable(self):
        storage = _make_storage(["r1", "r2"], [
            {"id": "r1", "permissions": {"write": False}},
            {"id": "r2", "permissions": {"write": False}},
        ])
        with patch("core.module_repos._assigned_ids", return_value=["r1", "r2"]), \
             patch("core.module_repos._primary_id", return_value=""):
            result = module_repos.get_primary_store("tasks", storage)
        assert result is storage._stores["r1"]

    def test_returns_none_when_no_storage(self):
        result = module_repos.get_primary_store("tasks", None)
        assert result is None


class TestGetModuleRepoList:
    def test_returns_repo_metadata_with_names(self):
        storage = _make_storage(["r1", "r2"], [
            {"id": "r1", "name": "Primary Repo"},
            {"id": "r2", "name": "Secondary Repo"},
        ])
        with patch("core.module_repos._assigned_ids", return_value=["r1", "r2"]):
            result = module_repos.get_module_repo_list("tasks", storage)
        assert result == [
            {"id": "r1", "name": "Primary Repo"},
            {"id": "r2", "name": "Secondary Repo"},
        ]

    def test_uses_id_as_name_fallback(self):
        storage = _make_storage(["r1"], [{"id": "r1"}])
        with patch("core.module_repos._assigned_ids", return_value=["r1"]):
            result = module_repos.get_module_repo_list("tasks", storage)
        assert result == [{"id": "r1", "name": "r1"}]

    def test_returns_empty_when_no_storage(self):
        result = module_repos.get_module_repo_list("tasks", None)
        assert result == []
