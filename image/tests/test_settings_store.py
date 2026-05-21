"""Tests for settings_store — migration, encryption round-trip, defaults."""

import json
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


# ── _migrate_legacy ─────────────────────────────────────────────────────────

class TestMigrateLegacy:
    """Old single-repo settings.json must be transparently upgraded."""

    def setup_method(self):
        from core import settings_store
        self.migrate = settings_store._migrate_legacy

    def test_new_format_unchanged(self):
        data = {"repos": [{"id": "abc", "url": "https://example.com"}]}
        result = self.migrate(data)
        assert result == data

    def test_old_format_creates_repos_list(self):
        old = {"repo_url": "https://gitea.example.com/owner/repo.git",
               "auth_mode": "pat", "pat": "secret",
               "git_user_name": "Alice", "git_user_email": "alice@example.com"}
        result = self.migrate(old)
        assert "repos" in result
        assert len(result["repos"]) == 1
        repo = result["repos"][0]
        assert repo["url"] == old["repo_url"]
        assert repo["auth_mode"] == "pat"
        assert repo["pat"] == "secret"

    def test_old_format_without_url_gives_empty_repos(self):
        result = self.migrate({"git_user_name": "Bob", "git_user_email": "bob@example.com"})
        assert result["repos"] == []

    def test_git_identity_preserved(self):
        old = {"repo_url": "https://example.com/r.git",
               "git_user_name": "Carol", "git_user_email": "carol@example.com"}
        result = self.migrate(old)
        assert result["git_user_name"] == "Carol"
        assert result["git_user_email"] == "carol@example.com"


# ── Encrypt / Decrypt round-trip ────────────────────────────────────────────

class TestEncryption:
    """Sensitive fields must survive an encrypt→save→load cycle."""

    def test_round_trip(self):
        from core import settings_store
        from cryptography.fernet import Fernet
        f = Fernet(Fernet.generate_key())

        original = "super-secret-value"
        encrypted = settings_store._encrypt(original, f)
        assert encrypted.startswith(settings_store.ENC_PREFIX)
        assert original not in encrypted

        decrypted = settings_store._decrypt(encrypted, f)
        assert decrypted == original

    def test_empty_string_not_encrypted(self):
        from core import settings_store
        from cryptography.fernet import Fernet
        f = Fernet(Fernet.generate_key())
        assert settings_store._encrypt("", f) == ""

    def test_decrypt_plain_value_passthrough(self):
        """Values without enc: prefix are returned as-is (backward compat)."""
        from core import settings_store
        from cryptography.fernet import Fernet
        f = Fernet(Fernet.generate_key())
        assert settings_store._decrypt("plain-text", f) == "plain-text"


# ── load() defaults ─────────────────────────────────────────────────────────

class TestLoadDefaults:
    """load() must return DEFAULTS when no settings file exists."""

    def test_returns_defaults_when_no_file(self):
        from core import settings_store
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(settings_store, "SETTINGS_PATH", Path(tmp) / "settings.json"):
                with patch.object(settings_store, "KEY_PATH", Path(tmp) / ".secret_key"):
                    result = settings_store.load()
        assert result["repos"] == []
        assert "git_user_name" in result
        assert "tls_mode" in result
        assert result["metrics_enabled"] is False


# ── Template CRUD ────────────────────────────────────────────────────────────

class TestTemplateCRUD:
    """get_templates / upsert_template / delete_template must behave correctly."""

    def setup_method(self):
        from core import settings_store
        import tempfile
        self._ss = settings_store
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._orig_sp = settings_store.SETTINGS_PATH
        self._orig_kp = settings_store.KEY_PATH
        settings_store.SETTINGS_PATH = tmp / "settings.json"
        settings_store.KEY_PATH = tmp / ".secret_key"

    def teardown_method(self):
        self._ss.SETTINGS_PATH = self._orig_sp
        self._ss.KEY_PATH = self._orig_kp
        self._tmp.cleanup()

    def test_get_templates_empty_by_default(self):
        assert self._ss.get_templates() == []

    def test_upsert_adds_template(self):
        tpl = self._ss.upsert_template({"name": "My Tpl", "content": "# Hello"})
        assert tpl["id"]
        templates = self._ss.get_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "My Tpl"

    def test_upsert_updates_existing_template(self):
        tpl = self._ss.upsert_template({"name": "Old", "content": "v1"})
        tpl_id = tpl["id"]
        self._ss.upsert_template({"id": tpl_id, "name": "New", "content": "v2"})
        templates = self._ss.get_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "New"
        assert templates[0]["content"] == "v2"

    def test_delete_template_removes_it(self):
        tpl = self._ss.upsert_template({"name": "T", "content": "c"})
        assert self._ss.delete_template(tpl["id"]) is True
        assert self._ss.get_templates() == []

    def test_delete_nonexistent_returns_false(self):
        assert self._ss.delete_template("nonexistent") is False
