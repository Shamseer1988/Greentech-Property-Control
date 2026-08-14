"""Email composition and delivery.

Every message the portal sends is written to ``outbound_messages``
first and delivered second. That ordering is deliberate: the log is the
record of what was said to a client on the company's behalf, and it
must exist even when the send fails.

Three guards stand between a template and a client's inbox, because the
cost of a wrong mass-mailing to tenants is not recoverable:

  * ``email.enabled`` is off by default. With it off, messages are
    composed and logged with status ``skipped`` — you can read exactly
    what *would* have gone out before letting any of it go.
  * ``email.redirect_to``, when set, sends everything to that one
    address instead, noting the intended recipient in the body. This is
    how you rehearse a month-end run.
  * ``dedupe_key`` is unique, so a sweep that runs twice cannot say the
    same thing twice.
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage as MIMEMessage
from email.utils import formataddr, parseaddr

from ..extensions import db
from ..models import OutboundMessage
from . import settings as settings_service


class EmailError(RuntimeError):
    """A send failed for a reason worth showing the operator."""


def is_enabled() -> bool:
    return settings_service.get_bool("email.enabled", False)


def _config() -> dict:
    return {
        "host": (settings_service.get("email.smtp_host") or "").strip(),
        "port": int(settings_service.get("email.smtp_port") or 587),
        "username": (settings_service.get("email.smtp_username") or "").strip(),
        "password": settings_service.get("email.smtp_password") or "",
        "from_address": (settings_service.get("email.from_address") or "").strip(),
        "from_name": (settings_service.get("email.from_name") or "").strip(),
        "tls": settings_service.get_bool("email.tls_enabled", True),
        "redirect_to": (settings_service.get("email.redirect_to") or "").strip(),
    }


def valid_address(value: str | None) -> bool:
    """Good enough to catch a blank or an obvious typo before we hand it
    to a mail server. Not an RFC validator, and not trying to be."""
    if not value:
        return False
    _, addr = parseaddr(value)
    return bool(addr) and "@" in addr and "." in addr.rsplit("@", 1)[-1]


def render(template: str | None, context: dict, fallback: str = "") -> str:
    """Substitute ``{placeholders}`` from `context`.

    A template naming a field we don't have keeps the placeholder rather
    than raising — a reminder that reads "{client_name}" is a visible
    fault the operator can fix, while a 500 in a nightly sweep is not.
    """
    text = template if template is not None and template.strip() else fallback
    out = text
    for key, value in context.items():
        out = out.replace("{" + key + "}", "" if value is None else str(value))
    return out


def queue(
    *,
    to_address: str,
    subject: str,
    body: str,
    to_name: str | None = None,
    event: str | None = None,
    rule_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    dedupe_key: str | None = None,
    is_manual: bool = False,
) -> OutboundMessage | None:
    """Write a message to the outbox.

    Returns None when `dedupe_key` has already been used — that is the
    normal, quiet outcome of a sweep re-running, not an error.
    """
    if dedupe_key:
        existing = OutboundMessage.query.filter_by(dedupe_key=dedupe_key).first()
        if existing is not None:
            return None

    message = OutboundMessage(
        channel="email",
        event=event,
        rule_id=rule_id,
        entity_type=entity_type,
        entity_id=entity_id,
        to_address=to_address,
        to_name=to_name,
        subject=subject,
        body=body,
        status="queued",
        dedupe_key=dedupe_key,
        is_manual=is_manual,
    )
    db.session.add(message)
    db.session.flush()
    return message


def deliver(message: OutboundMessage) -> OutboundMessage:
    """Attempt one message. Always leaves the row in a terminal state."""
    if message.status == "sent":
        return message

    message.attempts = (message.attempts or 0) + 1

    if not is_enabled():
        message.status = "skipped"
        message.error = "Email sending is switched off (Settings → Email)."
        db.session.flush()
        return message

    cfg = _config()
    if not cfg["host"] or not valid_address(cfg["from_address"]):
        message.status = "failed"
        message.error = "SMTP host or From address is not configured."
        db.session.flush()
        return message

    recipient = cfg["redirect_to"] or message.to_address
    if not valid_address(recipient):
        message.status = "failed"
        message.error = f"Not a usable email address: {recipient!r}"
        db.session.flush()
        return message

    body = message.body or ""
    if cfg["redirect_to"] and cfg["redirect_to"] != message.to_address:
        body = (f"[Redirected — this was addressed to "
                f"{message.to_name or ''} <{message.to_address}>]\n\n{body}")

    mime = MIMEMessage()
    mime["Subject"] = message.subject or "(no subject)"
    mime["From"] = formataddr((cfg["from_name"] or None, cfg["from_address"]))
    mime["To"] = recipient
    mime.set_content(body)

    try:
        _send(cfg, mime, recipient)
    except Exception as exc:                      # noqa: BLE001 - logged, not raised
        message.status = "failed"
        message.error = str(exc)[:2000]
        db.session.flush()
        return message

    message.status = "sent"
    message.error = None
    message.sent_at = datetime.utcnow()
    db.session.flush()
    return message


def _send(cfg: dict, mime: MIMEMessage, recipient: str) -> None:
    """The one place that actually talks to a mail server."""
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30,
                              context=ssl.create_default_context()) as smtp:
            if cfg["username"]:
                smtp.login(cfg["username"], cfg["password"])
            smtp.send_message(mime, to_addrs=[recipient])
        return

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
        smtp.ehlo()
        if cfg["tls"]:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if cfg["username"]:
            smtp.login(cfg["username"], cfg["password"])
        smtp.send_message(mime, to_addrs=[recipient])


def send_now(**kwargs) -> OutboundMessage | None:
    """Queue and deliver in one step. Used by the manual compose screen
    and by the sweep once it has decided a message is warranted."""
    message = queue(**kwargs)
    if message is None:
        return None
    return deliver(message)


def send_test(to_address: str) -> OutboundMessage:
    """Prove the SMTP settings work, without involving a client.

    Bypasses `email.enabled` on purpose: the operator is standing at the
    Settings screen having just typed the credentials, and asking them
    to switch on live sending in order to test is exactly backwards.
    """
    if not valid_address(to_address):
        raise EmailError(f"Not a usable email address: {to_address!r}")

    cfg = _config()
    if not cfg["host"]:
        raise EmailError("Set the SMTP host first.")
    if not valid_address(cfg["from_address"]):
        raise EmailError("Set a valid From address first.")

    message = OutboundMessage(
        channel="email", event="test", to_address=to_address,
        subject="GreenTech portal — test message",
        body=("This is a test from the GreenTech Real Estate portal.\n\n"
              "If you are reading it, the SMTP settings are correct.\n"
              f"Sent {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC."),
        status="queued", is_manual=True, attempts=1,
    )
    db.session.add(message)
    db.session.flush()

    mime = MIMEMessage()
    mime["Subject"] = message.subject
    mime["From"] = formataddr((cfg["from_name"] or None, cfg["from_address"]))
    mime["To"] = to_address
    mime.set_content(message.body)
    try:
        _send(cfg, mime, to_address)
    except Exception as exc:                      # noqa: BLE001
        message.status = "failed"
        message.error = str(exc)[:2000]
        db.session.flush()
        raise EmailError(str(exc)) from exc

    message.status = "sent"
    message.sent_at = datetime.utcnow()
    db.session.flush()
    return message
