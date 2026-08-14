"""Notification rules and the outbound message log.

Two tables:

``notification_rules`` is the operator's configuration — for each event
(a contract about to expire, rent falling due, a cheque bouncing), how
far in advance to warn, down which channels, and to whom.

``outbound_messages`` is one row per delivery *attempt*, on any channel.
It is both the sent-mail log the operator can audit and the mechanism
that stops a daily sweep re-sending the same reminder every morning: a
message carries a ``dedupe_key`` that is unique, so the second attempt
to warn about the same thing on the same day simply doesn't insert.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from ..extensions import db
from .base import BaseModel


# Events a rule can fire on. The value is what the evaluator dispatches
# on and what a template is keyed by, so it is part of the data model —
# renaming one is a migration, not a refactor.
NOTIFICATION_EVENTS = {
    "contract_expiry",      # a client contract is running out
    "agreement_expiry",     # a landlord agreement is running out
    "rent_due",             # a rent charge is due / overdue
    "pdc_due",              # a post-dated cheque is ready to bank
    "cheque_bounced",       # a cheque came back
    "document_expiry",      # CR / QID / title deed expiring
    "approval_pending",     # something is waiting on an approver
}

EVENT_LABELS = {
    "contract_expiry": "Client contract expiring",
    "agreement_expiry": "Landlord agreement expiring",
    "rent_due": "Rent due",
    "pdc_due": "Cheque ready to bank",
    "cheque_bounced": "Cheque bounced",
    "document_expiry": "Document expiring",
    "approval_pending": "Approval waiting",
}

CHANNELS = {"inapp", "email", "telegram", "push"}

# Who a rule can address. `staff` resolves to portal users by role;
# `client` / `landlord` resolve to the party the event is about, which
# is why an outward-facing channel plus a party audience is the only
# combination that can email someone outside the company.
AUDIENCES = {"staff", "client", "landlord"}

MESSAGE_STATUSES = {"queued", "sent", "failed", "skipped"}


class NotificationRule(BaseModel):
    __tablename__ = "notification_rules"

    event = Column(String(32), nullable=False, index=True)
    is_enabled = Column(Boolean, default=False, nullable=False)

    # Days before the date to warn — e.g. [60, 30, 7] warns two months,
    # one month and a week out. An empty list on a "due" style event
    # means fire on the day itself.
    advance_days = Column(db.JSON().with_variant(JSONB, "postgresql"),
                          nullable=False, default=list)

    channels = Column(db.JSON().with_variant(JSONB, "postgresql"),
                      nullable=False, default=list)
    audiences = Column(db.JSON().with_variant(JSONB, "postgresql"),
                       nullable=False, default=list)

    # Extra fixed recipients (the accounts mailbox, a manager) that get
    # the message regardless of who the event is about.
    extra_emails = Column(Text, nullable=True)          # comma separated
    staff_role_codes = Column(Text, nullable=True)      # comma separated

    subject_template = Column(Text, nullable=True)
    body_template = Column(Text, nullable=True)

    remarks = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_notification_rules_event_enabled", "event", "is_enabled"),
    )

    def channel_list(self) -> list[str]:
        return [c for c in (self.channels or []) if c in CHANNELS]

    def audience_list(self) -> list[str]:
        return [a for a in (self.audiences or []) if a in AUDIENCES]

    def advance_list(self) -> list[int]:
        out = []
        for value in (self.advance_days or []):
            try:
                out.append(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(set(out), reverse=True)

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        data["event_label"] = EVENT_LABELS.get(self.event, self.event)
        data["advance_days"] = self.advance_list()
        data["channels"] = self.channel_list()
        data["audiences"] = self.audience_list()
        return data


class OutboundMessage(BaseModel):
    """One delivery attempt on one channel.

    Never deleted — this is the record of what the portal said to a
    client on the company's behalf, and it has to survive the same way a
    receipt does.
    """
    __tablename__ = "outbound_messages"

    channel = Column(String(12), nullable=False, index=True)
    event = Column(String(32), nullable=True, index=True)
    rule_id = Column(Integer, ForeignKey("notification_rules.id", ondelete="SET NULL"),
                     nullable=True)

    # What the message is about, so the log can link back.
    entity_type = Column(String(48), nullable=True)
    entity_id = Column(Integer, nullable=True)

    to_address = Column(String(320), nullable=True)   # email / chat id
    to_name = Column(String(160), nullable=True)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)

    status = Column(String(12), default="queued", nullable=False, index=True)
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)

    # Identity of the thing being announced: event + entity + the
    # occasion (the advance-day bucket, or the month). Unique, so a
    # sweep that runs twice cannot say the same thing twice.
    dedupe_key = Column(String(200), unique=True, nullable=True, index=True)

    # True when a human pressed send rather than a rule firing.
    is_manual = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_outbound_messages_entity", "entity_type", "entity_id"),
        Index("ix_outbound_messages_status_channel", "status", "channel"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("sent_at") and not isinstance(data["sent_at"], str):
            data["sent_at"] = data["sent_at"].isoformat()
        return data
