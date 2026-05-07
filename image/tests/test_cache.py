"""Tests for cache module — retry logic, graceful degradation without Redis."""

import sys
import os
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core import cache


def _reset_cache_state():
    """Reset module-level state between tests."""
    cache._client = None
    cache._retry_after = 0.0


class TestCacheUnavailable:
    """When Redis is unreachable, all operations must silently do nothing."""

    def setup_method(self):
        _reset_cache_state()

    def test_get_returns_none_without_redis(self):
        with patch("core.cache._get_client", return_value=None):
            assert cache.get("any-key") is None

    def test_set_does_nothing_without_redis(self):
        with patch("core.cache._get_client", return_value=None):
            cache.set("key", {"data": 1})  # must not raise

    def test_invalidate_does_nothing_without_redis(self):
        with patch("core.cache._get_client", return_value=None):
            cache.invalidate_repo("repo123")  # must not raise

    def test_flush_does_nothing_without_redis(self):
        with patch("core.cache._get_client", return_value=None):
            cache.flush()  # must not raise

    def test_is_connected_returns_false_without_redis(self):
        with patch("core.cache._get_client", return_value=None):
            assert cache.is_connected() is False


class TestCacheRetryLogic:
    """After a connection failure, _get_client() must not retry immediately."""

    def setup_method(self):
        _reset_cache_state()

    def test_no_retry_before_interval(self):
        # Simulate a failed connection attempt setting _retry_after in the future
        cache._retry_after = time.monotonic() + 60  # retry in 60s
        cache._client = None

        with patch("core.cache._get_client", wraps=cache._get_client) as mock_get:
            result = cache._get_client()
        assert result is None  # should not attempt connection yet

    def test_retry_after_interval_elapsed(self):
        # Set retry_after in the past
        cache._retry_after = time.monotonic() - 1
        cache._client = None

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        with patch("redis.Redis.from_url", return_value=mock_redis):
            result = cache._get_client()

        assert result is mock_redis
        assert cache._client is mock_redis

    def test_failed_ping_resets_client_and_sets_retry(self):
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("connection refused")
        cache._client = mock_redis

        result = cache.is_connected()

        assert result is False
        assert cache._client is None
        assert cache._retry_after > time.monotonic()


class TestCacheGetSet:
    """get/set must serialize and deserialize values correctly."""

    def setup_method(self):
        _reset_cache_state()

    def test_get_set_round_trip(self):
        store = {}
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.get.side_effect = lambda k: store.get(k)
        mock_redis.set.side_effect = lambda k, v, ex=None: store.update({k: v})

        with patch("core.cache._get_client", return_value=mock_redis):
            cache.set("mykey", {"hello": "world"})
            result = cache.get("mykey")

        assert result == {"hello": "world"}

    def test_get_missing_key_returns_none(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("core.cache._get_client", return_value=mock_redis):
            assert cache.get("nonexistent") is None


class TestCacheStats:
    """get_stats() must return key count and hit rate, or None when disconnected."""

    def setup_method(self):
        _reset_cache_state()

    def test_returns_none_without_redis(self):
        with patch("core.cache._get_client", return_value=None):
            assert cache.get_stats() is None

    def test_returns_keys_and_hit_rate(self):
        mock_redis = MagicMock()
        mock_redis.dbsize.return_value = 42
        mock_redis.info.return_value = {"keyspace_hits": 80, "keyspace_misses": 20}
        mock_redis.keys.return_value = []

        with patch("core.cache._get_client", return_value=mock_redis):
            stats = cache.get_stats()

        assert stats["key_count"] == 42
        assert stats["hit_rate"] == 80  # 80 / (80+20) * 100

    def test_breakdown_counts_keys_by_prefix(self):
        mock_redis = MagicMock()
        mock_redis.dbsize.return_value = 5
        mock_redis.info.return_value = {"keyspace_hits": 0, "keyspace_misses": 0}

        def fake_keys(pattern):
            mapping = {
                "file:*": ["file:r1:a", "file:r1:b"],
                "ls:*": ["ls:r1:notes"],
                "search:*": [],
                "history_commits:*": ["history_commits:today"],
                "rss:*": [],
                "home:*": [],
                "motd:*": [],
                "potd:offset:*": [],
                "meme:offset:*": [],
                "potd:file:*": [],
                "meme:file:*": [],
            }
            return mapping.get(pattern, [])

        mock_redis.keys.side_effect = fake_keys

        with patch("core.cache._get_client", return_value=mock_redis):
            stats = cache.get_stats()

        assert stats["breakdown"] == {"file": 2, "ls": 1, "history": 1}
        # Prefixes with 0 keys are omitted from breakdown


class TestCacheBytes:
    def test_set_and_get_bytes_roundtrip(self):
        stored = {}

        def fake_set(key, val, ex=None):
            stored[key] = val

        def fake_get(key):
            return stored.get(key)

        mock_redis = MagicMock()
        mock_redis.set.side_effect = fake_set
        mock_redis.get.side_effect = fake_get

        data = b"\x89PNG\r\n\x1a\n\x00\x00binary"
        with patch("core.cache._get_client", return_value=mock_redis):
            cache.set_bytes("img:test", data, ttl=60)
            result = cache.get_bytes("img:test")

        assert result == data

    def test_set_bytes_skips_oversized(self):
        mock_redis = MagicMock()
        with patch("core.cache._get_client", return_value=mock_redis):
            cache.set_bytes("img:big", b"x" * (11 * 1024 * 1024), ttl=60)
        mock_redis.set.assert_not_called()

    def test_get_bytes_returns_none_on_missing(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch("core.cache._get_client", return_value=mock_redis):
            assert cache.get_bytes("img:missing") is None

    def test_hit_rate_none_when_no_requests(self):
        mock_redis = MagicMock()
        mock_redis.dbsize.return_value = 0
        mock_redis.info.return_value = {"keyspace_hits": 0, "keyspace_misses": 0}

        with patch("core.cache._get_client", return_value=mock_redis):
            stats = cache.get_stats()

        assert stats["hit_rate"] is None

    def test_returns_none_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.dbsize.side_effect = Exception("connection lost")

        with patch("core.cache._get_client", return_value=mock_redis):
            assert cache.get_stats() is None
