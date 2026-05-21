"""Dependency for guarding disabled modules."""

from fastapi import Depends, HTTPException
from core import settings_store


def require_module(module: str):
    """Return a FastAPI dependency that raises 404 if the module is disabled."""
    def guard():
        if not settings_store.is_module_enabled(module):
            raise HTTPException(status_code=404, detail=f"Module '{module}' is disabled")
    return Depends(guard)
