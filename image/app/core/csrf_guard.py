"""Stateless CSRF mitigation via Origin/Referer header validation.

No session/login system exists in this app (auth is expected to be handled
by a reverse proxy in front of the container, see HANDOVER.md), so
session-tied CSRF tokens aren't applicable. Instead, reject cross-origin
state-changing requests by comparing the Origin (or Referer as fallback)
header against the request's own Host.
"""

from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _UNSAFE_METHODS:
            source = request.headers.get("origin") or request.headers.get("referer")
            if source:
                source_host = urlparse(source).netloc
                if source_host and source_host != request.headers.get("host", ""):
                    return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
        return await call_next(request)
