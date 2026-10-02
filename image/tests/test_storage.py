"""Tests for storage helper functions (no git, no filesystem required)."""

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.storage import GitStorage, GitStorageError, MultiRepoStorage

# ── _slug ──────────────────────────────────────────────────────────────────


class TestSlug:
    """_slug() turns a title into a URL-safe filename stem."""

    def _slug(self, title):
        # Call via the static-ish method on a dummy instance without __init__
        return GitStorage._slug(None, title)

    def test_basic(self):
        assert self._slug("My Title") == "my-title"

    def test_lowercase(self):
        assert self._slug("UPPER CASE") == "upper-case"

    def test_special_chars_stripped(self):
        assert self._slug("Hello, World!") == "hello-world"

    def test_multiple_spaces_and_dashes(self):
        assert self._slug("foo  --  bar") == "foo-bar"

    def test_leading_trailing_dashes(self):
        assert self._slug("--hello--") == "hello"

    def test_unicode_letters_kept(self):
        result = self._slug("Ärger mit Ümlaut")
        assert result  # must not be empty
        assert "-" in result or result.isalnum()

    def test_empty_string_fallback(self):
        assert self._slug("") == "entry"

    def test_only_special_chars_fallback(self):
        assert self._slug("!!!") == "entry"

    def test_numbers_kept(self):
        assert self._slug("Python 3.12") == "python-312"


# ── _validate_category ─────────────────────────────────────────────────────


class TestRejectTraversal:
    """_reject_traversal() promises to validate *a single path component*.

    A value containing a separator satisfies neither that promise nor the
    caller's expectation: `save_attachment(filename="a/b")` would quietly
    create a subdirectory instead of being refused. No escape from the repo
    is possible either way — this closes the gap between what the function
    documents and what it enforces.
    """

    def test_plain_name_accepted(self):
        GitStorage._reject_traversal("notes.md", "Filename")

    def test_separator_rejected(self):
        with pytest.raises(GitStorageError):
            GitStorage._reject_traversal("sub/notes.md", "Filename")

    def test_nested_separator_rejected(self):
        with pytest.raises(GitStorageError):
            GitStorage._reject_traversal("a/b/c", "Filename")

    def test_traversal_still_rejected(self):
        for bad in ("../etc", "/etc/passwd", "..", "."):
            with pytest.raises(GitStorageError):
                GitStorage._reject_traversal(bad, "Filename")


class TestValidateCategory:
    """_validate_category() must block path traversal and empty names."""

    def _validate(self, cat):
        GitStorage._validate_category(cat)

    def test_valid_simple(self):
        self._validate("Linux-Basics")

    def test_valid_with_numbers(self):
        self._validate("Docker-2024")

    def test_empty_raises(self):
        with pytest.raises(GitStorageError):
            self._validate("")

    def test_whitespace_only_raises(self):
        with pytest.raises(GitStorageError):
            self._validate("   ")

    def test_dotdot_raises(self):
        with pytest.raises(GitStorageError):
            self._validate("../etc")

    def test_dotdot_deep_raises(self):
        with pytest.raises(GitStorageError):
            self._validate("foo/../../etc/passwd")

    def test_absolute_path_raises(self):
        with pytest.raises(GitStorageError):
            self._validate("/etc/passwd")

    def test_dot_alone_raises(self):
        with pytest.raises(GitStorageError):
            self._validate(".")


# ── Pull throttling ────────────────────────────────────────────────────────


class TestPullThrottling:
    """_pull() must skip git pull when called within the throttle window."""

    def _make_store(self):
        """Return a GitStorage instance without running __init__."""
        store = GitStorage.__new__(GitStorage)
        store._last_pull = 0.0
        return store

    def test_pull_runs_when_never_called(self):

        store = self._make_store()
        ran = []

        def fake_run(*args, **kwargs):
            ran.append(args)

        store._run = fake_run
        # PULL_THROTTLE_SECONDS defaults to 300; _last_pull=0 is far in the past
        with __import__("unittest.mock", fromlist=["patch"]).patch("core.storage.PULL_THROTTLE_SECONDS", 300):
            store._pull()

        assert ran, "_run should have been called"

    def test_pull_skipped_within_throttle_window(self):
        import time

        store = self._make_store()
        store._last_pull = time.monotonic()  # just pulled
        ran = []

        def fake_run(*args, **kwargs):
            ran.append(args)

        store._run = fake_run

        from core import storage as _storage_module

        original = _storage_module.PULL_THROTTLE_SECONDS
        _storage_module.PULL_THROTTLE_SECONDS = 300
        try:
            store._pull()
        finally:
            _storage_module.PULL_THROTTLE_SECONDS = original

        assert not ran, "_run must not be called within throttle window"

    def test_pull_runs_after_throttle_elapsed(self):
        import time

        store = self._make_store()
        store._last_pull = time.monotonic() - 400  # 400s ago > 300s throttle
        ran = []

        def fake_run(*args, **kwargs):
            ran.append(args)

        store._run = fake_run

        from core import storage as _storage_module

        original = _storage_module.PULL_THROTTLE_SECONDS
        _storage_module.PULL_THROTTLE_SECONDS = 300
        try:
            store._pull()
        finally:
            _storage_module.PULL_THROTTLE_SECONDS = original

        assert ran, "_run should be called after throttle window elapsed"

    def test_last_pull_updated_on_success(self):
        import time

        store = self._make_store()
        store._last_pull = 0.0

        def fake_run(*args, **kwargs):
            pass

        store._run = fake_run

        from core import storage as _storage_module

        original = _storage_module.PULL_THROTTLE_SECONDS
        _storage_module.PULL_THROTTLE_SECONDS = 300
        before = time.monotonic()
        try:
            store._pull()
        finally:
            _storage_module.PULL_THROTTLE_SECONDS = original

        assert store._last_pull >= before

    def test_last_pull_not_updated_on_error(self):
        store = self._make_store()
        store._last_pull = 0.0

        def fake_run(*args, **kwargs):
            raise GitStorageError("network error")

        store._run = fake_run

        from core import storage as _storage_module

        original = _storage_module.PULL_THROTTLE_SECONDS
        _storage_module.PULL_THROTTLE_SECONDS = 300
        try:
            store._pull()  # must not raise
        finally:
            _storage_module.PULL_THROTTLE_SECONDS = original

        assert store._last_pull == 0.0


# ── MultiRepoStorage.search category filter ────────────────────────────────


class TestMultiRepoSearchCategoryFilter:
    """MultiRepoStorage.search() must filter results by category when specified."""

    def _make_multi(self, search_results):
        """Build a MultiRepoStorage-like object with a fake store."""
        from core.storage import MultiRepoStorage

        multi = MultiRepoStorage.__new__(MultiRepoStorage)

        class FakeStore:
            repo_id = "repo1"

            def search(self, query):
                return search_results

        multi._stores = {"repo1": FakeStore()}
        multi._cfg = {"repos": []}
        return multi

    def test_no_filter_returns_all(self):

        results = [
            {"repo_id": "r1", "title": "A", "category": "Linux"},
            {"repo_id": "r1", "title": "B", "category": "Docker"},
        ]
        multi = self._make_multi(results)
        assert multi.search("foo") == results

    def test_filter_by_category_keeps_matching(self):

        results = [
            {"repo_id": "r1", "title": "A", "category": "Linux"},
            {"repo_id": "r1", "title": "B", "category": "Docker"},
        ]
        multi = self._make_multi(results)
        out = multi.search("foo", category="Linux")
        assert len(out) == 1
        assert out[0]["title"] == "A"

    def test_filter_by_category_excludes_others(self):

        results = [
            {"repo_id": "r1", "title": "A", "category": "Linux"},
            {"repo_id": "r1", "title": "B", "category": "Docker"},
        ]
        multi = self._make_multi(results)
        out = multi.search("foo", category="Kubernetes")
        assert out == []

    def test_empty_category_returns_all(self):

        results = [
            {"repo_id": "r1", "title": "A", "category": "Linux"},
        ]
        multi = self._make_multi(results)
        assert multi.search("foo", category="") == results


# ── Push conflict detection ────────────────────────────────────────────────


class TestPushConflictDetection:
    """_commit_and_push() must raise a human-readable error when push is rejected."""

    def _make_store(self):
        store = GitStorage.__new__(GitStorage)
        store.local_path = __import__("pathlib").Path("/tmp/fake-repo")
        store._gpg_key_id = None
        store._settings = {}
        store._push_retry_count = 0
        store.repo_id = "test-repo"
        return store

    def _make_push_result(self, returncode, stderr):
        import subprocess

        r = subprocess.CompletedProcess(args=[], returncode=returncode)
        r.stdout = ""
        r.stderr = stderr
        return r

    def _fake_run_with_staged_changes(self, *args, **kwargs):
        """Simulate git add + git diff showing staged changes (rc=1) + git commit ok.
        args is a flat tuple like ("git", "diff", "--cached", ...).
        rc=1 for diff means staged changes exist → push will run.
        """
        import subprocess

        rc = 1 if "diff" in args else 0
        r = subprocess.CompletedProcess(args=[], returncode=rc)
        r.stdout = ""
        r.stderr = ""
        return r

    def test_rejected_raises_human_message(self):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()
        store._run = self._fake_run_with_staged_changes
        store._build_env = lambda: {}

        push_result = subprocess.CompletedProcess(args=[], returncode=1)
        push_result.stdout = ""
        push_result.stderr = "! [rejected] main -> main (non-fast-forward)"

        with patch("core.storage.subprocess.run", return_value=push_result):
            with pytest.raises(GitStorageError) as exc_info:
                store._commit_and_push("docs: test")

        assert "Push rejected" in str(exc_info.value)
        assert "remote" in str(exc_info.value).lower()

    def test_fetch_first_raises_human_message(self):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()
        store._run = self._fake_run_with_staged_changes
        store._build_env = lambda: {}

        push_result = subprocess.CompletedProcess(args=[], returncode=1)
        push_result.stdout = ""
        push_result.stderr = (
            "error: failed to push some refs\n"
            "hint: Updates were rejected because the remote contains work that you do\n"
            "hint: not have locally. hint: 'git pull ...'\n"
        )

        with patch("core.storage.subprocess.run", return_value=push_result):
            with pytest.raises(GitStorageError) as exc_info:
                store._commit_and_push("docs: test")

        assert "Push rejected" in str(exc_info.value)

    def test_other_push_error_raises_raw_message(self):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()
        store._run = self._fake_run_with_staged_changes
        store._build_env = lambda: {}

        push_result = subprocess.CompletedProcess(args=[], returncode=128)
        push_result.stdout = ""
        # Use a non-network error (permission denied is not a connectivity issue)
        push_result.stderr = "fatal: remote: Permission denied to user/repo.git"

        with patch("core.storage.subprocess.run", return_value=push_result):
            with pytest.raises(GitStorageError) as exc_info:
                store._commit_and_push("docs: test")

        assert "Git error" in str(exc_info.value)
        assert "Push rejected" not in str(exc_info.value)

    def test_network_error_queues_pending_push(self, tmp_path):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()
        store.repo_id = "test-repo"
        store._run = self._fake_run_with_staged_changes
        store._build_env = lambda: {}
        store.local_path = tmp_path

        push_result = subprocess.CompletedProcess(args=[], returncode=128)
        push_result.stdout = ""
        push_result.stderr = "fatal: unable to access 'https://...': Could not resolve host: gitea.example.com"

        with patch("core.storage.subprocess.run", return_value=push_result):
            # Should NOT raise — queued for offline retry
            store._commit_and_push("docs: test")

        assert store.has_pending_push


# ── toggle_pin ─────────────────────────────────────────────────────────────


class TestTogglePin:
    """toggle_pin() must flip the pinned frontmatter flag and commit."""

    def _make_store_with_file(self, tmp_path, pinned=False):
        """Create a GitStorage stub with a real markdown file."""
        import frontmatter as fm

        store = GitStorage.__new__(GitStorage)
        store.repo_id = "repo1"
        store.local_path = tmp_path
        store._write_lock = threading.RLock()

        # Knowledge entries live in knowledge/ subdir
        cat_dir = tmp_path / "knowledge" / "Linux"
        cat_dir.mkdir(parents=True)
        kwargs = {"title": "My Entry", "category": "Linux", "created": "2025-01-01"}
        if pinned:
            kwargs["pinned"] = True
        post = fm.Post("Some content.", **kwargs)
        (cat_dir / "my-entry.md").write_text(fm.dumps(post), encoding="utf-8")

        commits = []
        store._commit_and_push = lambda msg: commits.append(msg)
        store._commits = commits

        # Provide filesystem-backed read_committed for tests (no real git repo)
        def _read_committed(path: str):
            full = tmp_path / path
            try:
                return full.read_bytes()
            except FileNotFoundError:
                return None

        store.read_committed = _read_committed

        store._cache_invalidated = []
        return store

    def test_pin_sets_pinned_true(self, tmp_path):
        store = self._make_store_with_file(tmp_path, pinned=False)
        import unittest.mock as mock

        with mock.patch("core.cache.invalidate_repo"):
            result = store.toggle_pin("Linux", "my-entry")
        assert result["pinned"] is True

    def test_unpin_removes_pinned_flag(self, tmp_path):
        import frontmatter as fm

        store = self._make_store_with_file(tmp_path, pinned=True)
        import unittest.mock as mock

        with mock.patch("core.cache.invalidate_repo"):
            result = store.toggle_pin("Linux", "my-entry")
        assert result["pinned"] is False
        # Flag must not appear in written file
        post = fm.load(store.knowledge_path / "Linux" / "my-entry.md")
        assert not post.get("pinned", False)

    def test_pin_preserves_content_and_title(self, tmp_path):
        import frontmatter as fm

        store = self._make_store_with_file(tmp_path, pinned=False)
        import unittest.mock as mock

        with mock.patch("core.cache.invalidate_repo"):
            store.toggle_pin("Linux", "my-entry")
        post = fm.load(store.knowledge_path / "Linux" / "my-entry.md")
        assert post.get("title") == "My Entry"
        assert post.content == "Some content."

    def test_pin_nonexistent_raises(self, tmp_path):
        store = self._make_store_with_file(tmp_path, pinned=False)
        with pytest.raises(GitStorageError):
            store.toggle_pin("Linux", "does-not-exist")

    def test_pin_commit_message_contains_action(self, tmp_path):
        store = self._make_store_with_file(tmp_path, pinned=False)
        import unittest.mock as mock

        with mock.patch("core.cache.invalidate_repo"):
            store.toggle_pin("Linux", "my-entry")
        assert any("pin" in msg for msg in store._commits)


# ── Pagination helper ──────────────────────────────────────────────────────


class TestPaginationMath:
    """Verify the pagination math used in category_view."""

    def _paginate(self, items, page, page_size=20):
        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        return items[(page - 1) * page_size : page * page_size], page, total_pages

    def test_single_page(self):
        items = list(range(5))
        result, p, tp = self._paginate(items, 1)
        assert result == items
        assert p == 1
        assert tp == 1

    def test_exactly_one_page_size(self):
        items = list(range(20))
        result, p, tp = self._paginate(items, 1)
        assert len(result) == 20
        assert tp == 1

    def test_two_pages(self):
        items = list(range(25))
        page1, _, tp = self._paginate(items, 1)
        page2, _, _ = self._paginate(items, 2)
        assert len(page1) == 20
        assert len(page2) == 5
        assert tp == 2

    def test_page_clamp_low(self):
        items = list(range(25))
        _, p, _ = self._paginate(items, 0)
        assert p == 1

    def test_page_clamp_high(self):
        items = list(range(25))
        _, p, _ = self._paginate(items, 999)
        assert p == 2

    def test_empty_list_returns_one_page(self):
        _, p, tp = self._paginate([], 1)
        assert p == 1
        assert tp == 1


# ── _sanitize_git_error ────────────────────────────────────────────────────


class TestSanitizeGitError:
    """Credentials embedded in URLs must be stripped from error messages."""

    def _sanitize(self, msg):
        from core.storage import _sanitize_git_error

        return _sanitize_git_error(msg)

    def test_strips_pat_from_https_url(self):
        msg = "Git error: fatal: repository 'https://oauth2:glpat-abc123@gitea.example.com/org/repo.git/' not found"
        result = self._sanitize(msg)
        assert "glpat-abc123" not in result
        assert "***@" in result

    def test_strips_basic_password_from_url(self):
        msg = "Clone failed: https://user:s3cr3t@gitea.example.com/repo.git returned 403"
        result = self._sanitize(msg)
        assert "s3cr3t" not in result
        assert "***@" in result

    def test_leaves_clean_url_unchanged(self):
        msg = "Git error: fatal: not a git repository"
        assert self._sanitize(msg) == msg

    def test_leaves_ssh_url_unchanged(self):
        msg = "Git error: ssh://git@gitea.example.com:2222/org/repo.git connection refused"
        result = self._sanitize(msg)
        assert result == msg

    def test_multiple_credentials_stripped(self):
        msg = "https://a:pass1@host.com and https://b:pass2@host.com"
        result = self._sanitize(msg)
        assert "pass1" not in result
        assert "pass2" not in result


# ── _build_env (CA cert) ───────────────────────────────────────────────────


class TestBuildEnvCaCert:
    """GIT_SSL_CAINFO must be set for any auth mode when a CA cert is configured."""

    def _make_storage(self, auth_mode, ca_cert=None):
        import tempfile
        from unittest.mock import patch

        settings = {
            "auth_mode": auth_mode,
            "ca_cert": ca_cert,
            "_global": {},
        }
        with patch.object(__import__("core.storage", fromlist=["GitStorage"]).GitStorage, "_ensure_repo"):
            with patch.object(__import__("core.storage", fromlist=["GitStorage"]).GitStorage, "_setup_credentials"):
                from core.storage import GitStorage as _GS

                s = _GS.__new__(_GS)
                s.repo_id = "test"
                s.repo_url = "https://example.com/repo.git"
                s.local_path = __import__("pathlib").Path("/tmp/test-repo")
                s._settings = settings
                s._ssh_key_file = None
                s._askpass_file = None
                s._gpg_home = None
                s._gpg_key_id = None
                s._last_pull = 0.0
                if ca_cert:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w")
                    tmp.write(ca_cert)
                    tmp.flush()
                    s._ca_cert_file = tmp.name
                else:
                    s._ca_cert_file = None
                return s

    def test_ca_cert_set_for_pat(self):
        s = self._make_storage("pat", ca_cert="-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        env = s._build_env()
        assert "GIT_SSL_CAINFO" in env
        assert env["GIT_SSL_CAINFO"] == s._ca_cert_file

    def test_ca_cert_set_for_basic(self):
        s = self._make_storage("basic", ca_cert="-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        env = s._build_env()
        assert "GIT_SSL_CAINFO" in env
        assert env["GIT_SSL_CAINFO"] == s._ca_cert_file

    def test_ca_cert_not_set_when_absent(self):
        s = self._make_storage("basic", ca_cert=None)
        env = s._build_env()
        assert "GIT_SSL_CAINFO" not in env

    def test_ca_cert_set_for_none_auth(self):
        s = self._make_storage("none", ca_cert="-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
        env = s._build_env()
        assert "GIT_SSL_CAINFO" in env


class TestBuildEnvIdentity:
    """Per-repo git identity must override global defaults."""

    def _make_storage(
        self,
        repo_name="",
        repo_email="",
        global_name="Global User",
        global_email="global@example.com",
    ):
        from unittest.mock import patch

        settings = {
            "auth_mode": "none",
            "git_user_name": repo_name,
            "git_user_email": repo_email,
            "_global": {
                "git_user_name": global_name,
                "git_user_email": global_email,
            },
        }
        with patch.object(__import__("core.storage", fromlist=["GitStorage"]).GitStorage, "_ensure_repo"):
            with patch.object(__import__("core.storage", fromlist=["GitStorage"]).GitStorage, "_setup_credentials"):
                from core.storage import GitStorage as _GS

                s = _GS.__new__(_GS)
                s.repo_id = "test"
                s.repo_url = "https://example.com/repo.git"
                s.local_path = __import__("pathlib").Path("/tmp/test-repo")
                s._settings = settings
                s._ssh_key_file = None
                s._ca_cert_file = None
                s._askpass_file = None
                s._gpg_home = None
                s._gpg_key_id = None
                s._last_pull = 0.0
                return s

    def test_global_identity_used_when_repo_empty(self):
        s = self._make_storage()
        env = s._build_env()
        assert env["GIT_AUTHOR_NAME"] == "Global User"
        assert env["GIT_AUTHOR_EMAIL"] == "global@example.com"

    def test_repo_identity_overrides_global(self):
        s = self._make_storage(repo_name="Alice", repo_email="alice@example.com")
        env = s._build_env()
        assert env["GIT_AUTHOR_NAME"] == "Alice"
        assert env["GIT_COMMITTER_NAME"] == "Alice"
        assert env["GIT_AUTHOR_EMAIL"] == "alice@example.com"

    def test_partial_override_falls_back_to_global(self):
        # Only name set — email falls back to global
        s = self._make_storage(repo_name="Alice", repo_email="")
        env = s._build_env()
        assert env["GIT_AUTHOR_NAME"] == "Alice"
        assert env["GIT_AUTHOR_EMAIL"] == "global@example.com"

    def test_gnupghome_set_when_gpg_configured(self):
        s = self._make_storage()
        s._gpg_home = "/tmp/gpg-test"
        env = s._build_env()
        assert env["GNUPGHOME"] == "/tmp/gpg-test"

    def test_gnupghome_not_set_when_no_gpg(self):
        s = self._make_storage()
        env = s._build_env()
        assert "GNUPGHOME" not in env


# ── list_committed uses HEAD ────────────────────────────────────────────────


class TestListCommittedUsesHEAD:
    """list_committed must read from HEAD, not origin/main."""

    def _make_store(self):
        store = GitStorage.__new__(GitStorage)
        store.repo_id = "test-repo"
        store._last_pull = 0.0
        store._settings = {}
        store.local_path = "/tmp/fake"
        store._build_env = lambda: {}
        store._ensure_fetched = lambda: None
        return store

    def test_git_command_targets_head(self):
        from unittest.mock import MagicMock, patch

        store = self._make_store()

        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = "notes/abc.yaml\n"
            return r

        with patch("core.storage.subprocess.run", side_effect=fake_run):
            with patch("core.cache.get", return_value=None):
                with patch("core.cache.set"):
                    store.list_committed("notes")

        assert captured, "subprocess.run should have been called"
        git_cmd = captured[0]
        assert "HEAD" in git_cmd, f"Expected HEAD in git command, got: {git_cmd}"
        assert "origin/main" not in git_cmd, "Must not use origin/main"

    def test_cache_invalidated_after_commit(self):
        """invalidate_repo is called after commit, before push attempt."""
        from unittest.mock import MagicMock, patch

        store = GitStorage.__new__(GitStorage)
        store.local_path = "/tmp/fake-repo"
        store._gpg_key_id = None
        store._settings = {}
        store._push_retry_count = 0
        store.repo_id = "test-repo"
        store._build_env = lambda: {}

        invalidated = []

        def fake_run(*args, **kwargs):
            r = MagicMock()
            # args is ("git", "diff", ...) — returncode 1 for diff means staged changes exist
            r.returncode = 1 if "diff" in args else 0
            r.stdout = ""
            r.stderr = ""
            return r

        push_result = MagicMock()
        push_result.returncode = 0
        push_result.stdout = ""
        push_result.stderr = ""

        store._run = fake_run

        with patch("core.storage.cache.invalidate_repo", side_effect=lambda rid: invalidated.append(rid)):
            with patch("core.storage.subprocess.run", return_value=push_result):
                store._commit_and_push("test: commit")

        assert "test-repo" in invalidated, "cache must be invalidated after commit"


# ── Attachments — path traversal protection (CONTENT-09) ────────────────────


class TestAttachmentPathTraversal:
    """save/get/delete_attachment must reject traversal in category/slug/filename
    at the storage layer itself — not just rely on router-side sanitizing like
    knowledge/router.py's _safe_filename (defense in depth)."""

    def _make_store(self, tmp_path):
        store = GitStorage.__new__(GitStorage)
        store.repo_id = "test-repo"
        store.local_path = tmp_path
        store._last_pull = 0.0
        store._write_lock = threading.RLock()
        store._pull = lambda: None
        store._commit_and_push = lambda msg: None
        return store

    def test_save_get_delete_roundtrip(self, tmp_path):
        from unittest.mock import patch

        store = self._make_store(tmp_path)
        with patch("core.storage.cache.invalidate_repo"):
            store.save_attachment("howto", "deploy", "notes.txt", b"hello")
            assert store.get_attachment("howto", "deploy", "notes.txt") == b"hello"
            assert "notes.txt" in store.list_attachments("howto", "deploy")
            assert store.delete_attachment("howto", "deploy", "notes.txt") is True
        assert store.get_attachment("howto", "deploy", "notes.txt") is None

    def test_save_attachment_rejects_traversal_category(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(GitStorageError):
            store.save_attachment("../../etc", "deploy", "notes.txt", b"x")

    def test_save_attachment_rejects_traversal_slug(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(GitStorageError):
            store.save_attachment("howto", "..", "notes.txt", b"x")

    def test_save_attachment_rejects_traversal_filename(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(GitStorageError):
            store.save_attachment("howto", "deploy", "../../../secret.txt", b"x")

    def test_get_attachment_rejects_traversal_filename(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(GitStorageError):
            store.get_attachment("howto", "deploy", "../secret.txt")

    def test_delete_attachment_rejects_traversal_filename(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(GitStorageError):
            store.delete_attachment("howto", "deploy", "../secret.txt")

    def test_traversal_never_touches_files_outside_repo(self, tmp_path):
        """End-to-end: a rejected attachment write must leave the filesystem untouched."""
        outside = tmp_path.parent / "outside-secret.txt"
        outside.write_text("original")

        store = self._make_store(tmp_path)
        with pytest.raises(GitStorageError):
            store.save_attachment("howto", "..", "../outside-secret.txt", b"pwned")

        assert outside.read_text() == "original"


# ── MultiRepoStorage — failed repo retry ────────────────────────────────────


class TestMultiRepoStorageRetryFailed:
    """Repos that fail to init (e.g. VPN/network down) are recorded and
    retried automatically instead of being dropped forever — this is what
    lets the app recover on its own after an outage, without a manual
    sync/flush/restart."""

    def _cfg(self):
        return {
            "repos": [
                {
                    "id": "r1",
                    "name": "Main",
                    "url": "https://git.example/r1.git",
                    "enabled": True,
                }
            ]
        }

    def test_failed_repo_recorded_not_dropped(self):
        from unittest.mock import patch

        with patch(
            "core.storage.GitStorage.__init__",
            side_effect=GitStorageError("Clone failed: Connection timed out"),
        ):
            store = MultiRepoStorage(self._cfg())

        assert store._stores == {}
        degraded = store.degraded_repos()
        assert len(degraded) == 1
        assert degraded[0]["id"] == "r1"
        assert degraded[0]["name"] == "Main"
        assert degraded[0]["network"] is True

    def test_retry_failed_recovers_once_network_is_back(self):
        from unittest.mock import patch

        with patch(
            "core.storage.GitStorage.__init__",
            side_effect=GitStorageError("Clone failed: Connection timed out"),
        ):
            store = MultiRepoStorage(self._cfg())
        assert "r1" in store._failed

        store._failed["r1"]["last_attempt"] = 0.0  # force the retry window to have elapsed

        with patch("core.storage.GitStorage.__init__", return_value=None):
            store.retry_failed()

        assert "r1" not in store._failed
        assert "r1" in store._stores

    def test_retry_failed_respects_min_interval(self):
        from unittest.mock import patch

        with patch(
            "core.storage.GitStorage.__init__",
            side_effect=GitStorageError("Clone failed: Connection timed out"),
        ):
            store = MultiRepoStorage(self._cfg())

        with patch("core.storage.GitStorage.__init__", return_value=None) as mock_init:
            store.retry_failed()  # called right away — interval has not elapsed yet

        mock_init.assert_not_called()
        assert "r1" in store._failed


# ── _revert_working_tree on failed commit ────────────────────────────────────


class TestRevertOnFailedCommit:
    """A failed `git commit` (before any commit exists) must never run
    `git reset --soft HEAD~1` — that would discard the previous, already
    -pushed commit instead of undoing the (nonexistent) new one."""

    def _make_store(self):
        store = GitStorage.__new__(GitStorage)
        store.local_path = __import__("pathlib").Path("/tmp/fake-repo")
        store._gpg_key_id = None
        store._settings = {}
        store._push_retry_count = 0
        store.repo_id = "test-repo"
        store._build_env = lambda: {}
        return store

    def test_failed_commit_does_not_reset_head(self):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()

        def fake_run(*args, check=True, timeout=None):
            if args == ("git", "add", "-A"):
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            if "diff" in args:
                return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            if "commit" in args:
                raise GitStorageError("simulated commit failure (e.g. disk full)")
            raise AssertionError(f"unexpected _run call: {args}")

        store._run = fake_run

        cleanup_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("core.storage.subprocess.run", return_value=cleanup_result) as mock_run:
            with pytest.raises(GitStorageError, match="simulated commit failure"):
                store._commit_and_push("docs: test")

        cleanup_cmds = [call.args[0] for call in mock_run.call_args_list]
        assert not any(cmd[:3] == ["git", "reset", "--soft"] for cmd in cleanup_cmds)
        assert any(cmd[:2] == ["git", "restore"] for cmd in cleanup_cmds)
        assert any(cmd[:2] == ["git", "clean"] for cmd in cleanup_cmds)

    def test_failed_push_does_reset_head(self):
        """Contrast case: once a commit exists locally but push fails for a
        non-network reason, the local-only commit must be rolled back."""
        import subprocess
        from unittest.mock import patch

        store = self._make_store()

        def fake_run(*args, check=True, timeout=None):
            if args == ("git", "add", "-A"):
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            if "diff" in args:
                return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            if "commit" in args:
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected _run call: {args}")

        store._run = fake_run

        push_result = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="fatal: remote: Permission denied"
        )
        with (
            patch("core.storage.subprocess.run", return_value=push_result) as mock_run,
            patch("core.storage.cache.invalidate_repo"),
        ):
            with pytest.raises(GitStorageError):
                store._commit_and_push("docs: test")

        cleanup_cmds = [call.args[0] for call in mock_run.call_args_list]
        assert any(cmd[:3] == ["git", "reset", "--soft"] for cmd in cleanup_cmds)


# ── read_committed / list_committed ref consistency ──────────────────────────


class TestCommittedReadRefConsistency:
    """read_committed() and list_committed() must query the same git ref.
    A mismatch (e.g. one on HEAD, one on origin/main) means a file just
    committed locally shows up in a listing but reads back as None — the
    exact bug this pair of tests guards against."""

    def _make_store(self):
        store = GitStorage.__new__(GitStorage)
        store.local_path = __import__("pathlib").Path("/tmp/fake-repo")
        store.repo_id = "test-repo"
        store._last_pull = 0.0
        store._build_env = lambda: {}
        store._ensure_fetched = lambda: None
        return store

    def test_read_committed_uses_head(self):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"content", stderr=b"")
        with (
            patch("core.storage.cache.get", return_value=None),
            patch("core.storage.cache.set"),
            patch("core.storage.subprocess.run", return_value=result) as mock_run,
        ):
            store.read_committed("notes/abc.yaml")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "show", "HEAD:notes/abc.yaml"]

    def test_list_committed_uses_head(self):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("core.storage.cache.get", return_value=None),
            patch("core.storage.cache.set"),
            patch("core.storage.subprocess.run", return_value=result) as mock_run,
        ):
            store.list_committed("notes")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "ls-tree", "--name-only", "HEAD", "notes/"]

    def test_list_committed_recursive_uses_head(self):
        import subprocess
        from unittest.mock import patch

        store = self._make_store()
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("core.storage.cache.get", return_value=None),
            patch("core.storage.cache.set"),
            patch("core.storage.subprocess.run", return_value=result) as mock_run,
        ):
            store.list_committed_recursive("notes")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "ls-tree", "-r", "--name-only", "HEAD", "notes/"]


class TestUnreadableKnowledgeEntry:
    """An entry with broken frontmatter is skipped — but never silently.

    Both listing and search used `except Exception: continue`. A single stray
    quote in the YAML header made the entry vanish from the UI with nothing in
    the log to say where it went.
    """

    GOOD = b"---\ntitle: Good entry\ncategory: ops\n---\nneedle body\n"
    BROKEN = b"---\ntitle: 'unterminated\ncategory: ops\n---\nneedle body\n"

    def _store(self):
        from core.storage import GitStorage

        store = GitStorage.__new__(GitStorage)
        store.repo_id = "r1"
        files = {"knowledge/ops/good.md": self.GOOD, "knowledge/ops/broken.md": self.BROKEN}
        store.list_committed_recursive = lambda d: list(files)
        store.read_committed = lambda p: files.get(p)
        return store

    def test_listing_logs_the_skipped_entry(self, caplog):
        with caplog.at_level("WARNING", logger="core.storage"):
            entries = self._store().get_entries()
        assert [e["title"] for e in entries] == ["Good entry"]
        assert "knowledge/ops/broken.md" in caplog.text

    def test_search_logs_the_skipped_entry(self, caplog):
        with caplog.at_level("WARNING", logger="core.storage"):
            results = self._store().search("needle")
        assert [r["title"] for r in results] == ["Good entry"]
        assert "knowledge/ops/broken.md" in caplog.text
