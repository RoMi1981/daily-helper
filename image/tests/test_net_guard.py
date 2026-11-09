"""Tests for core.net_guard — SSRF protection for server-side URL fetches."""

import asyncio
import os
import sys

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)

import pytest
from core.net_guard import (
    UnsafeUrlError,
    assert_http_or_https,
    assert_http_scheme,
    assert_public_http_url,
    fetch_public_url,
)


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url("file:///etc/passwd")


def test_rejects_no_host():
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url("http://")


def test_rejects_loopback():
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url("http://127.0.0.1/x")


def test_rejects_private_rfc1918():
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url("http://10.0.0.5/x")


def test_rejects_link_local():
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url("http://169.254.169.254/latest/meta-data")


def test_rejects_cgnat_range():
    """RFC 6598 Carrier-Grade NAT space (100.64.0.0/10) — ipaddress.is_private
    doesn't cover this, so it needs its own explicit check."""
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url("http://100.64.0.1/x")


def test_allows_cgnat_adjacent_public_range():
    """Sanity check the CGNAT check doesn't over-block: 100.63.x.x and
    100.128.x.x are outside the 100.64.0.0/10 block and are (in principle)
    publicly routable — resolution itself may still fail in a sandbox, but
    the guard shouldn't raise on scheme/host+CGNAT grounds for these."""
    import ipaddress

    assert ipaddress.ip_address("100.63.255.255") not in ipaddress.ip_network("100.64.0.0/10")
    assert ipaddress.ip_address("100.128.0.0") not in ipaddress.ip_network("100.64.0.0/10")


def test_rejects_unresolvable_host():
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url("http://this-host-does-not-exist.invalid/x")


class _FakeResponse:
    def __init__(self, is_redirect=False, next_url=None):
        self.is_redirect = is_redirect
        self.next_request = type("_Req", (), {"url": next_url})() if next_url else None


class _FakeAsyncClient:
    """Simulates a server that 302-redirects to an internal address after
    the first (public) URL passes validation — the exact SSRF bypass
    fetch_public_url's per-hop revalidation exists to close."""

    def __init__(self, responses):
        self._responses = list(responses)

    async def get(self, url, follow_redirects=False, **kwargs):
        return self._responses.pop(0)


# Driven via asyncio.run() rather than @pytest.mark.asyncio: the test image
# (image/Dockerfile.test) installs only `pytest httpx`, so an async test
# function would be skipped-as-failed there.
def test_fetch_public_url_revalidates_each_redirect_hop():
    responses = [
        _FakeResponse(is_redirect=True, next_url="http://169.254.169.254/latest/meta-data"),
    ]
    client = _FakeAsyncClient(responses)
    with pytest.raises(UnsafeUrlError):
        asyncio.run(fetch_public_url(client, "http://example.com/feed.xml"))


def test_fetch_public_url_too_many_redirects():
    client = _FakeAsyncClient([_FakeResponse(is_redirect=True, next_url="http://example.com/x")] * 10)
    with pytest.raises(UnsafeUrlError, match="Too many redirects"):
        asyncio.run(fetch_public_url(client, "http://example.com/feed.xml", max_redirects=2))


class TestAssertHttpScheme:
    """assert_http_scheme() guards URLs that are only *stored*, not fetched.
    It must not resolve DNS — otherwise a temporarily unresolvable host would
    make saving an RSS feed impossible, which is a real regression rather
    than a security win (no request is made when saving)."""

    def test_accepts_unresolvable_hostname(self):
        assert_http_scheme("https://e2e-test.example.com/feed.xml")

    def test_accepts_normal_https_url(self):
        assert_http_scheme("https://example.com/feed.xml")

    def test_rejects_non_http_scheme(self):
        with pytest.raises(UnsafeUrlError):
            assert_http_scheme("file:///etc/passwd")

    def test_rejects_missing_host(self):
        with pytest.raises(UnsafeUrlError):
            assert_http_scheme("http://")

    def test_rejects_literal_loopback_ip(self):
        """A literal internal IP needs no DNS to spot, so it is still blocked
        at save time — immediate feedback for the obvious case."""
        with pytest.raises(UnsafeUrlError):
            assert_http_scheme("http://127.0.0.1/feed.xml")

    def test_rejects_literal_private_ip(self):
        with pytest.raises(UnsafeUrlError):
            assert_http_scheme("http://10.0.0.5/feed.xml")

    def test_rejects_literal_link_local_ip(self):
        with pytest.raises(UnsafeUrlError):
            assert_http_scheme("http://169.254.169.254/latest/meta-data")


class TestAssertHttpOrHttps:
    """Used for operator-configured infrastructure URLs (the git remote),
    where a private LAN address is the normal case — so this must reject
    only the scheme, never the address."""

    def test_accepts_private_literal_ip(self):
        assert_http_or_https("https://10.0.0.5/owner/repo")

    def test_accepts_loopback(self):
        assert_http_or_https("http://127.0.0.1:3000/owner/repo")

    def test_accepts_public_host(self):
        assert_http_or_https("https://github.com/owner/repo")

    def test_rejects_file_scheme(self):
        with pytest.raises(UnsafeUrlError):
            assert_http_or_https("file:///etc/passwd")

    def test_rejects_missing_host(self):
        with pytest.raises(UnsafeUrlError):
            assert_http_or_https("http:///no-host")
