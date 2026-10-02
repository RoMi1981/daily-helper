"""Platform-specific permission checker for git repositories."""

import json
import logging
import os
import re
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core.net_guard import assert_http_or_https

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate the scheme on every redirect hop.

    urlopen() follows redirects on its own by default with no revalidation,
    which would let a compromised git host 302 the request to e.g. a file://
    URL after the initial check passed.

    Deliberately only a scheme check (assert_http_or_https), NOT the full
    no-private-address check: a self-hosted Gitea/GitLab on a private LAN
    address is the normal deployment for this app, and the repo URL is
    entered by the operator in Settings, not supplied by an untrusted party.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_http_or_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def detect_platform(url: str) -> str:
    """Detect git platform from URL. Returns 'github', 'gitlab', or 'gitea'."""
    if "github.com" in url:
        return "github"
    if "gitlab.com" in url:
        return "gitlab"
    return "gitea"


def _parse_owner_repo(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from SSH or HTTPS git URL."""
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    m = re.search(r"[:/]([^/:]+)/([^/]+)$", url)
    if m:
        return m.group(1), m.group(2)
    return None


def _api_base(url: str, platform: str) -> str | None:
    """Derive API base URL from repo URL."""
    if platform == "github":
        return "https://api.github.com"
    if platform == "gitlab":
        m = re.match(r"(https?://[^/]+)", url)
        return (m.group(1) + "/api/v4") if m else None
    # Gitea: HTTPS or ssh://
    m = re.match(r"https?://([^/]+)", url)
    if m:
        return f"https://{m.group(1)}/api/v1"
    m = re.match(r"ssh://[^@]+@([^:/]+)", url)
    if m:
        return f"https://{m.group(1)}/api/v1"
    # SCP-style: git@host:owner/repo
    m = re.match(r"[^@]+@([^:]+):", url)
    if m:
        return f"https://{m.group(1)}/api/v1"
    return None


def check_permissions(url: str, platform: str, pat: str = "", ca_cert: str = "") -> dict:
    """
    Check repo permissions via platform REST API using PAT.
    Returns {"read": bool, "write": bool, "error": str | None}
    ca_cert: PEM string for custom/self-signed CA (optional).
    """
    result: dict = {"read": False, "write": False, "error": None}

    parsed = _parse_owner_repo(url)
    if not parsed:
        result["error"] = "Could not parse owner/repo from URL"
        return result

    owner, repo = parsed
    api_base = _api_base(url, platform)
    if not api_base:
        result["error"] = "Could not determine API base URL"
        return result

    headers: dict[str, str] = {"Accept": "application/json"}
    if pat:
        if platform == "github":
            headers["Authorization"] = f"Bearer {pat}"
        elif platform == "gitlab":
            headers["PRIVATE-TOKEN"] = pat
        else:
            headers["Authorization"] = f"token {pat}"

    # Build SSL context with custom CA cert if provided
    ssl_ctx = None
    _ca_tmp = None
    if ca_cert and ca_cert.strip():
        try:
            ssl_ctx = ssl.create_default_context()
            run_dir = DATA_DIR / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            _ca_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w", dir=run_dir)
            _ca_tmp.write(ca_cert.strip())
            _ca_tmp.flush()
            _ca_tmp.close()
            ssl_ctx.load_verify_locations(_ca_tmp.name)
        except Exception:
            ssl_ctx = None

    try:
        if platform == "gitlab":
            encoded = urllib.parse.quote(f"{owner}/{repo}", safe="")
            api_url = f"{api_base}/projects/{encoded}"
        else:
            api_url = f"{api_base}/repos/{owner}/{repo}"

        # Scheme check only — a private/LAN git host is the expected case here
        # (see _SafeRedirectHandler for why the public-address check is wrong).
        assert_http_or_https(api_url)
        req = urllib.request.Request(api_url, headers=headers)
        opener = urllib.request.build_opener(_SafeRedirectHandler(), urllib.request.HTTPSHandler(context=ssl_ctx))
        with opener.open(req, timeout=10) as resp:
            data = json.loads(resp.read())

        result["read"] = True

        if platform in ("gitea", "github"):
            perms = data.get("permissions", {})
            result["write"] = bool(perms.get("push", False))
        elif platform == "gitlab":
            perms = data.get("permissions", {})
            project = (perms.get("project_access") or {}).get("access_level", 0)
            group = (perms.get("group_access") or {}).get("access_level", 0)
            result["write"] = max(project, group) >= 30  # Developer+

    except urllib.error.HTTPError as e:
        if e.code == 401:
            result["error"] = "Unauthorized — check your PAT"
        elif e.code == 404:
            result["error"] = "Repository not found"
        else:
            result["error"] = f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        result["error"] = str(e)
    finally:
        if _ca_tmp:
            try:
                import os as _os

                _os.unlink(_ca_tmp.name)
            except Exception as e:
                logger.warning("Failed to remove temp CA cert file %s: %s", _ca_tmp.name, e)

    return result
