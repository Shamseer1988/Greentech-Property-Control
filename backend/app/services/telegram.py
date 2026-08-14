"""Telegram delivery to the staff group.

Same shape as the email service — log first, deliver second, and the
same `telegram.enabled` tap that is off until someone turns it on.

Telegram is an internal channel: the bot posts to the company's own
staff group, never to a client. That is why it needs no audience
resolution and no redirect setting.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime

from ..extensions import db
from ..models import OutboundMessage
from . import settings as settings_service

API_BASE = "https://api.telegram.org"
TIMEOUT_SECONDS = 20


class TelegramError(RuntimeError):
    pass


def is_enabled() -> bool:
    return settings_service.get_bool("telegram.enabled", False)


def _config() -> tuple[str, str]:
    token = (settings_service.get("telegram.bot_token") or "").strip()
    chat_id = (settings_service.get("telegram.chat_id") or "").strip()
    return token, chat_id


def _post(token: str, method: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API_BASE}/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        try:
            detail = json.loads(detail).get("description", detail)
        except json.JSONDecodeError:
            pass
        raise TelegramError(f"Telegram refused the message: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TelegramError(f"Could not reach Telegram: {exc.reason}") from exc


def queue(
    *,
    text: str,
    event: str | None = None,
    rule_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    dedupe_key: str | None = None,
    is_manual: bool = False,
) -> OutboundMessage | None:
    if dedupe_key:
        if OutboundMessage.query.filter_by(dedupe_key=dedupe_key).first() is not None:
            return None
    _, chat_id = _config()
    message = OutboundMessage(
        channel="telegram", event=event, rule_id=rule_id,
        entity_type=entity_type, entity_id=entity_id,
        to_address=chat_id or None, body=text,
        status="queued", dedupe_key=dedupe_key, is_manual=is_manual,
    )
    db.session.add(message)
    db.session.flush()
    return message


def deliver(message: OutboundMessage) -> OutboundMessage:
    if message.status == "sent":
        return message
    message.attempts = (message.attempts or 0) + 1

    if not is_enabled():
        message.status = "skipped"
        message.error = "Telegram is switched off (Settings → Telegram)."
        db.session.flush()
        return message

    token, chat_id = _config()
    if not token or not chat_id:
        message.status = "failed"
        message.error = "Telegram bot token or chat id is not configured."
        db.session.flush()
        return message

    try:
        _post(token, "sendMessage", {
            "chat_id": chat_id,
            "text": message.body or "",
            "disable_web_page_preview": True,
        })
    except TelegramError as exc:
        message.status = "failed"
        message.error = str(exc)[:2000]
        db.session.flush()
        return message

    message.status = "sent"
    message.error = None
    message.to_address = chat_id
    message.sent_at = datetime.utcnow()
    db.session.flush()
    return message


def send_now(**kwargs) -> OutboundMessage | None:
    message = queue(**kwargs)
    if message is None:
        return None
    return deliver(message)


def send_test() -> OutboundMessage:
    """Post a test line to the configured group. Bypasses the enabled
    flag for the same reason the email test does."""
    token, chat_id = _config()
    if not token:
        raise TelegramError("Set the bot token first.")
    if not chat_id:
        raise TelegramError("Set the chat id first.")

    message = OutboundMessage(
        channel="telegram", event="test", to_address=chat_id,
        body=("GreenTech portal — test message. "
              f"If you can read this, the bot is wired up correctly "
              f"({datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC)."),
        status="queued", is_manual=True, attempts=1,
    )
    db.session.add(message)
    db.session.flush()

    try:
        _post(token, "sendMessage", {"chat_id": chat_id, "text": message.body})
    except TelegramError as exc:
        message.status = "failed"
        message.error = str(exc)[:2000]
        db.session.flush()
        raise

    message.status = "sent"
    message.sent_at = datetime.utcnow()
    db.session.flush()
    return message
