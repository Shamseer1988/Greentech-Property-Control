"""Realtime event fan-out (Phase 8a).

publish(channel, payload) broadcasts a JSON payload to every connected
SSE client subscribed to `channel`. Backed by Redis pub/sub when
REDIS_URL is set so events fan out across separate processes (worker,
beat, additional waitress instances if any); falls back to an
in-process queue otherwise (single-process dev / tests).

Channels:
  * 'occupancy' — unit status changes (allocation, release, maintenance)
  * 'notification:<user_id>' — per-user notification deliveries
"""
import json
import queue
import threading
from typing import Iterator

from flask import current_app


# In-process pub/sub for single-worker dev / tests. Each subscriber gets
# its own queue; publish() fans out.
_subs_lock = threading.Lock()
_subscribers: dict[str, list[queue.Queue]] = {}


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


def publish(channel: str, payload: dict) -> None:
    """Broadcast a JSON-serializable payload to all subscribers of
    `channel`. Safe to call from any thread / request context."""
    body = json.dumps(payload, default=str)
    r = _redis()
    if r is not None:
        try:
            r.publish(f"greentech:{channel}", body)
            return
        except Exception:
            pass  # fall through to in-process
    # In-process broadcast.
    with _subs_lock:
        subs = list(_subscribers.get(channel, []))
    for q in subs:
        try:
            q.put_nowait(body)
        except queue.Full:
            pass  # slow consumer; drop on the floor


def subscribe(channel: str) -> Iterator[str]:
    """Generator yielding event payloads as they arrive.

    Caller is responsible for breaking out — typical use is from a
    Flask streaming view. Each yield is a JSON string ready to be
    framed as an SSE `data: ...\\n\\n` block."""
    r = _redis()
    if r is not None:
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(f"greentech:{channel}")
        try:
            while True:
                # Poll with a timeout so the caller (the SSE route) gets
                # a chance to emit keepalives and to honor its own
                # max-stream deadline. listen() would block forever
                # waiting for the next message and starve both.
                msg = pubsub.get_message(timeout=15.0)
                if msg is None:
                    yield ""  # keepalive tick
                    continue
                if msg.get("type") != "message":
                    continue
                body = msg.get("data")
                if isinstance(body, bytes):
                    body = body.decode("utf-8", "replace")
                yield body
        finally:
            try:
                pubsub.close()
            except Exception:
                pass
        return

    q: queue.Queue = queue.Queue(maxsize=256)
    with _subs_lock:
        _subscribers.setdefault(channel, []).append(q)
    try:
        while True:
            try:
                yield q.get(timeout=15.0)
            except queue.Empty:
                # SSE keepalive — yield empty so the caller can frame
                # it as a comment line and keep the socket alive.
                yield ""
    finally:
        with _subs_lock:
            try:
                _subscribers[channel].remove(q)
            except (KeyError, ValueError):
                pass


def _broadcast_count(channel: str) -> int:
    """Test helper: how many in-process subscribers exist."""
    with _subs_lock:
        return len(_subscribers.get(channel, []))
