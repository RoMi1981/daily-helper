"""Global storage state — shared singleton to avoid circular imports."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_storage = None


def get_storage():
    global _storage
    if _storage is None:
        from core import settings_store
        from core.storage import MultiRepoStorage

        cfg = settings_store.load()
        if cfg.get("repos"):
            try:
                _storage = MultiRepoStorage(cfg)
            except Exception as e:
                logger.error("Storage init failed: %s", e)
    return _storage


def reset_storage():
    global _storage
    if _storage is not None:
        try:
            _storage.cleanup()
        except Exception:
            pass
    _storage = None
