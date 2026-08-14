"""Sentry-to-Telegram alerting.

Kept in its own tiny task rather than called directly from
observability.py::init_sentry()'s before_send hook, because that hook
fires synchronously inside whatever request just failed — the request's
DB session may itself be the thing that's broken (a pool exhaustion, an
aborted transaction), and telegram_service.send_now() needs a working
session to record the OutboundMessage row. Dispatching through Celery
gives the alert its own fresh app context (app.celery_app's ContextTask)
entirely decoupled from the failing request, so a broken session never
turns "alert on error" into a second error.
"""
from __future__ import annotations

from . import jobrun
from ..celery_app import celery
from ..services import telegram as telegram_service


@celery.task(name="app.tasks.sentry_alerts.send_sentry_alert")
def send_sentry_alert(text: str, dedupe_key: str | None = None) -> dict:
    with jobrun("send_sentry_alert", {"dedupe_key": dedupe_key}) as run:
        message = telegram_service.send_now(
            text=text, event="sentry_alert", is_manual=True, dedupe_key=dedupe_key,
        )
        status = message.status if message is not None else "deduped"
        run.result = status
        return {"status": status}
