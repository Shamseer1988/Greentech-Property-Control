"""Evaluate the notification rules and fan the results out.

The daily sweep asks each enabled rule one question: *what, today, is
exactly N days from happening?* — where N is one of the rule's advance
days. That framing is what makes the job idempotent and cheap. It looks
only at boundaries, so a contract 61 days out is silent, at 60 it fires
once, and at 59 it is silent again. Nothing accumulates, nothing needs
a "last notified" column, and re-running the sweep at noon after it ran
at six changes nothing because the dedupe key already exists.

Each occurrence produces one *finding*: a subject, a body, the party it
concerns and a dedupe key. Delivery then depends on the rule's channels
and audiences — the same finding can go to the tenant by email and to
the staff group on Telegram, and each delivery is logged separately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..extensions import db
from ..models import (
    Cheque, Client, ClientContract, Landlord, NotificationRule, Property,
    PropertyAgreement, RentCharge, User,
)
from ..models.notification_rule import EVENT_LABELS, NOTIFICATION_EVENTS
from . import email as email_service
from . import notifications as inapp_service
from . import settings as settings_service
from . import telegram as telegram_service
from .documents import expiring_documents
from .rent import month_start


@dataclass
class Finding:
    """One thing worth telling somebody about, today."""
    event: str
    subject: str
    body: str
    dedupe_key: str
    entity_type: str | None = None
    entity_id: int | None = None
    link: str | None = None
    # Who the event is about, when there is such a party.
    client: Client | None = None
    landlord: Landlord | None = None
    context: dict = field(default_factory=dict)


def _money(value) -> str:
    return f"{float(value or 0):,.2f}"


# ----------------------------------------------------------------------
# Defaults — what a rule says when the operator hasn't written a template
# ----------------------------------------------------------------------

DEFAULT_TEMPLATES: dict[str, tuple[str, str]] = {
    "contract_expiry": (
        "Tenancy {contract_number} expires on {expiry_date}",
        "Dear {client_name},\n\n"
        "Your tenancy {contract_number} for {property_name} "
        "({units}) expires on {expiry_date} — {days} day(s) from today.\n\n"
        "Please let us know whether you wish to renew.\n\n"
        "GreenTech Trading & Contracting"
    ),
    "agreement_expiry": (
        "Agreement for {property_name} expires on {expiry_date}",
        "Dear {landlord_name},\n\n"
        "Our lease agreement for {property_name} expires on {expiry_date} "
        "— {days} day(s) from today.\n\n"
        "We would like to discuss renewal terms.\n\n"
        "GreenTech Trading & Contracting"
    ),
    "rent_due": (
        "Rent for {month} — {amount} QAR outstanding",
        "Dear {client_name},\n\n"
        "Rent of {amount} QAR for {month} on {property_name} is "
        "outstanding.\n\nWe would be grateful for settlement.\n\n"
        "GreenTech Trading & Contracting"
    ),
    "pdc_due": (
        "Cheque {cheque_number} is due on {cheque_date}",
        "Cheque {cheque_number} ({bank_name}) for {amount} QAR from "
        "{client_name} is dated {cheque_date} and is ready to bank."
    ),
    "cheque_bounced": (
        "Cheque {cheque_number} returned unpaid",
        "Cheque {cheque_number} for {amount} QAR from {client_name} "
        "({property_name}) has been returned unpaid. A replacement is needed."
    ),
    "document_expiry": (
        "{category} for {entity_name} expires on {expiry_date}",
        "The {category} held for {entity_name} expires on {expiry_date} "
        "— {days} day(s) from today. Please obtain the renewed copy."
    ),
    "approval_pending": (
        "{count} approval(s) waiting",
        "There are {count} request(s) waiting for a decision in the portal."
    ),
}


# ----------------------------------------------------------------------
# Finders — one per event
# ----------------------------------------------------------------------

def _find_contract_expiry(rule: NotificationRule, today: date) -> list[Finding]:
    out = []
    for days in rule.advance_list():
        target = today + timedelta(days=days)
        rows = (
            db.session.query(ClientContract, Client, Property)
            .join(Client, ClientContract.client_id == Client.id)
            .join(Property, ClientContract.property_id == Property.id)
            .filter(ClientContract.status == "active")
            .filter(ClientContract.expiry_date == target)
            .all()
        )
        for contract, client, prop in rows:
            held = contract.active_allocations(max(today, contract.start_date))
            context = {
                "contract_number": contract.contract_number,
                "client_name": client.name,
                "property_name": prop.name,
                "expiry_date": contract.expiry_date.isoformat(),
                "days": days,
                "monthly_rent": _money(contract.monthly_rent),
                "units": ", ".join(a.unit.unit_number for a in held if a.unit) or "—",
            }
            out.append(_build(rule, context,
                              dedupe=f"contract_expiry:{contract.id}:{days}",
                              entity_type="client_contract", entity_id=contract.id,
                              link=f"/contracts/{contract.id}", client=client))
    return out


def _find_agreement_expiry(rule: NotificationRule, today: date) -> list[Finding]:
    out = []
    for days in rule.advance_list():
        target = today + timedelta(days=days)
        rows = (
            db.session.query(PropertyAgreement, Property, Landlord)
            .join(Property, PropertyAgreement.property_id == Property.id)
            .join(Landlord, PropertyAgreement.landlord_id == Landlord.id)
            .filter(PropertyAgreement.is_active.is_(True))
            .filter(PropertyAgreement.expiry_date == target)
            .all()
        )
        for agreement, prop, landlord in rows:
            context = {
                "landlord_name": landlord.name,
                "property_name": prop.name,
                "expiry_date": agreement.expiry_date.isoformat(),
                "days": days,
                "monthly_rent": _money(agreement.monthly_rent),
            }
            out.append(_build(rule, context,
                              dedupe=f"agreement_expiry:{agreement.id}:{days}",
                              entity_type="property_agreement", entity_id=agreement.id,
                              link=f"/properties/{prop.id}?tab=agreement",
                              landlord=landlord))
    return out


def _find_rent_due(rule: NotificationRule, today: date) -> list[Finding]:
    """Chase unpaid rent. `advance_days` here means days *after* the
    month started — [7, 21] chases a week in and three weeks in."""
    out = []
    period = month_start(today)
    offsets = rule.advance_list() or [0]
    for offset in offsets:
        if (today - period).days != offset:
            continue
        rows = (
            db.session.query(RentCharge, Client, Property)
            .join(Client, RentCharge.client_id == Client.id)
            .join(Property, RentCharge.property_id == Property.id)
            .filter(RentCharge.period_month == period)
            .filter(RentCharge.status.in_(("open", "part_paid")))
            .all()
        )
        for charge, client, prop in rows:
            outstanding = charge.outstanding()
            if outstanding <= 0:
                continue
            context = {
                "client_name": client.name,
                "property_name": prop.name,
                "month": period.strftime("%B %Y"),
                "amount": _money(outstanding),
                "days": offset,
            }
            out.append(_build(rule, context,
                              dedupe=f"rent_due:{charge.id}:{offset}",
                              entity_type="rent_charge", entity_id=charge.id,
                              link=f"/collections/{client.id}", client=client))
    return out


def _find_pdc_due(rule: NotificationRule, today: date) -> list[Finding]:
    out = []
    for days in rule.advance_list() or [0]:
        target = today + timedelta(days=days)
        rows = (
            db.session.query(Cheque, ClientContract, Client, Property)
            .join(ClientContract, Cheque.contract_id == ClientContract.id)
            .join(Client, ClientContract.client_id == Client.id)
            .join(Property, ClientContract.property_id == Property.id)
            .filter(Cheque.status == "received")
            .filter(Cheque.is_security.is_(False))
            .filter(Cheque.cheque_date == target)
            .all()
        )
        for cheque, contract, client, prop in rows:
            context = {
                "cheque_number": cheque.cheque_number,
                "bank_name": cheque.bank_name or "—",
                "amount": _money(cheque.amount),
                "cheque_date": cheque.cheque_date.isoformat(),
                "client_name": client.name,
                "property_name": prop.name,
                "days": days,
            }
            out.append(_build(rule, context,
                              dedupe=f"pdc_due:{cheque.id}:{days}",
                              entity_type="cheque", entity_id=cheque.id,
                              link=f"/contracts/{contract.id}", client=client))
    return out


def _find_cheque_bounced(rule: NotificationRule, today: date) -> list[Finding]:
    """Bounces are news the day they happen, so this ignores advance
    days and looks at what turned bad since yesterday."""
    rows = (
        db.session.query(Cheque, ClientContract, Client, Property)
        .join(ClientContract, Cheque.contract_id == ClientContract.id)
        .join(Client, ClientContract.client_id == Client.id)
        .join(Property, ClientContract.property_id == Property.id)
        .filter(Cheque.status == "bounced")
        .all()
    )
    out = []
    for cheque, contract, client, prop in rows:
        context = {
            "cheque_number": cheque.cheque_number,
            "amount": _money(cheque.amount),
            "client_name": client.name,
            "property_name": prop.name,
            "cheque_date": cheque.cheque_date.isoformat(),
        }
        out.append(_build(rule, context,
                          dedupe=f"cheque_bounced:{cheque.id}",
                          entity_type="cheque", entity_id=cheque.id,
                          link=f"/contracts/{contract.id}", client=client))
    return out


def _find_document_expiry(rule: NotificationRule, today: date) -> list[Finding]:
    out = []
    advance = rule.advance_list() or [30]
    horizon = max(advance)
    for row in expiring_documents(within_days=horizon, today=today):
        days_left = row.get("days_left")
        if days_left not in advance:
            continue
        context = {
            "category": (row.get("category") or "document").replace("_", " "),
            "entity_name": row.get("entity_name") or "—",
            "expiry_date": row.get("expiry_date"),
            "days": days_left,
            "doc_number": row.get("doc_number") or "—",
        }
        out.append(_build(rule, context,
                          dedupe=f"document_expiry:{row['id']}:{days_left}",
                          entity_type="attachment", entity_id=row["id"],
                          link="/alerts"))
    return out


def _find_approval_pending(rule: NotificationRule, today: date) -> list[Finding]:
    from .approvals import pending_counts
    counts = pending_counts()
    if not counts.get("total"):
        return []
    context = {"count": counts["total"], "date": today.isoformat()}
    return [_build(rule, context,
                   dedupe=f"approval_pending:{today.isoformat()}",
                   entity_type="approval_request", entity_id=None,
                   link="/approvals")]


FINDERS = {
    "contract_expiry": _find_contract_expiry,
    "agreement_expiry": _find_agreement_expiry,
    "rent_due": _find_rent_due,
    "pdc_due": _find_pdc_due,
    "cheque_bounced": _find_cheque_bounced,
    "document_expiry": _find_document_expiry,
    "approval_pending": _find_approval_pending,
}


def _build(rule: NotificationRule, context: dict, *, dedupe: str,
           entity_type=None, entity_id=None, link=None,
           client=None, landlord=None) -> Finding:
    subject_default, body_default = DEFAULT_TEMPLATES.get(rule.event, ("{event}", "{event}"))
    return Finding(
        event=rule.event,
        subject=email_service.render(rule.subject_template, context, subject_default),
        body=email_service.render(rule.body_template, context, body_default),
        dedupe_key=dedupe,
        entity_type=entity_type,
        entity_id=entity_id,
        link=link,
        client=client,
        landlord=landlord,
        context=context,
    )


# ----------------------------------------------------------------------
# Fan-out
# ----------------------------------------------------------------------

def _staff_user_ids(rule: NotificationRule) -> list[int]:
    query = User.query.filter(User.is_active.is_(True))
    codes = [c.strip() for c in (rule.staff_role_codes or "").split(",") if c.strip()]
    users = query.all()
    if not codes:
        return [u.id for u in users]
    picked = []
    for user in users:
        user_codes = {r.code for r in (user.roles or [])}
        if user_codes & set(codes):
            picked.append(user.id)
    return picked


def _extra_emails(rule: NotificationRule) -> list[str]:
    return [e.strip() for e in (rule.extra_emails or "").split(",")
            if email_service.valid_address(e.strip())]


def deliver_finding(rule: NotificationRule, finding: Finding, *, dry_run: bool = False) -> dict:
    """Send one finding down every channel the rule asks for.

    `dry_run` composes and reports without writing outbound rows — what
    the Preview button on the rules screen uses, so an operator can see
    exactly who would be contacted before switching a rule on.
    """
    planned: list[dict] = []
    channels = rule.channel_list()
    audiences = rule.audience_list()

    # --- who gets an email
    recipients: list[tuple[str, str]] = []          # (address, name)
    if "client" in audiences and finding.client is not None:
        if email_service.valid_address(finding.client.email):
            recipients.append((finding.client.email, finding.client.name))
    if "landlord" in audiences and finding.landlord is not None:
        if email_service.valid_address(finding.landlord.email):
            recipients.append((finding.landlord.email, finding.landlord.name))
    for address in _extra_emails(rule):
        recipients.append((address, "GreenTech"))

    if "email" in channels:
        for address, name in recipients:
            planned.append({"channel": "email", "to": address, "name": name})
            if dry_run:
                continue
            email_service.send_now(
                to_address=address, to_name=name,
                subject=finding.subject, body=finding.body,
                event=finding.event, rule_id=rule.id,
                entity_type=finding.entity_type, entity_id=finding.entity_id,
                dedupe_key=f"email:{finding.dedupe_key}:{address}",
            )

    if "telegram" in channels:
        text = f"{finding.subject}\n\n{finding.body}"
        planned.append({"channel": "telegram", "to": "staff group"})
        if not dry_run:
            telegram_service.send_now(
                text=text, event=finding.event, rule_id=rule.id,
                entity_type=finding.entity_type, entity_id=finding.entity_id,
                dedupe_key=f"telegram:{finding.dedupe_key}",
            )

    if "inapp" in channels or "push" in channels:
        user_ids = _staff_user_ids(rule)
        planned.append({"channel": "inapp", "to": f"{len(user_ids)} staff user(s)"})
        if not dry_run:
            for user_id in user_ids:
                inapp_service.create_for(
                    user_id=user_id, type=finding.event,
                    title=finding.subject, body=finding.body[:1000],
                    link=finding.link,
                )
    return {"dedupe_key": finding.dedupe_key, "deliveries": planned}


def evaluate_rule(rule: NotificationRule, today: date | None = None,
                  *, dry_run: bool = False) -> dict:
    today = today or date.today()
    finder = FINDERS.get(rule.event)
    if finder is None:
        return {"event": rule.event, "findings": 0, "results": [],
                "error": f"No finder for {rule.event}"}
    findings = finder(rule, today)
    results = [deliver_finding(rule, f, dry_run=dry_run) for f in findings]
    return {
        "event": rule.event,
        "event_label": EVENT_LABELS.get(rule.event, rule.event),
        "findings": len(findings),
        "results": results,
    }


def run_sweep(today: date | None = None, *, dry_run: bool = False,
              only_event: str | None = None) -> dict:
    """Evaluate every enabled rule. The daily task's whole body."""
    today = today or date.today()
    query = NotificationRule.query.filter(NotificationRule.is_enabled.is_(True))
    if only_event:
        query = query.filter(NotificationRule.event == only_event)

    per_event = []
    for rule in query.order_by(NotificationRule.event).all():
        per_event.append(evaluate_rule(rule, today, dry_run=dry_run))
    if not dry_run:
        db.session.commit()
    return {
        "date": today.isoformat(),
        "dry_run": dry_run,
        "rules_evaluated": len(per_event),
        "findings": sum(r["findings"] for r in per_event),
        "events": per_event,
    }


def seed_defaults() -> int:
    """Create one disabled rule per event so the settings screen has
    something to show. Only ever adds — never overwrites an operator's
    configuration."""
    existing = {r.event for r in NotificationRule.query.all()}
    defaults = {
        "contract_expiry": ([60, 30, 7], ["inapp", "email"], ["client"]),
        "agreement_expiry": ([90, 60, 30], ["inapp", "email"], ["landlord"]),
        "rent_due": ([7, 21], ["inapp", "email"], ["client"]),
        "pdc_due": ([3], ["inapp", "telegram"], ["staff"]),
        "cheque_bounced": ([], ["inapp", "telegram"], ["staff"]),
        "document_expiry": ([60, 30], ["inapp"], ["staff"]),
        "approval_pending": ([], ["inapp"], ["staff"]),
    }
    created = 0
    for event in sorted(NOTIFICATION_EVENTS):
        if event in existing:
            continue
        advance, channels, audiences = defaults.get(event, ([], ["inapp"], ["staff"]))
        db.session.add(NotificationRule(
            event=event, is_enabled=False, advance_days=advance,
            channels=channels, audiences=audiences,
        ))
        created += 1
    if created:
        db.session.flush()
    return created
