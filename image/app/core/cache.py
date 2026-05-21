"""Optional Redis cache — gracefully disabled if Redis is unavailable."""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_client = None  # None = not yet tried, redis.Redis = connected
_retry_after = 0.0  # timestamp after which to retry connecting
_RETRY_INTERVAL = 30  # seconds between reconnect attempts


def _get_client():
    global _client, _retry_after
    if _client is not None:
        return _client
    if time.monotonic() < _retry_after:
        return None
    try:
        import redis as redis_lib

        url = os.environ.get("REDIS_URL", "redis://redis:6379")
        c = redis_lib.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        c.ping()
        _client = c
        logger.info("Redis cache connected: %s", url)
    except Exception as e:
        logger.warning("Redis unavailable, will retry in %ds: %s", _RETRY_INTERVAL, e)
        _retry_after = time.monotonic() + _RETRY_INTERVAL
    return _client


def get_client():
    return _get_client()


def get(key: str) -> Any | None:
    c = _get_client()
    if not c:
        return None
    try:
        val = c.get(key)
        return json.loads(val) if val is not None else None
    except Exception:
        return None


def get_bytes(key: str) -> bytes | None:
    """Retrieve binary data stored via set_bytes."""
    import base64

    val = get(key)
    if val is None:
        return None
    try:
        return base64.b64decode(val)
    except Exception:
        return None


_max_file_bytes: int = 10 * 1024 * 1024  # configurable via configure_limits()


def configure_limits(max_file_mb: int) -> None:
    global _max_file_bytes
    _max_file_bytes = max(1, max_file_mb) * 1024 * 1024


def set_bytes(key: str, data: bytes, ttl: int = 600) -> None:
    """Store binary data base64-encoded. Skipped silently if data exceeds configured limit."""
    import base64

    if len(data) > _max_file_bytes:
        return
    set(key, base64.b64encode(data).decode("ascii"), ttl=ttl)


def set(key: str, value: Any, ttl: int = 600) -> None:
    c = _get_client()
    if not c:
        return
    try:
        c.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass


def invalidate_repo(repo_id: str) -> None:
    """Clear all cache entries for a repo plus cross-repo caches."""
    c = _get_client()
    if not c:
        return
    try:
        patterns = [
            f"kb:{repo_id}:*",
            f"ls:{repo_id}:*",
            f"file:{repo_id}:*",
            "search:global:*",
            "history_commits:*",
            "home:recent",
            "potd:file:*",
            "meme:file:*",
        ]
        keys = []
        for p in patterns:
            keys.extend(c.keys(p))
        if keys:
            c.delete(*keys)
    except Exception:
        pass


def flush() -> None:
    c = _get_client()
    if not c:
        return
    try:
        c.flushdb()
    except Exception:
        pass


def is_connected() -> bool:
    """Return True if Redis is reachable right now."""
    global _client, _retry_after
    c = _get_client()
    if not c:
        return False
    try:
        c.ping()
        return True
    except Exception:
        _client = None
        _retry_after = time.monotonic() + _RETRY_INTERVAL
        return False


# Ordered list of (redis key pattern, display label) for the home breakdown
_KEY_GROUPS: list[tuple[str, str]] = [
    ("file:*", "file"),
    ("ls:*", "ls"),
    ("search:*", "search"),
    ("history_commits:*", "history"),
    ("rss:*", "rss"),
    ("home:*", "home"),
    ("motd:*", "motd"),
    ("potd:offset:*", "potd"),
    ("meme:offset:*", "meme"),
    ("potd:file:*", "potd:img"),
    ("meme:file:*", "meme:img"),
]


def get_stats() -> dict | None:
    """Return cache stats: key count, hit rate, breakdown by key group. None if disconnected."""
    c = _get_client()
    if not c:
        return None
    try:
        info = c.info("stats")
        keys = c.dbsize()
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = round(hits / total * 100) if total > 0 else None
        breakdown: dict[str, int] = {}
        for pattern, label in _KEY_GROUPS:
            count = len(c.keys(pattern))
            if count:
                breakdown[label] = count
        return {"key_count": keys, "hit_rate": hit_rate, "breakdown": breakdown}
    except Exception:
        return None
