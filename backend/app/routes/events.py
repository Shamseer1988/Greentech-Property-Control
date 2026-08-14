"""Server-Sent Events endpoints (Phase 8a).

GET /api/v1/events/stream  — long-lived text/event-stream the frontend
                              subscribes to. Auth via cookie (same as
                              every other route). Yields:
                                event: occupancy
                                data: {...json...}

POST /api/v1/events/publish — admin / test helper that publishes a
                              payload onto a channel. Useful for
                              smoke-testing the SSE pipeline end-to-end
                              without touching the assignment service.

In production the WSGI server (waitress) needs enough threads that a
long-lived stream connection doesn't starve the request thread pool.
The default 8 threads is fine for ~4 concurrent SSE subscribers; bump
WAITRESS_THREADS in backend/.env if you expect more.
"""
import json
import time

from flask import Blueprint, Response, request, stream_with_context

from ..services import events
from ..utils.auth import login_required, current_user
from ..utils.responses import success_response, error_response

events_bp = Blueprint("events", __name__)

# Whitelist channels a client can subscribe to. Per-user notifications
# get the user's id resolved server-side, never trusted from the URL.
PUBLIC_CHANNELS = {"occupancy"}

# Cap a single SSE connection. The browser's EventSource auto-reconnects
# on clean close, so this is invisible to the user — but it lets the
# gthread worker recycle the thread and frees the pooled HTTP socket on
# the Next.js proxy side before either keepalive timer expires. Without
# the cap, one open dashboard tab pins one of only `threads=8` gthread
# slots for the lifetime of the page.
STREAM_MAX_SECONDS = 25


@events_bp.get("/stream")
@login_required
def stream():
    requested = request.args.get("channel", "occupancy")
    user = current_user()
    if requested not in PUBLIC_CHANNELS and requested != "notification":
        return error_response("Unknown channel", 400)
    channel = (
        f"notification:{user.id}" if requested == "notification" else requested
    )

    @stream_with_context
    def gen():
        # Initial comment so the browser opens the connection cleanly
        # even if the first real event takes a while.
        yield ":ok\n\n"
        deadline = time.monotonic() + STREAM_MAX_SECONDS
        for body in events.subscribe(channel):
            if not body:
                # Keepalive ping every ~15s — comment lines are ignored
                # by the EventSource parser but keep the TCP socket
                # warm through middleboxes.
                yield ":keepalive\n\n"
            else:
                yield f"event: {requested}\ndata: {body}\n\n"
            if time.monotonic() >= deadline:
                return

    resp = Response(gen(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"  # disable nginx buffering
    # No explicit Connection header here: it's hop-by-hop (PEP 3333) and
    # waitress asserts against a WSGI app setting it, crashing the
    # worker outright. The generator's own STREAM_MAX_SECONDS cap above
    # already ends the response body on a clean schedule; waitress
    # closes the socket once the chunked body finishes, which is enough
    # for the Next.js/nginx proxy to stop trying to reuse it.
    return resp


@events_bp.post("/publish")
@login_required
def publish_event():
    """Test / admin helper. Validates the channel and forwards to
    services.events.publish — used by integration tests + the smoke
    button on the events page."""
    payload = request.get_json(silent=True) or {}
    channel = payload.get("channel", "occupancy")
    data = payload.get("data") or {}
    user = current_user()
    if channel not in PUBLIC_CHANNELS and channel != "notification":
        return error_response("Unknown channel", 400)
    if channel == "notification":
        channel = f"notification:{user.id}"
    events.publish(channel, data)
    return success_response(message="published")
