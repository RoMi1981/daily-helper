"""Tests for core.permission_checker — SSRF-guarded repo permission checks."""

import json
import os
import sys

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)

import urllib.request

import pytest
from core.net_guard import UnsafeUrlError
from core.permission_checker import (
    _parse_owner_repo,
    _SafeRedirectHandler,
    check_permissions,
    detect_platform,
)


class TestDetectPlatform:
    def test_github(self):
        assert detect_platform("https://github.com/owner/repo") == "github"

    def test_gitlab(self):
        assert detect_platform("https://gitlab.com/owner/repo") == "gitlab"

    def test_defaults_to_gitea(self):
        assert detect_platform("https://git.example.com/owner/repo") == "gitea"


class TestParseOwnerRepo:
    def test_https_url(self):
        assert _parse_owner_repo("https://github.com/owner/repo") == ("owner", "repo")

    def test_https_url_with_git_suffix(self):
        assert _parse_owner_repo("https://github.com/owner/repo.git") == ("owner", "repo")

    def test_ssh_url(self):
        assert _parse_owner_repo("git@github.com:owner/repo.git") == ("owner", "repo")

    def test_trailing_slash(self):
        assert _parse_owner_repo("https://github.com/owner/repo/") == ("owner", "repo")

    def test_unparseable_returns_none(self):
        assert _parse_owner_repo("not-a-url") is None


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


class TestCheckPermissionsUrlGuard:
    """The repo URL is entered by the operator in Settings and normally
    points at a self-hosted Gitea/GitLab on a private LAN address, so the
    guard here must only reject non-http schemes — never private targets.
    Blocking those broke "Check permissions" for every LAN-hosted repo."""

    def test_allows_private_lan_host(self, monkeypatch):
        def fake_open(self, req, timeout=None):
            return _FakeResponse({"permissions": {"push": True}})

        monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
        result = check_permissions("https://10.0.0.5/owner/repo", "gitea", pat="x")
        assert result["read"] is True
        assert result["error"] is None

    def test_allows_localhost(self, monkeypatch):
        def fake_open(self, req, timeout=None):
            return _FakeResponse({"permissions": {"push": False}})

        monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
        result = check_permissions("https://localhost/owner/repo", "gitea", pat="x")
        assert result["read"] is True
        assert result["write"] is False

    def test_allows_public_host(self, monkeypatch):
        def fake_open(self, req, timeout=None):
            return _FakeResponse({"permissions": {"push": True}})

        monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
        result = check_permissions("https://github.com/owner/repo", "github", pat="x")
        assert result["read"] is True
        assert result["write"] is True
        assert result["error"] is None


class TestSafeRedirectHandler:
    """urlopen() follows redirects on its own with no revalidation by
    default — _SafeRedirectHandler re-checks the scheme on every hop so a
    compromised git host cannot 302 the request to e.g. file://."""

    def test_allows_redirect_to_private_target(self):
        """A LAN git host redirecting within its own network is legitimate."""
        handler = _SafeRedirectHandler()
        req = urllib.request.Request("https://10.0.0.5/repos/owner/repo")
        result = handler.redirect_request(req, None, 302, "Found", {}, "https://10.0.0.5/api/v1/repos/owner/repo")
        assert result is not None

    def test_rejects_redirect_to_non_http_scheme(self):
        handler = _SafeRedirectHandler()
        req = urllib.request.Request("https://api.example.com/repos/owner/repo")
        with pytest.raises(UnsafeUrlError):
            handler.redirect_request(req, None, 302, "Found", {}, "file:///etc/passwd")
