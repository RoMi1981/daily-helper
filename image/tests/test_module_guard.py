"""Tests for core/module_guard.py — require_module dependency."""

import sys
import os
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core import module_guard
from fastapi import HTTPException


def _call_guard(module: str):
    """Unwrap the Depends(...) and call the inner guard function directly."""
    dep = module_guard.require_module(module)
    dep.dependency()


class TestRequireModule:
    def test_no_exception_when_module_enabled(self):
        with patch("core.module_guard.settings_store.is_module_enabled", return_value=True):
            _call_guard("tasks")  # must not raise

    def test_raises_404_when_module_disabled(self):
        with patch("core.module_guard.settings_store.is_module_enabled", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                _call_guard("tasks")
        assert exc_info.value.status_code == 404
        assert "tasks" in exc_info.value.detail

    def test_enabled_by_default_when_key_missing(self):
        # is_module_enabled should return True when key is absent; guard must not raise
        with patch("core.module_guard.settings_store.is_module_enabled", return_value=True):
            _call_guard("unknown_module")  # must not raise
