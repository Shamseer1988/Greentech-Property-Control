"""Notification rules, the outbound message log, and manual sending.

Anything on this blueprint that can put a message in front of someone
outside the company sits behind `notification.send`, separately from the
`notification.manage` needed to write the rules.
"""
from datetime import date, datetime

from flask import Blueprint, request

from ..extensions import db
from ..models import (
    Client, ClientContract, Landlord, NotificationRule, OutboundMessage,
)
from ..models.notification_rule import (
    AUDIENCES, CHANNELS, EVENT_LABELS, NOTIFICATION_EVENTS,
)
from ..services import (
    ai as ai_service, audit, email as email_service,
    notification_rules as rules_service, telegram as telegram_service,
)
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

messaging_bp = Blueprint("messaging", __name__)


def _parse_day(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


# ----------------------------------------------------------------- rules

@messaging_bp.get("/rules")
@require_permission("notification.manage")
def list_rules():
    rules = NotificationRule.query.order_by(NotificationRule.event).all()
    return success_response(
        data=[r.to_dict() for r in rules],
        meta={
            "events": sorted(NOTIFICATION_EVENTS),
            "event_labels": EVENT_LABELS,
            "channels": sorted(CHANNELS),
            "audiences": sorted(AUDIENCES),
            "defaults": {k: {"subject": v[0], "body": v[1]}
                         for k, v in rules_service.DEFAULT_TEMPLATES.items()},
        },
    )


@messaging_bp.post("/rules/seed")
@require_permission("notification.manage")
def seed_rules():
    created = rules_service.seed_defaults()
    db.session.commit()
    return success_response(
        data={"created": created},
        message=f"{created} rule(s) added" if created else "Every event already has a rule",
    )


@messaging_bp.put("/rules/<int:rule_id>")
@require_permission("notification.manage")
def update_rule(rule_id: int):
    rule = NotificationRule.query.get_or_404(rule_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    before = rule.to_dict()

    if "is_enabled" in payload:
        rule.is_enabled = bool(payload["is_enabled"])
    if "advance_days" in payload:
        try:
            rule.advance_days = sorted(
                {int(d) for d in (payload["advance_days"] or [])}, reverse=True)
        except (TypeError, ValueError):
            return error_response("advance_days must be a list of whole numbers", 400)
    if "channels" in payload:
        bad = set(payload["channels"] or []) - CHANNELS
        if bad:
            return error_response(f"Unknown channel(s): {sorted(bad)}", 400)
        rule.channels = list(payload["channels"] or [])
    if "audiences" in payload:
        bad = set(payload["audiences"] or []) - AUDIENCES
        if bad:
            return error_response(f"Unknown audience(s): {sorted(bad)}", 400)
        rule.audiences = list(payload["audiences"] or [])
    for field in ("extra_emails", "staff_role_codes", "subject_template",
                  "body_template", "remarks"):
        if field in payload:
            setattr(rule, field, (payload[field] or None))

    rule.updated_by = actor.id
    audit.record(user=actor, action="update", module="notification",
                 entity_type="notification_rule", entity_id=rule.id,
                 old_value=before, new_value=rule.to_dict(),
                 remarks=rule.event)
    db.session.commit()
    return success_response(data=rule.to_dict(), message="Rule saved")


@messaging_bp.post("/rules/<int:rule_id>/preview")
@require_permission("notification.manage")
def preview_rule(rule_id: int):
    """Show what this rule *would* do today, writing nothing.

    The point of the phase: an operator can see the exact list of people
    a rule would contact before allowing it to contact them.
    """
    rule = NotificationRule.query.get_or_404(rule_id)
    payload = request.get_json(silent=True) or {}
    on = _parse_day(payload.get("date")) or date.today()
    result = rules_service.evaluate_rule(rule, on, dry_run=True)
    db.session.rollback()          # nothing from a preview may persist
    return success_response(data=result)


# ----------------------------------------------------------------- sweep

@messaging_bp.post("/sweep")
@require_permission("notification.send")
def run_sweep():
    payload = request.get_json(silent=True) or {}
    on = _parse_day(payload.get("date")) or date.today()
    dry_run = bool(payload.get("dry_run", False))
    actor = current_user()

    result = rules_service.run_sweep(on, dry_run=dry_run)
    if not dry_run:
        audit.record(user=actor, action="sweep", module="notification",
                     entity_type="notification_sweep", entity_id=None,
                     new_value={"date": result["date"],
                                "findings": result["findings"]},
                     remarks=f"{result['findings']} finding(s)")
        db.session.commit()
    else:
        db.session.rollback()
    return success_response(
        data=result,
        message=(f"{result['findings']} finding(s) "
                 f"{'previewed' if dry_run else 'processed'}"),
    )


# ------------------------------------------------------------- outbox log

@messaging_bp.get("/messages")
@require_permission("notification.view")
def list_messages():
    query = OutboundMessage.query
    for field in ("channel", "status", "event", "entity_type"):
        value = request.args.get(field)
        if value:
            query = query.filter(getattr(OutboundMessage, field) == value)
    if request.args.get("entity_id"):
        query = query.filter(OutboundMessage.entity_id ==
                             request.args.get("entity_id", type=int))
    date_from = _parse_day(request.args.get("date_from"))
    date_to = _parse_day(request.args.get("date_to"))
    if date_from:
        query = query.filter(OutboundMessage.created_at >= datetime.combine(
            date_from, datetime.min.time()))
    if date_to:
        query = query.filter(OutboundMessage.created_at < datetime.combine(
            date_to, datetime.max.time()))

    limit = min(request.args.get("limit", default=200, type=int), 1000)
    rows = query.order_by(OutboundMessage.id.desc()).limit(limit).all()
    counts = dict(
        db.session.query(OutboundMessage.status, db.func.count(OutboundMessage.id))
        .group_by(OutboundMessage.status).all()
    )
    return success_response(
        data=[r.to_dict() for r in rows],
        meta={"count": len(rows), "limit": limit, "status_counts": counts},
    )


@messaging_bp.post("/messages/<int:message_id>/retry")
@require_permission("notification.send")
def retry_message(message_id: int):
    message = OutboundMessage.query.get_or_404(message_id)
    if message.status == "sent":
        return error_response("That message was already sent", 400)
    actor = current_user()
    if message.channel == "email":
        email_service.deliver(message)
    elif message.channel == "telegram":
        telegram_service.deliver(message)
    else:
        return error_response(f"Cannot retry a {message.channel} message", 400)
    audit.record(user=actor, action="retry", module="notification",
                 entity_type="outbound_message", entity_id=message.id,
                 new_value={"status": message.status}, remarks=message.subject)
    db.session.commit()
    return success_response(data=message.to_dict(),
                            message=f"Message {message.status}")


# --------------------------------------------------------- manual sending

@messaging_bp.post("/send")
@require_permission("notification.send")
def send_manual():
    """Compose-and-send from a client / landlord / contract page.

    The recipient is resolved server-side from the named party rather
    than taken from the request, so a compose screen cannot be talked
    into mailing an arbitrary address.
    """
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()
    if not subject or not body:
        return error_response("Both a subject and a body are required", 400)

    party_type = (payload.get("party_type") or "").strip()
    party_id = payload.get("party_id")
    party, address, name = None, None, None
    if party_type == "client":
        party = Client.query.get(party_id)
    elif party_type == "landlord":
        party = Landlord.query.get(party_id)
    else:
        return error_response("party_type must be 'client' or 'landlord'", 400)
    if party is None:
        return error_response(f"No such {party_type}", 404)

    address, name = party.email, party.name
    if not email_service.valid_address(address):
        return error_response(
            f"{name} has no usable email address on file — add one first.", 400)

    message = email_service.send_now(
        to_address=address, to_name=name, subject=subject, body=body,
        event="manual", entity_type=party_type, entity_id=party.id,
        is_manual=True,
    )
    audit.record(user=actor, action="send", module="notification",
                 entity_type="outbound_message", entity_id=message.id,
                 new_value={"to": address, "subject": subject,
                            "status": message.status},
                 remarks=f"manual email to {party_type} {party.code}")
    db.session.commit()
    return success_response(
        data=message.to_dict(),
        message=("Sent" if message.status == "sent"
                 else f"Logged but not sent — {message.error}"),
    )


# ------------------------------------------------------------ connectivity

@messaging_bp.post("/test/email")
@require_permission("settings.manage")
def test_email():
    payload = request.get_json(silent=True) or {}
    to_address = (payload.get("to") or "").strip()
    try:
        message = email_service.send_test(to_address)
    except email_service.EmailError as exc:
        db.session.commit()          # keep the failed row as evidence
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=message.to_dict(),
                            message=f"Test email sent to {to_address}")


@messaging_bp.post("/test/telegram")
@require_permission("settings.manage")
def test_telegram():
    try:
        message = telegram_service.send_test()
    except telegram_service.TelegramError as exc:
        db.session.commit()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=message.to_dict(), message="Test message posted")


@messaging_bp.post("/test/ai")
@require_permission("settings.manage")
def test_ai():
    try:
        reply = ai_service.test_connection()
    except ai_service.AIError as exc:
        return error_response(str(exc), 400)
    return success_response(data={"reply": reply}, message="AI provider responded")


# ------------------------------------------------------------------- AI

@messaging_bp.post("/ai/draft")
@require_permission("notification.send")
def ai_draft():
    """Draft a message for a human to review. Sends nothing."""
    payload = request.get_json(silent=True) or {}
    purpose = (payload.get("purpose") or "").strip()
    if not purpose:
        return error_response("Say what the message is for", 400)

    facts = dict(payload.get("facts") or {})
    # Let the caller name a contract and have the facts filled in, so a
    # draft can't quote a rent figure the caller invented.
    if payload.get("contract_id"):
        contract = ClientContract.query.get(payload["contract_id"])
        if contract is not None:
            facts.setdefault("client_name", contract.client.name if contract.client else None)
            facts.setdefault("property_name", contract.property.name if contract.property else None)
            facts.setdefault("contract_number", contract.contract_number)
            facts.setdefault("monthly_rent", f"{float(contract.monthly_rent):,.2f} QAR")
            facts.setdefault("expiry_date", contract.expiry_date.isoformat())
    try:
        draft = ai_service.draft_message(
            purpose=purpose, facts=facts,
            tone=(payload.get("tone") or "courteous"))
    except ai_service.AIError as exc:
        return error_response(str(exc), 400)
    return success_response(data={"draft": draft, "facts": facts})


@messaging_bp.post("/ai/monthly-summary")
@require_permission("notification.send")
def ai_monthly_summary():
    from ..services import dashboard as dashboard_service
    payload = request.get_json(silent=True) or {}
    month = _parse_day(payload.get("month")) or date.today()
    summary = dashboard_service.summary(month=month)
    figures = {
        "month": summary["month"],
        "rent_charged": summary["collections"]["charged"],
        "rent_collected": summary["collections"]["collected"],
        "collection_percent": summary["collections"]["collection_percent"],
        "total_arrears": summary["ageing"]["total_outstanding"],
        "clients_in_arrears": summary["ageing"]["clients_in_arrears"],
        "paid_to_landlords": summary["pnl"].get("rent_paid"),
        "property_costs": summary["pnl"].get("expense_total"),
        "net_profit": summary["pnl"].get("net_profit"),
        "occupancy_percent": summary["units"]["occupancy_percent"],
        "empty_units": summary["units"]["empty"],
        "contracts_expiring_90_days": summary["contract_expiry"]["buckets"]["total"],
    }
    try:
        text = ai_service.monthly_summary(figures)
    except ai_service.AIError as exc:
        return error_response(str(exc), 400)
    return success_response(data={"summary": text, "figures": figures})
