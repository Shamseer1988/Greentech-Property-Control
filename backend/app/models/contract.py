"""Client contracts — the agreements GreenTech signs with tenants.

Three rules from docs/ACCOUNTING-RULES.md shape this schema:

  * **History is never overwritten** (rule 3). Rent changes, free months,
    cancellations and unit changes are ``ContractAmendment`` rows with an
    effective date. The contract row keeps its *current* values for fast
    reads, but every change is reconstructable from the amendments.
  * **Occupancy is computed, never typed** (rule 10). Which units a
    contract holds lives in ``ContractUnit`` with ``from_date`` /
    ``to_date`` — releasing a unit closes the row, it never deletes it,
    so "who held unit 101 last March?" stays answerable.
  * **Cheques are stateful, never edited** (rule 9). Each PDC transition
    is a ``ChequeEvent`` row; a bounced cheque is replaced by a new one
    linked back to it.
"""
from datetime import date

from sqlalchemy import (
    Column, String, Integer, Date, Numeric, Text, Boolean, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


PAYMENT_MODES = {"cash", "cheque", "online"}

CONTRACT_STATUSES = {
    "active",      # running
    "cancelled",   # ended early by amendment
    "expired",     # ran to its expiry date
    "renewed",     # superseded by a renewal contract
}

AMENDMENT_TYPES = {
    "rent_change",
    "free_months",
    "units_added",
    "units_removed",
    "cancellation",
    "renewal",
    "dates_correction",
}

CHEQUE_STATUSES = {"received", "deposited", "cleared", "bounced", "replaced", "returned"}


class ClientContract(BaseModel):
    __tablename__ = "client_contracts"

    contract_number = Column(String(40), unique=True, nullable=False, index=True)

    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)

    start_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False, index=True)

    # Current values. Their history lives in ContractAmendment.
    monthly_rent = Column(Numeric(12, 2), nullable=False)
    payment_mode = Column(String(8), nullable=False, index=True)

    # Cash clients often pay a deposit; cheque clients hand over a
    # security cheque instead (see Cheque.is_security).
    security_deposit = Column(Numeric(12, 2), nullable=True)
    # The "OP Dec-2025" column of the master file — what they already owed
    # when the contract was brought into the system.
    opening_balance = Column(Numeric(12, 2), default=0, nullable=False)

    status = Column(String(16), default="active", nullable=False, index=True)
    cancellation_date = Column(Date, nullable=True)
    cancellation_reason = Column(String(160), nullable=True)

    # Set when a renewal supersedes this contract.
    renewed_to_id = Column(Integer, ForeignKey("client_contracts.id", ondelete="SET NULL"), nullable=True)

    remarks = Column(Text, nullable=True)

    client = relationship("Client", lazy="joined")
    property = relationship("Property", lazy="joined")
    allocations = relationship(
        "ContractUnit", back_populates="contract",
        lazy="select", cascade="all, delete-orphan",
    )
    amendments = relationship(
        "ContractAmendment", back_populates="contract",
        lazy="select", cascade="all, delete-orphan",
        order_by="ContractAmendment.id",
    )
    cheques = relationship(
        "Cheque", back_populates="contract",
        lazy="select", cascade="all, delete-orphan",
        order_by="Cheque.cheque_date",
    )

    __table_args__ = (
        Index("ix_client_contracts_status_expiry", "status", "expiry_date"),
    )

    def active_allocations(self, on: date | None = None) -> list["ContractUnit"]:
        """Allocations held on `on` (default today)."""
        on = on or date.today()
        return [a for a in (self.allocations or []) if a.covers(on)]

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("start_date", "expiry_date", "cancellation_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        for k in ("monthly_rent", "security_deposit", "opening_balance"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        if self.client is not None:
            data["client"] = {
                "id": self.client.id, "code": self.client.code,
                "name": self.client.name, "name_ar": self.client.name_ar,
            }
        if self.property is not None:
            data["property"] = {
                "id": self.property.id, "code": self.property.code,
                "name": self.property.name,
            }
        return data


class ContractUnit(BaseModel):
    """One unit held by one contract for a dated span.

    ``to_date`` NULL means still held. Releasing a unit sets ``to_date``;
    the row survives so past occupancy stays reconstructable.
    """

    __tablename__ = "contract_units"

    contract_id = Column(Integer, ForeignKey("client_contracts.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False, index=True)

    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=True, index=True)
    release_reason = Column(String(120), nullable=True)

    contract = relationship("ClientContract", back_populates="allocations")
    unit = relationship("Unit", lazy="joined")

    __table_args__ = (
        Index("ix_contract_units_unit_open", "unit_id", "to_date"),
    )

    def covers(self, on: date) -> bool:
        if self.from_date > on:
            return False
        return self.to_date is None or self.to_date >= on

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("from_date", "to_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if self.unit is not None:
            data["unit"] = {
                "id": self.unit.id,
                "unit_number": self.unit.unit_number,
                "unit_type": self.unit.unit_type,
                "floor_id": self.unit.floor_id,
            }
        return data


class ContractAmendment(BaseModel):
    """A dated, versioned change to a contract. Never edited in place."""

    __tablename__ = "contract_amendments"

    contract_id = Column(Integer, ForeignKey("client_contracts.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    amendment_number = Column(String(40), unique=True, nullable=False, index=True)
    # Sequence within the contract: 1, 2, 3 … so the order is explicit.
    sequence = Column(Integer, nullable=False)

    amendment_type = Column(String(24), nullable=False, index=True)
    effective_date = Column(Date, nullable=False, index=True)

    # Type-specific payload, kept as plain columns where they are queried
    # and JSON-ish text where they are only displayed.
    old_rent = Column(Numeric(12, 2), nullable=True)
    new_rent = Column(Numeric(12, 2), nullable=True)
    free_months = Column(Integer, nullable=True)
    free_from_month = Column(Date, nullable=True)
    unit_ids = Column(Text, nullable=True)  # comma-separated ids touched

    # dates_correction only — fixing a data-entry mistake in the
    # original start/expiry date, not a genuine new term (that's
    # `renewal`, which supersedes the contract with a new one instead).
    old_start_date = Column(Date, nullable=True)
    new_start_date = Column(Date, nullable=True)
    old_expiry_date = Column(Date, nullable=True)
    new_expiry_date = Column(Date, nullable=True)

    reason = Column(String(160), nullable=True)
    remarks = Column(Text, nullable=True)

    contract = relationship("ClientContract", back_populates="amendments")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("effective_date", "free_from_month",
                  "old_start_date", "new_start_date", "old_expiry_date", "new_expiry_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        for k in ("old_rent", "new_rent"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        data["unit_ids"] = (
            [int(x) for x in self.unit_ids.split(",") if x] if self.unit_ids else []
        )
        return data


class Cheque(BaseModel):
    """A post-dated cheque held against a contract.

    An annual cheque contract means 12 rent cheques plus one security
    cheque (``is_security``). The security cheque is not part of the rent
    schedule and is returned, not deposited, at the end.
    """

    __tablename__ = "cheques"

    contract_id = Column(Integer, ForeignKey("client_contracts.id", ondelete="CASCADE"),
                         nullable=False, index=True)

    cheque_number = Column(String(40), nullable=False)
    bank_name = Column(String(120), nullable=True)
    cheque_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)

    is_security = Column(Boolean, default=False, nullable=False)
    # Which rent month this cheque covers (1st of the month). NULL for
    # the security cheque.
    for_month = Column(Date, nullable=True, index=True)

    status = Column(String(12), default="received", nullable=False, index=True)
    # Replacement chain after a bounce.
    replaces_cheque_id = Column(Integer, ForeignKey("cheques.id", ondelete="SET NULL"), nullable=True)

    remarks = Column(Text, nullable=True)

    contract = relationship("ClientContract", back_populates="cheques")
    events = relationship(
        "ChequeEvent", back_populates="cheque",
        lazy="select", cascade="all, delete-orphan", order_by="ChequeEvent.id",
    )

    __table_args__ = (
        Index("ix_cheques_status_date", "status", "cheque_date"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("cheque_date", "for_month"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if data.get("amount") is not None:
            data["amount"] = float(data["amount"])
        return data


class ChequeEvent(BaseModel):
    """One dated transition in a cheque's life. Append-only."""

    __tablename__ = "cheque_events"

    cheque_id = Column(Integer, ForeignKey("cheques.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    event_type = Column(String(12), nullable=False)  # a CHEQUE_STATUSES value
    event_date = Column(Date, nullable=False, default=date.today)
    bank_reference = Column(String(80), nullable=True)
    reason = Column(String(160), nullable=True)   # bounce reason
    remarks = Column(Text, nullable=True)

    cheque = relationship("Cheque", back_populates="events")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("event_date") and not isinstance(data["event_date"], str):
            data["event_date"] = data["event_date"].isoformat()
        return data
