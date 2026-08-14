"""Observability wiring (Phase 6): JSON logs + request-id, Sentry,
Prometheus.

The three init_*() functions are called from create_app; each is safe
to call without an env var set (no-ops cleanly so dev / CI don't need
Sentry DSN or a real metrics token to boot)."""
import logging
import os
import sys
import uuid

import structlog
from flask import Flask, abort, g, request


log = structlog.get_logger("greentech")


# ---------------------------------------------------------------------------
# JSON logging + per-request request-id
# ---------------------------------------------------------------------------
def init_logging(app: Flask) -> None:
    """Configure structlog so app logs are JSON to stdout in prod (and
    in tests so we can assert on them), pretty in dev.

    Installs before/after request hooks that:
      * pull the request-id from X-Request-ID (or Cloudflare's CF-Ray
        as a fallback — they're orderable per connection), or mint a
        new uuid4 if neither is present;
      * stash it on g.request_id + structlog context so every log line
        emitted during the request carries it;
      * echo it back as X-Request-ID so callers can quote it in support
        tickets.
    """
    level_name = (app.config.get("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    use_json = bool(app.config.get("LOG_JSON", app.config.get("ENV") == "production"))
    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    # Wire stdlib logging through structlog. Other libraries (sqlalchemy,
    # waitress, etc.) write to logging.getLogger and we want those lines
    # to come out with the same shape.
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        # No caching: a second create_app (test suite, waitress reload)
        # must be able to flip JSON vs console without restarting the
        # process.
        cache_logger_on_first_use=False,
    )

    @app.before_request
    def _bind_request_id():
        # Cloudflare's CF-Ray is per-edge-connection; X-Request-ID is the
        # conventional name behind nginx. Prefer the explicit one.
        rid = (
            request.headers.get("X-Request-ID")
            or request.headers.get("CF-Ray")
            or uuid.uuid4().hex
        )
        g.request_id = rid
        # Bind into context so every log call in this request carries it.
        structlog.contextvars.clear_contextvars()
        bindings = {
            "request_id": rid,
            "method": request.method,
            "path": request.path,
            "remote_addr": request.remote_addr,
        }
        # If the user lookup has already populated g.current_user, attach
        # their id. Most requests bind in @login_required which fires
        # after this hook, so the user_id will only appear on the after-
        # request log line.
        if hasattr(g, "current_user") and g.current_user is not None:
            bindings["user_id"] = g.current_user.id
        structlog.contextvars.bind_contextvars(**bindings)

    @app.after_request
    def _emit_access_log(resp):
        rid = getattr(g, "request_id", None)
        if rid is not None:
            resp.headers["X-Request-ID"] = rid
            # Late-bind user_id if @login_required attached the user.
            if hasattr(g, "current_user") and g.current_user is not None:
                structlog.contextvars.bind_contextvars(user_id=g.current_user.id)
            log.info(
                "request",
                status=resp.status_code,
                length=resp.calculate_content_length() or 0,
            )
        return resp

    @app.teardown_request
    def _clear_context(_exc):
        structlog.contextvars.clear_contextvars()


# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------
def _alert_telegram_on_error(event: dict, hint: dict) -> dict:
    """Sentry before_send hook — fires a Telegram alert for every error-
    level event Sentry is about to accept, then always returns the event
    unchanged so Sentry still records it regardless of whether the alert
    itself succeeds.

    Dispatches through a Celery task (app.tasks.sentry_alerts) rather
    than calling telegram_service directly — this hook runs inside the
    request that just failed, and that request's DB session may be part
    of what's broken, so a synchronous DB-writing call here could turn
    one error into two. The whole thing is additionally wrapped in its
    own try/except: alerting must never be the reason Sentry itself
    fails to capture an event."""
    try:
        level = event.get("level")
        if level not in ("error", "fatal"):
            return event
        exc_info = hint.get("exc_info") if hint else None
        if exc_info:
            exc_type = exc_info[0].__name__ if exc_info[0] else "Error"
            exc_message = str(exc_info[1]) if len(exc_info) > 1 else ""
        else:
            exc_type = event.get("exception", {}).get("values", [{}])[0].get("type", "Error")
            exc_message = event.get("message") or ""
        text = f"⚠ {exc_type}: {exc_message}"[:500]
        fingerprint = event.get("fingerprint") or [event.get("event_id", "")]
        dedupe_key = f"sentry:{'|'.join(str(f) for f in fingerprint)}"

        from .tasks.sentry_alerts import send_sentry_alert
        send_sentry_alert.delay(text, dedupe_key)
    except Exception:
        pass  # never let alerting stop Sentry from receiving the event
    return event


def init_sentry(app: Flask) -> None:
    """Initialise Sentry if SENTRY_DSN is set. No-op otherwise.

    Uses the Flask + SQLAlchemy + Redis integrations so we get HTTP
    transaction tagging, DB query spans, and Redis ops for free."""
    dsn = app.config.get("SENTRY_DSN") or os.getenv("SENTRY_DSN")
    if not dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=app.config.get("ENV", "production"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,
        integrations=[FlaskIntegration(), SqlalchemyIntegration()],
        before_send=_alert_telegram_on_error,
    )


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------
def init_metrics(app: Flask) -> None:
    """Mount /metrics behind an X-Metrics-Token header check.

    PrometheusMetrics(path=None) wires the per-request histograms etc.
    but doesn't auto-mount an unguarded endpoint. We add the route
    ourselves so it can be auth-gated against a static token shared
    with the scraper (Prometheus / Grafana Agent / etc.)."""
    from prometheus_flask_exporter import PrometheusMetrics
    from prometheus_client import REGISTRY, generate_latest, CONTENT_TYPE_LATEST

    metrics = PrometheusMetrics(app, path=None)
    # prometheus_client uses a process-global registry, so subsequent
    # create_app() calls (test suite, waitress reload) collide on the
    # already-registered metric. Skip if it's been added.
    if "greentech_app_info" not in {
        getattr(c, "_name", None) for c in REGISTRY._names_to_collectors.values()
    }:
        metrics.info("greentech_app_info", "Application info",
                     version=app.config.get("VERSION", "1.0.0"))

    @app.route("/metrics")
    def _metrics():
        token_required = app.config.get("METRICS_TOKEN")
        if token_required:
            presented = request.headers.get("X-Metrics-Token")
            if not presented or presented != token_required:
                abort(401)
        # Skip auth entirely when METRICS_TOKEN is empty — useful for
        # dev/testing and for ops who scrape from a private network.
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
