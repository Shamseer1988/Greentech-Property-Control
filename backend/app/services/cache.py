"""Small app-level cache with graceful in-memory fallback.

Redis-backed when REDIS_URL is set (get/set with TTL, JSON-serialized).
Falls back to a process-local dict when Redis is unset or unreachable —
mirrors services/events.py::_redis()'s exact fallback shape, so this
behaves identically whether or not a broker is running. This is a
best-effort cache, not a source of truth: on any Redis error we degrade
silently rather than raise, since a cache miss just costs an extra query.
"""
import json
import threading
import time
from typing import Any

from flask import current_app

_local_lock = threading.Lock()
_local_store: dict[str, tuple[float, str]] = {}  # key -> (expires_at, json value)

_PREFIX = "greentech:cache:"


def _redis():
    """Lazy redis client. Returns None when REDIS_URL is unset."""
    url = current_app.config.get("REDIS_URL")
    if not url:
        return None
    try:
        import redis as redis_lib
        return redis_lib.Redis.from_url(url)
    except Exception:
        return None


def _disabled() -> bool:
    """The in-process fallback store is a module-level global that outlives
    any single test's app/db fixture — without this, a value cached by one
    test would leak into the next, since pytest reuses the same process.
    Redis-backed caching wouldn't have this problem (each test app still
    talks to the same broker, but keys are cheap and TTLs are short), but
    since REDIS_URL is unset in the test config too, every cache read in
    the suite would otherwise hit the leaky fallback path. Simplest fix:
    caching is inert under TESTING, so tests see the exact same
    always-hits-the-DB behavior they did before this module existed."""
    return bool(current_app.config.get("TESTING"))


def cache_get(key: str) -> Any | None:
    if _disabled():
        return None
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_PREFIX + key)
            return json.loads(raw) if raw is not None else None
        except Exception:
            pass  # fall through to the in-process store
    with _local_lock:
        entry = _local_store.get(key)
        if entry is None:
            return None
        expires_at, raw = entry
        if expires_at < time.time():
            _local_store.pop(key, None)
            return None
        return json.loads(raw)


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    if _disabled():
        return
    raw = json.dumps(value, default=str)
    r = _redis()
    if r is not None:
        try:
            r.set(_PREFIX + key, raw, ex=ttl_seconds)
            return
        except Exception:
            pass  # fall through to the in-process store
    with _local_lock:
        _local_store[key] = (time.time() + ttl_seconds, raw)


def cache_delete(*keys: str) -> None:
    r = _redis()
    if r is not None:
        try:
            r.delete(*(_PREFIX + k for k in keys))
        except Exception:
            pass
    with _local_lock:
        for k in keys:
            _local_store.pop(k, None)
