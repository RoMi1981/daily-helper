"""Guard against SSRF when the app fetches user-supplied URLs server-side
(RSS feeds, meme/POTD "fetch from URL"): only allow http/https and reject
hostnames that resolve to private, loopback, or link-local addresses."""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class UnsafeUrlError(ValueError):
    pass


# RFC 6598 Carrier-Grade NAT space — ipaddress.is_private returns False for
# this range, so it needs an explicit check alongside the other blocklists.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.version == 4 and ip in _CGNAT)
    )


def assert_http_or_https(url: str) -> None:
    """Validate scheme and presence of a host — nothing else.

    For URLs pointing at infrastructure the operator configured themselves
    (the git remote in Settings), where a private/LAN address is the normal
    case and blocking it would break the app's primary deployment. Still
    rejects file://, gopher:// and friends, which is the part that matters
    when the URL is handed to urllib.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"URL scheme '{parsed.scheme}' not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no host")


def assert_http_scheme(url: str) -> None:
    """Validate a URL that is only being *stored*, not fetched.

    Checks the scheme and (if the host is a literal IP) the address, but
    deliberately does NOT resolve DNS: storing a feed URL performs no
    request, so a temporarily unresolvable host must not block saving it.
    The actual SSRF protection lives on the fetch path
    (assert_public_http_url / fetch_public_url), which is where a request
    is genuinely made.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"URL scheme '{parsed.scheme}' not allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL has no host")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # hostname, not a literal IP — resolved at fetch time instead
    if _is_blocked_ip(ip):
        raise UnsafeUrlError(f"URL points at a non-public address: {ip}")


async def fetch_public_url(client: httpx.AsyncClient, url: str, max_redirects: int = 5, **kwargs):
    """GET `url` re-validating against SSRF on every redirect hop, since
    validating only the initial URL wouldn't stop a malicious server from
    302-redirecting to an internal address after the check passed."""
    for _ in range(max_redirects + 1):
        assert_public_http_url(url)
        resp = await client.get(url, follow_redirects=False, **kwargs)
        if resp.is_redirect:
            url = str(resp.next_request.url)
            continue
        return resp
    raise UnsafeUrlError("Too many redirects")


# NOTE — accepted residual risk (not fixed here): assert_public_http_url()
# resolves the hostname once to validate it, then hands the *hostname* back
# to httpx/urllib, which re-resolve independently when actually connecting.
# A DNS-rebinding attacker (attacker-controlled DNS, TTL=0) could return a
# public IP for the validation lookup and a private one moments later for
# the real connection. Closing this fully requires pinning the validated IP
# for the actual socket connect (a custom transport/resolver), which adds
# real complexity and its own failure modes (SNI/Host-header handling) for
# a threat model where the attacker already needs the user to add the URL
# themselves (RSS feed / meme / POTD / repo URL) on a single-user internal
# tool. Documented instead of "fixed" per this project's simplicity-first
# convention — revisit if this app is ever exposed beyond a trusted network.
def assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"URL scheme '{parsed.scheme}' not allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeUrlError(f"Could not resolve host: {host}") from e
    for _family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_blocked_ip(ip):
            raise UnsafeUrlError(f"URL resolves to a non-public address: {ip}")
