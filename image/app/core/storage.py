"""Git-backed storage driver for the knowledge base."""

import hashlib
import logging
import os
import random
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
import yaml

from . import cache

logger = logging.getLogger(__name__)

PULL_THROTTLE_SECONDS = int(os.environ.get("PULL_THROTTLE_SECONDS", "300"))

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))


class GitStorageError(Exception):
    pass


def _sanitize_git_error(msg: str) -> str:
    """Strip embedded credentials from git error messages before they reach the client."""
    return re.sub(r"(https?://)[^@\s]*@", r"\1***@", msg)


_NETWORK_ERROR_HINTS = (
    "could not resolve host",
    "connection refused",
    "connection timed out",
    "timed out",
    "network is unreachable",
    "unable to connect",
    "failed to connect",
    "no route to host",
    "connection reset",
    "ssh: connect to host",
    "connection closed",
    "temporary failure in name resolution",
    "errno 111",
    "errno 113",
    "no address associated",
    "broken pipe",
)


def _is_network_error(stderr: str) -> bool:
    lower = stderr.lower()
    return any(hint in lower for hint in _NETWORK_ERROR_HINTS)


# ── History rules ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _HistoryRule:
    """A module that stores one flat file per item under its own prefix.

    Modules whose paths vary (knowledge, tasks, notes, links) are handled by
    GitStorage._HISTORY_SPECIAL instead."""

    prefix: str
    module: str
    category: str
    url: str  # "/eol" or "/runbooks/{id}"
    title: "Callable[[dict, str], str]"
    depth: int = 2
    suffix: str | None = ".yaml"


def _title_from(*keys: str) -> "Callable[[dict, str], str]":
    """First non-empty key wins, the id is the fallback."""

    def pick(data: dict, slug: str) -> str:
        for key in keys:
            value = data.get(key)
            if value:
                return str(value)
        return slug

    return pick


def _title_vacation(data: dict, slug: str) -> str:
    start, end = data.get("start_date", ""), data.get("end_date", "")
    return f"{start} – {end}" if start and end else slug


def _title_motd(data: dict, slug: str) -> str:
    return data.get("text", "")[:60] or slug


def _title_eol(data: dict, slug: str) -> str:
    return f"{data.get('product', '')} {data.get('cycle', '')}".strip() or slug


def _title_stem(data: dict, slug: str) -> str:
    return slug


_HISTORY_RULES: tuple[_HistoryRule, ...] = (
    _HistoryRule("snippets/", "snippets", "Snippets", "/snippets/{id}", _title_from("title")),
    _HistoryRule("vacations/entries/", "vacations", "Vacations", "/vacations", _title_vacation, depth=3),
    # AppointmentStorage writes appointments/entries/ — the flat variant stays
    # for repos that still carry commits from the older layout.
    _HistoryRule(
        "appointments/entries/",
        "appointments",
        "Appointments",
        "/appointments",
        _title_from("title", "subject"),
        depth=3,
    ),
    _HistoryRule("appointments/", "appointments", "Appointments", "/appointments", _title_from("title", "subject")),
    _HistoryRule("runbooks/", "runbooks", "Runbooks", "/runbooks/{id}", _title_from("title")),
    _HistoryRule("mail_templates/", "mail_templates", "Mail Templates", "/mail-templates/{id}", _title_from("title")),
    _HistoryRule(
        "ticket_templates/", "ticket_templates", "Ticket Templates", "/ticket-templates/{id}", _title_from("title")
    ),
    _HistoryRule("motd/", "motd", "MOTD", "/motd", _title_motd),
    _HistoryRule("potd/", "potd", "Picture of the Day", "/potd", _title_stem, suffix=None),
    _HistoryRule("memes/", "memes", "Memes", "/memes", _title_stem, suffix=None),
    _HistoryRule("eol/", "eol", "EOL Tracker", "/eol", _title_eol),
    _HistoryRule("rss/", "rss", "RSS", "/rss", _title_from("name")),
)


class GitStorage:
    """Single-repo git storage driver."""

    def __init__(self, repo_id: str, repo_url: str, settings: dict):
        self.repo_id = repo_id
        self.repo_url = repo_url
        self.local_path = DATA_DIR / "repos" / repo_id
        self._settings = settings
        self._ssh_key_file: str | None = None
        self._ca_cert_file: str | None = None
        self._askpass_file: str | None = None
        self._gpg_home: str | None = None
        self._gpg_key_id: str | None = None
        self._last_pull: float = 0.0
        self._push_retry_count: int = int(settings.get("push_retry_count", 1))
        self._write_lock = threading.RLock()
        self._setup_credentials()
        self._ensure_repo()

    def write_lock(self):
        """Serialise one repo's write transaction: pull → change files → commit.

        Without it two writers can interleave between pull and commit and the
        second push takes the first one's file state with it — a lost update.
        Reentrant, so a method holding the lock may call another that takes it.
        Per repo, not global: writing to two repos in parallel is fine.
        """
        return self._write_lock

    @property
    def _pending_push_path(self) -> Path:
        return self.local_path / ".pending_push"

    @property
    def has_pending_push(self) -> bool:
        return self._pending_push_path.exists()

    def _mark_pending_push(self) -> None:
        try:
            self._pending_push_path.write_text("")
        except Exception as e:
            logger.warning("Failed to mark pending push for repo %s: %s", self.repo_id, e)

    def _clear_pending_push(self) -> None:
        try:
            self._pending_push_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Failed to clear pending push marker for repo %s: %s", self.repo_id, e)

    def retry_pending_push(self) -> bool:
        """Try to push pending local commits to remote. Returns True when clean."""
        if not self.has_pending_push:
            return True
        try:
            result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return False
        if result.returncode == 0:
            self._clear_pending_push()
            cache.invalidate_repo(self.repo_id)
            logger.info("Offline push retry succeeded for repo %s", self.repo_id)
            return True
        logger.debug(
            "Offline push retry still failing for repo %s: %s",
            self.repo_id,
            result.stderr.strip()[:120],
        )
        return False

    @property
    def knowledge_path(self) -> Path:
        """Knowledge entries live in knowledge/ subdir of the repo."""
        return self.local_path / "knowledge"

    # --- Credential setup ---

    def _setup_credentials(self):
        s = self._settings
        auth_mode = s.get("auth_mode", "none")

        creds_dir = DATA_DIR / "run"
        creds_dir.mkdir(parents=True, exist_ok=True)

        if auth_mode == "ssh" and s.get("ssh_key"):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w", dir=creds_dir)
            key = s["ssh_key"].strip().replace("\r\n", "\n").replace("\r", "\n")
            if not key.endswith("\n"):
                key += "\n"
            tmp.write(key)
            tmp.flush()
            os.chmod(tmp.name, 0o600)
            self._ssh_key_file = tmp.name

        if s.get("ca_cert"):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w", dir=creds_dir)
            tmp.write(s["ca_cert"].strip())
            tmp.flush()
            self._ca_cert_file = tmp.name

        if s.get("gpg_key"):
            self._setup_gpg(s["gpg_key"], s.get("gpg_passphrase", ""))

        if auth_mode == "basic" and s.get("basic_password"):
            user = s.get("basic_user", "")
            pwd = s.get("basic_password", "")
            script = (
                "#!/bin/sh\n"
                'case "$1" in\n'
                f"  *sername*) echo {shlex.quote(user)} ;;\n"
                f"  *assword*) echo {shlex.quote(pwd)} ;;\n"
                "esac\n"
            )
            askpass_dir = DATA_DIR / "run"
            askpass_dir.mkdir(parents=True, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sh", mode="w", dir=askpass_dir)
            tmp.write(script)
            tmp.flush()
            os.chmod(tmp.name, 0o700)
            self._askpass_file = tmp.name

    def _setup_gpg(self, gpg_key: str, passphrase: str):
        """Import GPG key into a per-repo homedir and capture the key ID.

        Sets self._gpg_home and self._gpg_key_id only when the key is fully
        imported and verifiably accessible.  On any failure both stay None so
        commits fall back to unsigned mode instead of crashing.
        """
        gpg_dir = Path("/tmp/daily-helper/gpg") / self.repo_id
        gpg_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        gpg_home = str(gpg_dir)

        # Allow loopback pinentry (no TTY needed)
        (gpg_dir / "gpg-agent.conf").write_text("allow-loopback-pinentry\n")

        env = os.environ.copy()
        env["GNUPGHOME"] = gpg_home

        import_input = gpg_key.strip().encode()
        result = subprocess.run(
            ["gpg", "--batch", "--import"],
            input=import_input,
            capture_output=True,
            env=env,
        )
        if result.returncode != 0:
            logger.warning("GPG import failed for repo %s: %s", self.repo_id, result.stderr.decode())
            return

        # Extract key ID from import output
        key_id: str | None = None
        for line in result.stderr.decode().splitlines():
            if "key " in line and ":" in line:
                # "gpg: key ABCD1234: public key ..."
                parts = line.split("key ")
                if len(parts) > 1:
                    key_id = parts[1].split(":")[0].strip()
                    break

        if not key_id:
            logger.warning("GPG key ID could not be extracted for repo %s", self.repo_id)
            return

        # Verify the secret key is actually accessible (pubring.kbx may be missing
        # if GPG wrote to a different location or the homedir was recreated)
        verify = subprocess.run(
            ["gpg", "--batch", "--list-secret-keys", key_id],
            capture_output=True,
            env=env,
        )
        if verify.returncode != 0:
            logger.warning(
                "GPG key %s not accessible for repo %s after import — signing disabled. %s",
                key_id,
                self.repo_id,
                verify.stderr.decode(),
            )
            return

        # Only commit to signed mode now that the key is confirmed usable
        self._gpg_home = gpg_home
        self._gpg_key_id = key_id

        # Pre-cache passphrase in gpg-agent so signing works non-interactively
        if passphrase:
            subprocess.run(
                [
                    "gpg",
                    "--batch",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase-fd",
                    "0",
                    "--armor",
                    "--sign",
                ],
                input=(passphrase + "\n" + "test").encode(),
                capture_output=True,
                env=env,
            )

    def _build_env(self) -> dict:
        env = os.environ.copy()
        s = self._settings
        cfg = s.get("_global", {})

        # Repo-specific identity takes precedence over global
        name = s.get("git_user_name", "").strip() or cfg.get("git_user_name", "Daily Helper")
        email = s.get("git_user_email", "").strip() or cfg.get("git_user_email", "daily@helper.local")
        env["GIT_AUTHOR_NAME"] = name
        env["GIT_AUTHOR_EMAIL"] = email
        env["GIT_COMMITTER_NAME"] = name
        env["GIT_COMMITTER_EMAIL"] = email

        if self._gpg_home:
            env["GNUPGHOME"] = self._gpg_home

        if s.get("auth_mode") == "ssh" and self._ssh_key_file:
            env["GIT_SSH_COMMAND"] = f"ssh -i {self._ssh_key_file} -o StrictHostKeyChecking=accept-new -o BatchMode=yes"

        if self._ca_cert_file:
            env["GIT_SSL_CAINFO"] = self._ca_cert_file

        if self._askpass_file:
            env["GIT_ASKPASS"] = self._askpass_file
            env["GIT_TERMINAL_PROMPT"] = "0"

        return env

    def _effective_url(self) -> str:
        s = self._settings
        url = self.repo_url
        if s.get("auth_mode") == "pat" and s.get("pat"):
            url = re.sub(r"^(https?://)", rf"\1oauth2:{s['pat']}@", url)
        return url

    # --- Git operations ---

    def _run(self, *args, check=True, timeout=None):
        try:
            result = subprocess.run(
                args,
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise GitStorageError(f"Git command timed out: {' '.join(args)}") from e
        if check and result.returncode != 0:
            raise GitStorageError(_sanitize_git_error(f"Git error: {result.stderr.strip()}"))
        return result

    def _ensure_repo(self):
        if (self.local_path / ".git").exists():
            # Always sync the remote URL so that PAT/credential changes in
            # settings take effect without requiring a full re-clone.
            subprocess.run(
                ["git", "remote", "set-url", "origin", self._effective_url()],
                cwd=self.local_path,
                capture_output=True,
                env=self._build_env(),
            )
            try:
                self._run("git", "pull", "--rebase", "origin", "main")
            except GitStorageError:
                pass
        else:
            self.local_path.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", self._effective_url(), str(self.local_path)],
                capture_output=True,
                text=True,
                env=self._build_env(),
            )
            if result.returncode != 0:
                raise GitStorageError(_sanitize_git_error(f"Clone failed: {result.stderr.strip()}"))

    def _pull(self):
        now = time.monotonic()
        if now - self._last_pull < PULL_THROTTLE_SECONDS:
            return
        try:
            self._run("git", "pull", "--rebase", "origin", "main", timeout=15)
            self._last_pull = time.monotonic()
        except GitStorageError:
            pass

    def _ensure_fetched(self):
        """Fetch from origin to refresh remote-tracking refs (throttled, shares _last_pull)."""
        now = time.monotonic()
        if now - self._last_pull < PULL_THROTTLE_SECONDS:
            return
        try:
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=self.local_path,
                capture_output=True,
                env=self._build_env(),
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            pass
        self._last_pull = time.monotonic()

    def read_committed(self, path: str) -> bytes | None:
        """Read a file from HEAD — never touches the working tree.

        Uses HEAD (not origin/main) so it agrees with list_committed()/
        list_committed_recursive(): a file just committed locally (but not
        yet pushed) must be readable, or callers pairing "list" with "read"
        would see it in the listing and then get None back for it.
        """
        path_hash = hashlib.sha1(path.encode()).hexdigest()[:20]
        cache_key = f"file:{self.repo_id}:{path_hash}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached.encode() if isinstance(cached, str) else None

        self._ensure_fetched()
        result = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=self.local_path,
            capture_output=True,
            env=self._build_env(),
        )
        if result.returncode != 0:
            return None
        content = result.stdout
        # Only cache text files up to 256 KB to avoid Redis memory bloat
        if len(content) < 256 * 1024:
            try:
                cache.set(cache_key, content.decode("utf-8"), ttl=600)
            except (UnicodeDecodeError, AttributeError):
                pass  # binary file — skip caching
        return content

    def list_committed(self, directory: str) -> list[str]:
        """List filenames directly in directory/ from HEAD (non-recursive)."""
        cache_key = f"ls:{self.repo_id}:{directory}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        self._ensure_fetched()
        result = subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD", f"{directory}/"],
            cwd=self.local_path,
            capture_output=True,
            text=True,
            env=self._build_env(),
        )
        if result.returncode != 0:
            cache.set(cache_key, [], ttl=600)
            return []
        prefix = directory.rstrip("/") + "/"
        names = []
        for line in result.stdout.splitlines():
            name = line.strip()
            if not name:
                continue
            # git ls-tree returns full paths (e.g. "notes/file.yaml"); strip prefix
            if name.startswith(prefix):
                name = name[len(prefix) :]
            names.append(name)
        cache.set(cache_key, names, ttl=600)
        return names

    def list_committed_recursive(self, directory: str) -> list[str]:
        """List all file paths under directory/ recursively from HEAD."""
        cache_key = f"ls:{self.repo_id}:r:{directory}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        self._ensure_fetched()
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", f"{directory}/"],
            cwd=self.local_path,
            capture_output=True,
            text=True,
            env=self._build_env(),
        )
        if result.returncode != 0:
            cache.set(cache_key, [], ttl=600)
            return []
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        cache.set(cache_key, names, ttl=600)
        return names

    def _revert_working_tree(self, undo_commit: bool = True):
        """Discard all staged and unstaged changes, remove untracked files.

        Called after a failed push (undo_commit=True, to drop the local-only
        commit that couldn't be pushed) or after a failed commit itself
        (undo_commit=False — no commit exists yet, so `reset HEAD~1` would
        wrongly discard the previous, already-pushed commit instead).
        """
        env = self._build_env()
        cmds = [
            ["git", "restore", "--staged", "."],  # unstage
            ["git", "restore", "."],  # discard working-tree changes
            ["git", "clean", "-fd"],  # remove untracked files/dirs
        ]
        if undo_commit:
            cmds.insert(0, ["git", "reset", "--soft", "HEAD~1"])  # undo commit
        for cmd in cmds:
            subprocess.run(cmd, cwd=self.local_path, capture_output=True, env=env)

    def _commit_and_push(self, message: str):
        self._run("git", "add", "-A")
        result = self._run("git", "diff", "--cached", "--quiet", check=False)
        if result.returncode == 0:
            return

        # ── Commit phase — revert on any failure ────────────────────────────
        try:
            if self._gpg_key_id and self._gpg_home:
                try:
                    self._run("git", "commit", "-m", message, f"--gpg-sign={self._gpg_key_id}")
                except GitStorageError as exc:
                    if "gpg" in str(exc).lower() or "sign" in str(exc).lower():
                        logger.warning("GPG signing failed for repo %s, falling back: %s", self.repo_id, exc)
                        self._gpg_key_id = None
                        self._gpg_home = None
                        self._run("git", "commit", "-m", message)
                    else:
                        raise
            else:
                self._run("git", "commit", "-m", message)
        except Exception:
            self._revert_working_tree(undo_commit=False)
            raise

        # Invalidate cache immediately after commit so HEAD-based reads reflect new state
        cache.invalidate_repo(self.repo_id)

        # ── Push phase — network errors queue locally, others revert+raise ──
        try:
            push = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            self._mark_pending_push()
            logger.warning("Push timed out for repo %s — queued for offline retry", self.repo_id)
            return

        if push.returncode == 0:
            cache.invalidate_repo(self.repo_id)
            self._clear_pending_push()
            return

        stderr = push.stderr.strip()

        # Conflict: rebase and retry
        if any(p in stderr.lower() for p in ("rejected", "non-fast-forward", "fetch first", "behind")):
            for attempt in range(self._push_retry_count):
                if attempt > 0:
                    time.sleep(random.uniform(0.5, 2.0))
                rebase = subprocess.run(
                    ["git", "pull", "--rebase", "origin", "main"],
                    cwd=self.local_path,
                    capture_output=True,
                    env=self._build_env(),
                )
                if rebase.returncode != 0:
                    break
                self._last_pull = time.monotonic()
                retry = subprocess.run(
                    ["git", "push", "origin", "main"],
                    cwd=self.local_path,
                    capture_output=True,
                    text=True,
                    env=self._build_env(),
                )
                if retry.returncode == 0:
                    cache.invalidate_repo(self.repo_id)
                    self._clear_pending_push()
                    return
                stderr = retry.stderr.strip()
                if not any(p in stderr.lower() for p in ("rejected", "non-fast-forward", "fetch first", "behind")):
                    break
            self._revert_working_tree()
            raise GitStorageError(
                "Push rejected: the remote has new commits not yet in your local copy. "
                "Another client may have pushed changes — the app will sync automatically on the next request."
            )

        # Network error: keep commit locally, queue for retry
        if _is_network_error(stderr):
            self._mark_pending_push()
            logger.warning("Push failed (network) for repo %s — queued for retry", self.repo_id)
            return

        # Other error: revert and surface
        self._revert_working_tree()
        raise GitStorageError(_sanitize_git_error(f"Git error: {stderr}"))

    def test_connection(self) -> dict:
        s = self._settings
        sanitized_url = re.sub(r"(https?://)[^@\s]*@", r"\1***@", self._effective_url())
        info: dict = {
            "ok": False,
            "read_ok": False,
            "write_ok": False,
            "write_tested": False,
            "output": "",
            "write_output": "",
            "effective_url": sanitized_url,
            "auth_mode": s.get("auth_mode", "none"),
            "pat_present": bool(s.get("pat", "").strip()),
            "ca_cert_present": bool(s.get("ca_cert", "").strip()),
            "ssh_key_present": bool(s.get("ssh_key", "").strip()),
            "platform": s.get("platform", "gitea"),
        }

        # ── Read test: ls-remote ──
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", self._effective_url()],
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=15,
            )
            info["read_ok"] = result.returncode == 0
            raw = result.stdout.strip() or result.stderr.strip() or "(no output)"
            info["output"] = _sanitize_git_error(raw)
        except subprocess.TimeoutExpired:
            info["output"] = "Timeout — repository unreachable after 15s."
            info["ok"] = False
            return info
        except Exception as e:
            info["output"] = str(e)
            return info

        if not info["read_ok"]:
            info["ok"] = False
            return info

        # ── Write test: temp branch commit + push + delete ──
        info["write_tested"] = True
        test_branch = "daily-helper/write-test"
        try:
            self._ensure_repo()

            # Start from current HEAD, create temp branch
            self._run("git", "fetch", "origin")
            self._run("git", "checkout", "-B", test_branch, "origin/main")

            # Write a marker file, commit, push
            marker = self.local_path / ".daily-helper-write-test"
            marker.write_text(f"write test {datetime.now(timezone.utc).isoformat()}\n")
            self._run("git", "add", str(marker))
            self._run("git", "commit", "-m", "chore: daily-helper write test (auto-removed)")
            push = subprocess.run(
                ["git", "push", "origin", test_branch],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=30,
            )
            if push.returncode != 0:
                info["write_ok"] = False
                info["write_output"] = _sanitize_git_error(push.stderr.strip() or "Push failed")
            else:
                info["write_ok"] = True
                info["write_output"] = "Test commit pushed and removed successfully."
                # Delete remote branch
                del_result = subprocess.run(
                    ["git", "push", "origin", "--delete", test_branch],
                    cwd=self.local_path,
                    capture_output=True,
                    text=True,
                    env=self._build_env(),
                    timeout=15,
                )
                if del_result.returncode != 0:
                    info["write_output"] += (
                        f" (remote branch cleanup failed: {_sanitize_git_error(del_result.stderr.strip())})"
                    )
        except Exception as exc:
            info["write_ok"] = False
            info["write_output"] = _sanitize_git_error(str(exc))
        finally:
            # Always return to main branch and clean up locally
            try:
                subprocess.run(
                    ["git", "checkout", "main"],
                    cwd=self.local_path,
                    capture_output=True,
                    env=self._build_env(),
                )
                subprocess.run(
                    ["git", "branch", "-D", test_branch],
                    cwd=self.local_path,
                    capture_output=True,
                    env=self._build_env(),
                )
                marker = self.local_path / ".daily-helper-write-test"
                if marker.exists():
                    marker.unlink()
            except Exception:
                pass

        info["ok"] = info["read_ok"] and info["write_ok"]
        return info

    # --- Helpers ---

    def _slug(self, title: str) -> str:
        slug = title.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_-]+", "-", slug)
        return slug.strip("-") or "entry"

    @staticmethod
    def _reject_traversal(value: str, label: str) -> None:
        """Reject path traversal / absolute paths in a single path component.

        Used at the storage layer itself (not just in router-side helpers
        like knowledge/router.py's _safe_filename) so a caller can never
        turn a category/slug/filename into an escape from the repo dir.
        """
        stripped = value.strip() if value else ""
        if not stripped:
            raise GitStorageError(f"{label} must not be empty.")
        if stripped in (".", ".."):
            raise GitStorageError(f"Invalid {label.lower()}: {value!r}")
        parts = Path(stripped).parts
        if any(p in (".", "..", "/") or p.startswith("/") for p in parts):
            raise GitStorageError(f"Invalid {label.lower()}: {value!r}")
        # Exactly one component: a value like "sub/name" contains no traversal
        # but is still not the single component this function promises, and
        # would silently create a subdirectory at the call site.
        if len(parts) != 1:
            raise GitStorageError(f"Invalid {label.lower()}: {value!r}")

    @classmethod
    def _validate_category(cls, category: str) -> None:
        """Reject path traversal and absolute paths in category names."""
        cls._reject_traversal(category, "Category")

    def _entry_dict_from_git(self, git_path: str, content: bytes) -> dict:
        """Build an entry dict from a git object (never reads from working tree)."""
        post = frontmatter.loads(content.decode("utf-8"))
        parts = git_path.split("/")  # knowledge/{category}/{slug}.md
        category = parts[1] if len(parts) >= 3 else ""
        slug = parts[-1].replace(".md", "")
        rel_path = "/".join(parts[1:])
        return {
            "repo_id": self.repo_id,
            "title": post.get("title", slug),
            "category": post.get("category", category),
            "created": post.get("created", ""),
            "slug": slug,
            "path": rel_path,
            "excerpt": post.content[:200].strip(),
            "pinned": bool(post.get("pinned", False)),
        }

    # --- Public API ---

    def get_categories(self) -> list[str]:
        key = f"kb:{self.repo_id}:categories"
        cached = cache.get(key)
        if cached is not None:
            return cached
        self._ensure_fetched()
        result = subprocess.run(
            ["git", "ls-tree", "--name-only", "-d", "HEAD", "knowledge/"],
            cwd=self.local_path,
            capture_output=True,
            text=True,
            env=self._build_env(),
        )
        prefix = "knowledge/"
        dirs = (
            sorted(
                line.strip()[len(prefix) :] if line.strip().startswith(prefix) else line.strip()
                for line in result.stdout.splitlines()
                if line.strip() and not line.strip().startswith(".")
            )
            if result.returncode == 0
            else []
        )
        cache.set(key, dirs)
        return dirs

    def get_entries(self, category: str | None = None) -> list[dict]:
        key = f"kb:{self.repo_id}:entries:{category or '*'}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        git_dir = f"knowledge/{category}" if category else "knowledge"
        paths = self.list_committed_recursive(git_dir)
        entries = []
        for git_path in sorted(paths):
            if not git_path.endswith(".md"):
                continue
            content = self.read_committed(git_path)
            if content is None:
                continue
            try:
                entries.append(self._entry_dict_from_git(git_path, content))
            except Exception as exc:
                # The entry is left out of the list; without the log it would
                # simply be gone from the UI with no hint where to look.
                logger.warning("Skipping unreadable knowledge entry %s in %s: %s", git_path, self.repo_id, exc)
                continue
        cache.set(key, entries)
        return entries

    def get_entry(self, category: str, slug: str) -> dict | None:
        self._reject_traversal(category, "Category")
        self._reject_traversal(slug, "Slug")
        git_path = f"knowledge/{category}/{slug}.md"
        content = self.read_committed(git_path)
        if content is None:
            return None
        post = frontmatter.loads(content.decode("utf-8"))
        return {
            "repo_id": self.repo_id,
            "title": post.get("title", slug),
            "category": post.get("category", category),
            "created": post.get("created", ""),
            "slug": slug,
            "content": post.content,
            "pinned": bool(post.get("pinned", False)),
            "attachments": self.list_attachments(category, slug),
        }

    # ── History ────────────────────────────────────────────────────────────────

    def _slug_to_title(self, slug: str) -> str:
        return slug.replace("-", " ").replace("_", " ").title()

    def _history_read_yaml(self, path: str, deleted: bool) -> dict:
        if deleted:
            return {}
        content = self.read_committed(path)
        if not content:
            return {}
        try:
            return yaml.safe_load(content.decode("utf-8")) or {}
        except Exception:
            return {}

    def _history_read_md_title(self, path: str, fallback: str, deleted: bool) -> str:
        if deleted:
            return fallback
        content = self.read_committed(path)
        if content:
            try:
                return frontmatter.loads(content.decode("utf-8")).get("title", fallback)
            except Exception:
                pass
        return fallback

    def _history_change(
        self, action: str, path: str, module: str, category: str, slug: str, title: str, url: str, **extra
    ) -> dict:
        return {
            "action": action,
            "path": path,
            "module": module,
            "category": category,
            "slug": slug,
            "repo_id": self.repo_id,
            "title": title,
            "deleted": action == "D",
            "url": url,
            **extra,
        }

    # ── History: modules whose paths need their own rules ──────────────────────

    def _history_knowledge(self, path: str, parts: list[str], action: str) -> "dict | None":
        """knowledge/{category}/{slug}.md — the only Markdown module, and the
        only one whose category is part of the path rather than fixed."""
        if not (path.endswith(".md") and len(parts) == 3):
            return None
        category, slug = parts[1], parts[2][:-3]
        title = self._history_read_md_title(path, self._slug_to_title(slug), action == "D")
        return self._history_change(
            action, path, "knowledge", category, slug, title, f"/knowledge/entries/{self.repo_id}/{category}/{slug}"
        )

    def _history_tasks(self, path: str, parts: list[str], action: str) -> "dict | None":
        """tasks/{id}.yaml or tasks/done/{id}.yaml — completing a task moves the
        file, so the commit that removes it can only be titled from the other
        location."""
        if not path.endswith(".yaml"):
            return None
        if len(parts) == 2:
            task_id = parts[1][:-5]
        elif len(parts) == 3 and parts[1] == "done":
            task_id = parts[2][:-5]
        else:
            return None
        data = self._history_read_yaml(path, action == "D")
        if not data:
            alt = f"tasks/done/{task_id}.yaml" if len(parts) == 2 else f"tasks/{task_id}.yaml"
            data = self._history_read_yaml(alt, False)
        return self._history_change(
            action, path, "tasks", "Tasks", task_id, data.get("title") or task_id, f"/tasks/{task_id}/edit"
        )

    def _history_notes(self, path: str, parts: list[str], action: str) -> "dict | None":
        """notes/{id}.yaml or notes/archive/{id}.yaml — an archived note has no
        detail page of its own."""
        if not path.endswith(".yaml"):
            return None
        if len(parts) == 2:
            note_id = parts[1][:-5]
            url = f"/notes/{note_id}"
        elif len(parts) == 3 and parts[1] == "archive":
            note_id = parts[2][:-5]
            url = "/notes/archive"
        else:
            return None
        data = self._history_read_yaml(path, action == "D")
        return self._history_change(action, path, "notes", "Notes", note_id, data.get("subject") or note_id, url)

    def _history_links(self, path: str, parts: list[str], action: str) -> "dict | None":
        """links/{id}.yaml or links/{section}/{id}.yaml — links moved between
        flat and sectioned layouts, so both spellings still occur in history."""
        if not path.endswith(".yaml"):
            return None
        if len(parts) == 2:
            link_id, section = parts[1][:-5], ""
        elif len(parts) == 3:
            link_id, section = parts[2][:-5], parts[1]
        else:
            return None
        data = self._history_read_yaml(path, action == "D")
        if not data and action != "D":
            for alt in (f"links/default/{link_id}.yaml", f"links/{link_id}.yaml"):
                if alt == path:
                    continue
                alt_data = self._history_read_yaml(alt, False)
                if alt_data:
                    data = alt_data
                    section = alt.split("/")[1] if alt.count("/") == 2 else ""
                    break
        title = data.get("title") or data.get("url") or link_id
        edit_url = f"/links/{link_id}/edit" + (f"?section={section}" if section else "")
        return self._history_change(
            action, path, "links", "Links", link_id, title, "/links" if action == "D" else edit_url
        )

    _HISTORY_SPECIAL = {
        "knowledge": _history_knowledge,
        "tasks": _history_tasks,
        "notes": _history_notes,
        "links": _history_links,
    }

    def _parse_history_path(self, path: str, action: str) -> "dict | None":
        """Parse a changed file path into a history change dict, or None to skip.

        A path that matches no rule drops out of the history silently, so every
        module that writes to the repo needs an entry either in _HISTORY_SPECIAL
        or in _HISTORY_RULES (see test_history_rules.py)."""
        parts = path.split("/")
        special = self._HISTORY_SPECIAL.get(parts[0])
        if special is not None:
            return special(self, path, parts, action)

        for rule in _HISTORY_RULES:
            if not path.startswith(rule.prefix) or len(parts) != rule.depth:
                continue
            if rule.suffix and not path.endswith(rule.suffix):
                continue
            # removesuffix, not rsplit: an id containing a dot would otherwise
            # be truncated. Media files have no fixed suffix and keep rsplit.
            slug = parts[-1].removesuffix(rule.suffix) if rule.suffix else parts[-1].rsplit(".", 1)[0]
            data = self._history_read_yaml(path, action == "D") if rule.suffix == ".yaml" else {}
            return self._history_change(
                action,
                path,
                rule.module,
                rule.category,
                slug,
                rule.title(data, slug),
                rule.url.format(id=slug),
            )

        return None  # unknown / internal file — skip

    def get_history(self, since_dt: "datetime | None" = None, limit: int = 200) -> list[dict]:
        """Return commit history for all modules, newest first.
        Each entry: {hash, ts, author, subject, changes: [{action, path, module, category,
        slug, repo_id, title, deleted, url}]}
        """
        args = [
            "git",
            "log",
            "--format=COMMIT|%H|%ct|%an|%s",
            "--name-status",
            "--diff-filter=ADM",
        ]
        if since_dt:
            args.append(f"--since={int(since_dt.timestamp())}")
        args.append(f"-n{limit * 4}")
        try:
            r = subprocess.run(
                args,
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=15,
            )
        except Exception:
            return []

        results: list[dict] = []
        current: dict | None = None
        for line in r.stdout.splitlines():
            if line.startswith("COMMIT|"):
                if current and current["changes"]:
                    results.append(current)
                parts = line.split("|", 4)
                if len(parts) == 5:
                    current = {
                        "hash": parts[1],
                        "ts": int(parts[2]),
                        "author": parts[3],
                        "subject": parts[4],
                        "changes": [],
                    }
                else:
                    current = None
            elif current and line and "\t" in line:
                action, _, path = line.partition("\t")
                path = path.strip()
                action = action.strip()
                ch = self._parse_history_path(path, action)
                if ch:
                    current["changes"].append(ch)
        if current and current["changes"]:
            results.append(current)
        return results[:limit]

    def get_file_history(self, path: str, limit: int = 30) -> list[dict]:
        """Return commit history for a single file path (git log --follow).
        Each entry: {sha, date (datetime), author, message}
        """
        try:
            r = subprocess.run(
                [
                    "git",
                    "log",
                    "--follow",
                    "--format=COMMIT|%H|%ct|%an|%s",
                    f"-n{limit}",
                    "--",
                    path,
                ],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=10,
            )
        except Exception:
            return []
        entries = []
        for line in r.stdout.splitlines():
            if not line.startswith("COMMIT|"):
                continue
            parts = line.split("|", 4)
            if len(parts) == 5:
                entries.append(
                    {
                        "sha": parts[1],
                        "date": datetime.fromtimestamp(int(parts[2])),
                        "author": parts[3],
                        "message": parts[4],
                    }
                )
        return entries

    def get_file_diff(self, sha: str, path: str) -> str:
        """Return unified diff for a specific commit and file path."""
        # Basic SHA validation to prevent injection
        if not sha or not all(c in "0123456789abcdefABCDEF" for c in sha):
            return ""
        try:
            r = subprocess.run(
                ["git", "show", "--unified=3", f"{sha}", "--", path],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=10,
            )
        except Exception:
            return ""
        return r.stdout if r.returncode == 0 else ""

    def get_recent_activity(self, limit: int = 10) -> dict:
        """Return last N added and last N modified knowledge entries."""
        history = self.get_history(limit=limit * 6)
        added: list[dict] = []
        modified: list[dict] = []
        seen_added: set[str] = set()
        seen_modified: set[str] = set()
        for commit in history:
            for ch in commit["changes"]:
                key = f"{ch['category']}/{ch['slug']}"
                if ch["action"] == "A" and key not in seen_added:
                    seen_added.add(key)
                    added.append({**ch, "ts": commit["ts"]})
                elif ch["action"] == "M" and key not in seen_modified:
                    seen_modified.add(key)
                    modified.append({**ch, "ts": commit["ts"]})
                if len(added) >= limit and len(modified) >= limit:
                    break
            if len(added) >= limit and len(modified) >= limit:
                break
        return {"added": added[:limit], "modified": modified[:limit]}

    # ── Attachments ────────────────────────────────────────────────────────────

    def _attachment_dir(self, category: str, slug: str) -> Path:
        self._reject_traversal(category, "Category")
        self._reject_traversal(slug, "Slug")
        return self.knowledge_path / category / slug

    def list_attachments(self, category: str, slug: str) -> list[str]:
        att_dir = self._attachment_dir(category, slug)
        if not att_dir.is_dir():
            return []
        return sorted(f.name for f in att_dir.iterdir() if f.is_file())

    def save_attachment(self, category: str, slug: str, filename: str, data: bytes) -> None:
        self._reject_traversal(filename, "Filename")
        with self.write_lock():
            self._pull()
            att_dir = self._attachment_dir(category, slug)
            att_dir.mkdir(parents=True, exist_ok=True)
            (att_dir / filename).write_bytes(data)
            self._commit_and_push(f"docs: attach '{filename}' to {category}/{slug}")
        cache.invalidate_repo(self.repo_id)

    def get_attachment(self, category: str, slug: str, filename: str) -> bytes | None:
        self._reject_traversal(filename, "Filename")
        att_file = self._attachment_dir(category, slug) / filename
        return att_file.read_bytes() if att_file.is_file() else None

    def delete_attachment(self, category: str, slug: str, filename: str) -> bool:
        self._reject_traversal(filename, "Filename")
        with self.write_lock():
            self._pull()
            att_file = self._attachment_dir(category, slug) / filename
            if not att_file.is_file():
                return False
            att_file.unlink()
            att_dir = self._attachment_dir(category, slug)
            if att_dir.is_dir() and not any(att_dir.iterdir()):
                att_dir.rmdir()
            self._commit_and_push(f"docs: remove attachment '{filename}' from {category}/{slug}")
        cache.invalidate_repo(self.repo_id)
        return True

    def save_entry(self, category: str, title: str, content: str) -> dict:
        self._validate_category(category)
        with self.write_lock():
            category_dir = self.knowledge_path / category
            category_dir.mkdir(parents=True, exist_ok=True)

            slug = self._slug(title)
            md_file = category_dir / f"{slug}.md"

            # The free-slug search reads the directory and the write claims it —
            # two concurrent creates with the same title would otherwise pick the
            # same filename and one entry would be lost.
            counter = 1
            while md_file.exists():
                existing = frontmatter.load(md_file)
                if existing.get("title") == title:
                    break
                md_file = category_dir / f"{slug}-{counter}.md"
                counter += 1
            slug = md_file.stem

            post = frontmatter.Post(
                content,
                title=title,
                category=category,
                created=datetime.now().strftime("%Y-%m-%d"),
            )
            md_file.write_text(frontmatter.dumps(post), encoding="utf-8")
            self._commit_and_push(f"docs: add '{title}' in {category}")
        cache.invalidate_repo(self.repo_id)
        return {"repo_id": self.repo_id, "slug": slug, "category": category}

    def update_entry(self, category: str, slug: str, title: str, content: str) -> dict:
        self._validate_category(category)
        with self.write_lock():
            self._pull()
            md_file = self.knowledge_path / category / f"{slug}.md"
            if not md_file.exists():
                raise GitStorageError(f"Entry not found: {category}/{slug}")
            existing = frontmatter.load(md_file)
            kwargs = {
                "title": title,
                "category": category,
                "created": existing.get("created", datetime.now().strftime("%Y-%m-%d")),
            }
            if existing.get("pinned"):
                kwargs["pinned"] = True
            post = frontmatter.Post(content, **kwargs)
            md_file.write_text(frontmatter.dumps(post), encoding="utf-8")
            self._commit_and_push(f"docs: update '{title}' in {category}")
        cache.invalidate_repo(self.repo_id)
        return {"repo_id": self.repo_id, "slug": slug, "category": category}

    def search(self, query: str) -> list[dict]:
        if not query.strip():
            return []
        key = f"kb:{self.repo_id}:search:{query.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        query_lower = query.lower()
        paths = self.list_committed_recursive("knowledge")
        results = []
        for git_path in sorted(paths):
            if not git_path.endswith(".md"):
                continue
            content = self.read_committed(git_path)
            if content is None:
                continue
            try:
                post = frontmatter.loads(content.decode("utf-8"))
                haystack = (post.get("title", "") + " " + post.content).lower()
                if query_lower not in haystack:
                    continue
                parts = git_path.split("/")
                category = parts[1] if len(parts) >= 3 else ""
                slug = parts[-1].replace(".md", "")
                idx = haystack.find(query_lower)
                snippet_start = max(0, idx - 80)
                snippet_end = min(len(post.content), idx + 120)
                snippet = post.content[snippet_start:snippet_end].strip()
                results.append(
                    {
                        "repo_id": self.repo_id,
                        "title": post.get("title", slug),
                        "category": post.get("category", category),
                        "slug": slug,
                        "path": "/".join(parts[1:]),
                        "snippet": snippet,
                        # The date filter on /search reads this. Without it the
                        # filter silently passed every knowledge hit through.
                        "created": str(post.get("created", "")),
                    }
                )
            except Exception as exc:
                logger.warning("Search skipped unreadable knowledge entry %s in %s: %s", git_path, self.repo_id, exc)
                continue
        cache.set(key, results)
        return results

    def toggle_pin(self, category: str, slug: str) -> dict:
        git_path = f"knowledge/{category}/{slug}.md"
        # Read and write have to sit in one transaction: the new state is derived
        # from the committed one, so an interleaved toggle would be inverted back.
        with self.write_lock():
            content = self.read_committed(git_path)
            if content is None:
                raise GitStorageError(f"Entry not found: {category}/{slug}")
            post = frontmatter.loads(content.decode("utf-8"))
            new_pinned = not bool(post.get("pinned", False))
            md_file = self.knowledge_path / category / f"{slug}.md"
            kwargs = {
                "title": post.get("title", slug),
                "category": post.get("category", category),
                "created": post.get("created", ""),
            }
            if new_pinned:
                kwargs["pinned"] = True
            new_post = frontmatter.Post(post.content, **kwargs)
            md_file.write_text(frontmatter.dumps(new_post), encoding="utf-8")
            action = "pin" if new_pinned else "unpin"
            self._commit_and_push(f"docs: {action} '{post.get('title', slug)}'")
        cache.invalidate_repo(self.repo_id)
        return {"repo_id": self.repo_id, "slug": slug, "category": category, "pinned": new_pinned}

    def delete_entry(self, category: str, slug: str) -> bool:
        git_path = f"knowledge/{category}/{slug}.md"
        content = self.read_committed(git_path)
        if content is None:
            return False
        title = frontmatter.loads(content.decode("utf-8")).get("title", slug)
        with self.write_lock():
            self._pull()
            md_file = self.knowledge_path / category / f"{slug}.md"
            if not md_file.exists():
                return False
            md_file.unlink()
            att_dir = self._attachment_dir(category, slug)
            if att_dir.is_dir():
                shutil.rmtree(att_dir)
            cat_dir = self.knowledge_path / category
            if cat_dir.is_dir() and not any(cat_dir.iterdir()):
                cat_dir.rmdir()
            self._commit_and_push(f"docs: remove '{title}' from {category}")
        cache.invalidate_repo(self.repo_id)
        return True

    def repo_health(self) -> dict:
        """Return quick health stats for this repo (no remote call for file/commit counts)."""
        result: dict = {
            "repo_id": self.repo_id,
            "last_commit_ts": None,
            "file_count": 0,
            "commits_7d": 0,
            "reachable": False,
            "ok": False,
        }
        try:
            r = subprocess.run(
                ["git", "log", "-1", "--format=%ct"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                result["last_commit_ts"] = int(r.stdout.strip())

            r = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", "HEAD"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=5,
            )
            if r.returncode == 0:
                result["file_count"] = len([ln for ln in r.stdout.splitlines() if ln.strip()])

            r = subprocess.run(
                ["git", "log", "--since=7.days", "--oneline"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=5,
            )
            if r.returncode == 0:
                result["commits_7d"] = len([ln for ln in r.stdout.splitlines() if ln.strip()])

            r = subprocess.run(
                ["git", "ls-remote", "--heads", self._effective_url()],
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=6,
            )
            result["reachable"] = r.returncode == 0
            result["ok"] = True
        except subprocess.TimeoutExpired:
            result["reachable"] = False
        except Exception:
            pass
        return result

    def cleanup(self):
        for path in [self._ssh_key_file, self._ca_cert_file, self._askpass_file]:
            if path:
                try:
                    Path(path).unlink()
                except Exception:
                    pass
        if self._gpg_home:
            try:
                # Kill gpg-agent for this homedir before removing
                subprocess.run(
                    ["gpgconf", "--homedir", self._gpg_home, "--kill", "gpg-agent"],
                    capture_output=True,
                )
                shutil.rmtree(self._gpg_home, ignore_errors=True)
            except Exception:
                pass


REPO_RETRY_INTERVAL_SECONDS = int(os.environ.get("REPO_RETRY_INTERVAL_SECONDS", "30"))


class MultiRepoStorage:
    """Manages multiple GitStorage instances, routes reads/writes by repo_id."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._stores: dict[str, GitStorage] = {}
        # repo_id -> {"repo": dict, "error": str, "network": bool, "last_attempt": float}
        # Repos that failed to init (e.g. network unreachable) land here instead of
        # being dropped silently — retry_failed() re-attempts them periodically so
        # the app self-heals once connectivity returns, without a manual sync/restart.
        self._failed: dict[str, dict] = {}
        for repo in cfg.get("repos", []):
            if not repo.get("enabled", True):
                continue
            self._init_repo(repo)
        self._cleanup_orphaned_repos(cfg)

    def _global_settings(self) -> dict:
        return {
            "git_user_name": self._cfg.get("git_user_name", "Daily Helper"),
            "git_user_email": self._cfg.get("git_user_email", "daily@helper.local"),
        }

    def _init_repo(self, repo: dict) -> bool:
        """Try to init a single repo's GitStorage. Records failures in self._failed."""
        rid = repo["id"]
        repo_settings = dict(repo)
        repo_settings["_global"] = self._global_settings()
        try:
            self._stores[rid] = GitStorage(
                repo_id=rid,
                repo_url=repo["url"],
                settings=repo_settings,
            )
            self._failed.pop(rid, None)
            return True
        except GitStorageError as e:
            logger.error("Failed to init repo %s (%s): %s", rid, repo.get("name"), e)
            self._failed[rid] = {
                "repo": repo,
                "error": str(e),
                "network": _is_network_error(str(e)),
                "last_attempt": time.monotonic(),
            }
            return False

    def retry_failed(self) -> None:
        """Re-attempt init for repos that previously failed (e.g. network down).

        Called periodically from the background maintenance loop so a repo
        that failed to clone at startup (VPN not connected yet, DNS not
        ready, ...) comes online on its own once the network recovers.
        """
        now = time.monotonic()
        for rid in list(self._failed):
            info = self._failed[rid]
            if now - info["last_attempt"] < REPO_RETRY_INTERVAL_SECONDS:
                continue
            if self._init_repo(info["repo"]):
                logger.info("Repo %s recovered after retry", rid)

    def degraded_repos(self) -> list[dict]:
        """Repos currently failed/unreachable, for status banners."""
        return [
            {
                "id": rid,
                "name": info["repo"].get("name", rid),
                "error": info["error"],
                "network": info["network"],
                "last_attempt": info["last_attempt"],
            }
            for rid, info in self._failed.items()
        ]

    def _cleanup_orphaned_repos(self, cfg: dict) -> None:
        """Remove cloned repos that are no longer in the config."""
        repos_root = DATA_DIR / "repos"
        if not repos_root.is_dir():
            return
        known_ids = {r["id"] for r in cfg.get("repos", [])}
        for entry in repos_root.iterdir():
            if entry.is_dir() and entry.name not in known_ids:
                try:
                    shutil.rmtree(entry)
                    logger.info("Cleaned up orphaned repo clone: %s", entry.name)
                except Exception as e:
                    logger.warning("Failed to remove orphaned repo %s: %s", entry.name, e)

    def get_store(self, repo_id: str) -> GitStorage | None:
        return self._stores.get(repo_id)

    def writable_repos(self) -> list[dict]:
        cfg = self._cfg
        return [r for r in cfg.get("repos", []) if r.get("permissions", {}).get("write") and r["id"] in self._stores]

    def get_categories(self) -> list[dict]:
        """Returns list of {repo_id, repo_name, category}."""
        result = []
        repo_map = {r["id"]: r.get("name", r["id"]) for r in self._cfg.get("repos", [])}
        for rid, store in self._stores.items():
            try:
                for cat in store.get_categories():
                    result.append(
                        {
                            "repo_id": rid,
                            "repo_name": repo_map.get(rid, rid),
                            "category": cat,
                        }
                    )
            except Exception as e:
                logger.warning("get_categories failed for repo %s: %s", rid, e)
        return result

    def get_entries(self, repo_id: str | None = None, category: str | None = None) -> list[dict]:
        if repo_id:
            store = self._stores.get(repo_id)
            return store.get_entries(category) if store else []
        entries = []
        for store in self._stores.values():
            try:
                entries.extend(store.get_entries(category))
            except Exception as e:
                logger.warning("get_entries failed for repo %s: %s", store.repo_id, e)
        return entries

    def get_entry(self, repo_id: str, category: str, slug: str) -> dict | None:
        store = self._stores.get(repo_id)
        return store.get_entry(category, slug) if store else None

    def search(self, query: str, category: str = "") -> list[dict]:
        results = []
        for store in self._stores.values():
            try:
                results.extend(store.search(query))
            except Exception as e:
                logger.warning("search failed for repo %s: %s", store.repo_id, e)
        if category:
            results = [r for r in results if r.get("category") == category]
        return results

    def save_entry(self, repo_id: str, category: str, title: str, content: str) -> dict:
        store = self._stores.get(repo_id)
        if not store:
            raise GitStorageError(f"Repo not found or not initialized: {repo_id}")
        return store.save_entry(category, title, content)

    def update_entry(self, repo_id: str, category: str, slug: str, title: str, content: str) -> dict:
        store = self._stores.get(repo_id)
        if not store:
            raise GitStorageError(f"Repo not found or not initialized: {repo_id}")
        return store.update_entry(category, slug, title, content)

    def toggle_pin(self, repo_id: str, category: str, slug: str) -> dict:
        store = self._stores.get(repo_id)
        if not store:
            raise GitStorageError(f"Repo not found or not initialized: {repo_id}")
        return store.toggle_pin(category, slug)

    def delete_entry(self, repo_id: str, category: str, slug: str) -> bool:
        store = self._stores.get(repo_id)
        return store.delete_entry(category, slug) if store else False

    def get_history(self, since_dt: "datetime | None" = None, limit: int = 200) -> list[dict]:
        """Aggregate history across all repos, sorted by timestamp descending."""
        all_commits: list[dict] = []
        for store in self._stores.values():
            all_commits.extend(store.get_history(since_dt=since_dt, limit=limit))
        all_commits.sort(key=lambda c: c["ts"], reverse=True)
        return all_commits[:limit]

    def get_recent_activity(self, limit: int = 10) -> dict:
        added_all: list[dict] = []
        modified_all: list[dict] = []
        seen_added: set[str] = set()
        seen_modified: set[str] = set()
        merged = self.get_history(limit=limit * 8)
        for commit in merged:
            for ch in commit["changes"]:
                key = f"{ch['repo_id']}/{ch['category']}/{ch['slug']}"
                if ch["action"] == "A" and key not in seen_added:
                    seen_added.add(key)
                    added_all.append({**ch, "ts": commit["ts"]})
                elif ch["action"] == "M" and key not in seen_modified:
                    seen_modified.add(key)
                    modified_all.append({**ch, "ts": commit["ts"]})
                if len(added_all) >= limit and len(modified_all) >= limit:
                    break
            if len(added_all) >= limit and len(modified_all) >= limit:
                break
        return {"added": added_all[:limit], "modified": modified_all[:limit]}

    def list_attachments(self, repo_id: str, category: str, slug: str) -> list[str]:
        store = self._stores.get(repo_id)
        return store.list_attachments(category, slug) if store else []

    def save_attachment(self, repo_id: str, category: str, slug: str, filename: str, data: bytes) -> None:
        store = self._stores.get(repo_id)
        if not store:
            raise GitStorageError(f"Repo not found: {repo_id}")
        store.save_attachment(category, slug, filename, data)

    def get_attachment(self, repo_id: str, category: str, slug: str, filename: str) -> bytes | None:
        store = self._stores.get(repo_id)
        return store.get_attachment(category, slug, filename) if store else None

    def delete_attachment(self, repo_id: str, category: str, slug: str, filename: str) -> bool:
        store = self._stores.get(repo_id)
        return store.delete_attachment(category, slug, filename) if store else False

    def repo_health(self, repo_id: str) -> dict:
        store = self._stores.get(repo_id)
        if not store:
            return {"repo_id": repo_id, "ok": False, "error": "not initialized"}
        return store.repo_health()

    def repos_status(self) -> list[dict]:
        """Return online/pending status for all repos (no remote call)."""
        repo_map = {r["id"]: r.get("name", r["id"]) for r in self._cfg.get("repos", [])}
        return [
            {
                "id": rid,
                "name": repo_map.get(rid, rid),
                "pending_push": store.has_pending_push,
            }
            for rid, store in self._stores.items()
        ]

    def retry_all_pending(self) -> None:
        """Attempt to push for every repo that has queued offline changes."""
        for store in self._stores.values():
            if store.has_pending_push:
                try:
                    store.retry_pending_push()
                except Exception as exc:
                    logger.debug("Retry push error for %s: %s", store.repo_id, exc)

    def cleanup(self):
        for store in self._stores.values():
            store.cleanup()
        self._stores.clear()
