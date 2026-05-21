"""Tests for core/state.py — global storage singleton lifecycle."""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core import state


def _reset_state():
    state._storage = None


class TestGetStorage:
    def setup_method(self):
        _reset_state()

    def test_returns_none_when_no_repos_configured(self):
        with patch("core.settings_store.load", return_value={"repos": []}):
            result = state.get_storage()
        assert result is None

    def test_returns_none_when_repos_key_missing(self):
        with patch("core.settings_store.load", return_value={}):
            result = state.get_storage()
        assert result is None

    def test_returns_multirepo_storage_when_repos_configured(self):
        mock_storage = MagicMock()
        cfg = {"repos": [{"id": "r1", "enabled": True}]}
        with patch("core.settings_store.load", return_value=cfg), \
             patch("core.storage.MultiRepoStorage", return_value=mock_storage) as MockClass:
            result = state.get_storage()
        MockClass.assert_called_once_with(cfg)
        assert result is mock_storage

    def test_returns_cached_instance_on_second_call(self):
        mock_storage = MagicMock()
        cfg = {"repos": [{"id": "r1"}]}
        with patch("core.settings_store.load", return_value=cfg), \
             patch("core.storage.MultiRepoStorage", return_value=mock_storage) as MockClass:
            r1 = state.get_storage()
            r2 = state.get_storage()
        assert r1 is r2
        MockClass.assert_called_once()

    def test_returns_none_when_storage_init_raises(self):
        cfg = {"repos": [{"id": "r1"}]}
        with patch("core.settings_store.load", return_value=cfg), \
             patch("core.storage.MultiRepoStorage", side_effect=Exception("init failed")):
            result = state.get_storage()
        assert result is None


class TestResetStorage:
    def setup_method(self):
        _reset_state()

    def test_calls_cleanup_and_sets_storage_to_none(self):
        mock_storage = MagicMock()
        state._storage = mock_storage

        state.reset_storage()

        mock_storage.cleanup.assert_called_once()
        assert state._storage is None

    def test_reset_when_already_none_does_not_raise(self):
        state._storage = None
        state.reset_storage()  # must not raise
        assert state._storage is None

    def test_reset_ignores_cleanup_exception(self):
        mock_storage = MagicMock()
        mock_storage.cleanup.side_effect = Exception("cleanup failed")
        state._storage = mock_storage

        state.reset_storage()  # must not raise

        assert state._storage is None
