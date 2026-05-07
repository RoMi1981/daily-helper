"""Shared fixtures for Playwright E2E tests.

Uses the real daily-helper-data-e2e-test.git repo via SSH deploy key.
Tests are skipped automatically when the key is not available.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

# In Docker (WORKDIR /app, COPY app/ ./): main.py liegt direkt in /app
# Lokal (image/tests/e2e/): main.py liegt in image/app/
_tests_root = Path(__file__).parent.parent.parent
APP_DIR = str(_tests_root) if (_tests_root / "main.py").exists() else str(_tests_root / "app")


def _free_port() -> int:
    """Ask the OS for a free TCP port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


E2E_PORT = _free_port()
E2E_REPO_ID = "e2e-test-repo"
E2E_REPO_ID_2 = "e2e-test-repo-02"
TEST_REPO_URL = os.environ.get(
    "TEST_E2E_REPO_URL",
    "ssh://git@gitea.nas.trabs.net:2222/Tests/daily-helper-data-e2e-test.git",
)
TEST_REPO_URL_2 = os.environ.get(
    "TEST_E2E_REPO_URL_2",
    "ssh://git@gitea.nas.trabs.net:2222/Tests/daily-helper-data-e2e-test-02.git",
)
KEY_PATH = os.path.expanduser("~/.ssh/dh_test_deploy_key")
KEY_ENV_VAR = "TEST_DEPLOY_KEY_PRIVATE"


def _get_deploy_key() -> str | None:
    """Return deploy key content, writing from env var if needed.
    Always returns the file content (proper newlines), never raw env var.
    """
    if not os.path.exists(KEY_PATH):
        key_content = os.environ.get(KEY_ENV_VAR)
        if not key_content:
            return None
        os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
        with open(KEY_PATH, "w") as f:
            f.write(key_content.strip() + "\n")
        os.chmod(KEY_PATH, 0o600)
    return open(KEY_PATH).read()  # always read from file — guaranteed proper newlines


_deploy_key = _get_deploy_key()

pytestmark = pytest.mark.skipif(
    _deploy_key is None,
    reason="Deploy key not available (set TEST_DEPLOY_KEY_PRIVATE or place key at ~/.ssh/dh_test_deploy_key)",
)


def _ensure_known_hosts() -> None:
    """Pre-populate ~/.ssh/known_hosts so git clone doesn't fail on host verification."""
    from urllib.parse import urlparse

    parsed = urlparse(TEST_REPO_URL)
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 22)
    ssh_dir = Path(os.path.expanduser("~/.ssh"))
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    known_hosts = ssh_dir / "known_hosts"
    result = subprocess.run(
        ["ssh-keyscan", "-p", port, host],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode == 0 and result.stdout:
        with open(known_hosts, "a") as f:
            f.write(result.stdout)


@pytest.fixture(scope="session")
def app_data_dir(tmp_path_factory):
    """Write settings.json pointing to both real test repos."""
    _ensure_known_hosts()
    d = tmp_path_factory.mktemp("e2e-data")
    settings = {
        "repos": [
            {
                "id": E2E_REPO_ID,
                "name": "E2E Test Repo",
                "url": TEST_REPO_URL,
                "enabled": True,
                "auth_mode": "ssh",
                # Plaintext key — settings_store._decrypt() passes it through unchanged
                "ssh_key": _deploy_key or "",
                "permissions": {"read": True, "write": True},
            },
            {
                "id": E2E_REPO_ID_2,
                "name": "E2E Test Repo 02",
                "url": TEST_REPO_URL_2,
                "enabled": True,
                "auth_mode": "ssh",
                "ssh_key": _deploy_key or "",
                "permissions": {"read": True, "write": True},
            },
        ],
        "git_user_name": "E2E Test",
        "git_user_email": "e2e@test.local",
        "sprint_anchor_date": "2026-01-05",
        "sprint_duration_weeks": 3,
        "sprint_name_prefix": "E2E Sprint",
        "modules_enabled": {
            "knowledge": True,
            "tasks": True,
            "vacations": True,
            "notes": True,
            "links": True,
            "runbooks": True,
            "mail_templates": True,
            "ticket_templates": True,
            "appointments": True,
            "memes": True,
        },
    }
    (d / "settings.json").write_text(json.dumps(settings))
    return str(d)


@pytest.fixture(scope="session")
def live_server(app_data_dir):
    """Start the FastAPI app with uvicorn and wait until /health responds."""
    for repo_id in (E2E_REPO_ID, E2E_REPO_ID_2):
        stale = Path("/tmp/daily-helper/repos") / repo_id
        if stale.exists():
            shutil.rmtree(stale)

    env = {
        **os.environ,
        "DATA_DIR": app_data_dir,
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://127.0.0.1:9999"),
        # High throttle: E2E has a single writer (the test process via HTTP POST).
        # All writes are committed locally before the read — no remote pull needed.
        # Eliminates ~17 × 15s pull stalls across the test run (~4 min saved).
        "PULL_THROTTLE_SECONDS": "3600",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(E2E_PORT),
            "--log-level",
            "warning",
        ],
        cwd=APP_DIR,
        env=env,
    )
    base = f"http://127.0.0.1:{E2E_PORT}"
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{base}/health", timeout=1)
            break
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError(f"uvicorn exited early (code {proc.returncode})")
            time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("Server did not become ready within 30 s")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(live_server):
    """Override pytest-playwright base_url so page.goto('/path') works."""
    return live_server


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Grant clipboard permissions for clipboard-related tests."""
    return {
        **browser_context_args,
        "permissions": ["clipboard-read", "clipboard-write"],
    }


@pytest.fixture(autouse=True)
def set_page_timeout(page):
    """Increase default timeouts to 60 s — E2E server may be slow after many git ops."""
    page.set_default_timeout(60_000)
    page.set_default_navigation_timeout(60_000)


@pytest.fixture(scope="session")
def seeded_links(live_server):
    """Pre-create link test data once per session to minimise git pushes."""
    import urllib.parse

    links = [
        {"title": "E2E Link Alpha", "url": "https://example.com/alpha", "category": ""},
        {"title": "E2E Docs Link", "url": "https://docs.example.com", "category": "E2E-Docs"},
        {"title": "E2E URL Check", "url": "https://urlcheck.example.com", "category": ""},
        {
            "title": "E2E Filtered Link",
            "url": "https://filtered.example.com",
            "category": "E2E-Filter",
        },
        {"title": "E2E Quasar Link", "url": "https://quasar.example.com", "category": ""},
    ]
    for link in links:
        data = urllib.parse.urlencode({k: v for k, v in link.items()}).encode()
        req = urllib.request.Request(
            f"{live_server}/links/new",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError:
            pass  # redirect (303) raises HTTPError — that's expected
    return True


@pytest.fixture(scope="session")
def seeded_overflow_content(live_server):
    """Create notes with long subjects and long spaceless bodies.

    Ensures /notes and /history have real content with strings that can overflow
    on mobile — the main blind spot of the empty-page responsive tests.
    """
    import urllib.parse

    def _post(url, fields):
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError:
            pass  # 303 redirect — expected

    # Notes — long subject (tests word-break in list card + history audit entry)
    _post(
        f"{live_server}/notes/new",
        {
            "subject": "E2ELongSubjectOverflowTestWithoutAnySpacesForMobileLayoutCheck",
            "body": "Normal body for overflow subject test",
        },
    )
    # Notes — long spaceless body (simulates Fernet ciphertext; tests word-break:break-all)
    _post(
        f"{live_server}/notes/new",
        {
            "subject": "E2E Encrypted Note Overflow Test",
            "body": (
                "SGVsbG9Xb3JsZEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaYWJjZGVmZ2hpamts"
                "bW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkwQUJDREVGR0hJSktMTU5PUFFSU1RVVldY"
            ),
        },
    )

    # Tasks — long title without spaces (tests .task-title overflow in task card)
    _post(
        f"{live_server}/tasks",
        {
            "title": "E2ELongTaskTitleWithoutSpacesForMobileOverflowLayoutTestingPurposes",
            "description": "",
            "priority": "medium",
            "recurring": "none",
        },
    )

    # Runbooks — long title without spaces (tests card-as-container word-break)
    _post(
        f"{live_server}/runbooks/new",
        {
            "title": "E2ELongRunbookTitleWithoutSpacesForMobileOverflowLayoutTestingPurposes",
            "description": "",
        },
    )

    return True
