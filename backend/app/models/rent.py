"""Rent charges and receipts — the money ledger.

Shaped by docs/ACCOUNTING-RULES.md:

  * **No hard delete** (rule 1). A wrong receipt is *voided* with a
    reason and stays visible; its allocations are reversed so the dues
    it paid reopen.
  * **Posted transactions are immutable** (rule 2). A receipt's amount,
    date and party never change after posting — corrections are a void
    plus a fresh receipt.
  * **Gapless numbering** (rule 4). `RV-YYYYMM-NNNN`, issued inside the
    same transaction that creates the row, never reused — a voided
    receipt keeps its number.
  * **Allocation discipline** (rule 8). Receipts settle the oldest open
    charge first unless the operator overrides, and the override is
    recorded. Anything unallocated sits as a client advance.
"""
from datetime import date

from sqlalchemy import (
    Column, String, Integer, Date, Numeric, Text, Boolean, ForeignKey, Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


CHARGE_STATUSES = {"open", "part_paid", "paid", "cancelled"}
RECEIPT_MODES = {"cash", "cheque", "online", "adjustment"}
RECEIPT_STATUSES = {"posted", "voided"}


class RentCharge(BaseModel):
    """What a client owes for one month on one contract.

    One row per contract per month. Regenerating a month updates an
    untouched row and refuses to disturb one that has money against it.
    """

    __tablename__ = "rent_charges"

    contract_id = Column(Integer, ForeignKey("client_contracts.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"),
                       nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="RESTRICT"),
                         nullable=False, index=True)

    # Always the 1st of the month the charge belongs to.
    period_month = Column(Date, nullable=False, index=True)

    amount = Column(Numeric(12, 2), nullable=False)
    allocated = Column(Numeric(12, 2), default=0, nullable=False)

    # Why the amount is what it is — so a 0 or an odd figure explains
    # itself on screen without re-deriving it.
    is_free_month = Column(Boolean, default=False, nullable=False)
    is_opening_balance = Column(Boolean, default=False, nullable=False)
    proration_note = Column(String(120), nullable=True)

    status = Column(String(12), default="open", nullable=False, index=True)
    remarks = Column(Text, nullable=True)

    contract = relationship("ClientContract", lazy="joined")
    client = relationship("Client", lazy="joined")
    allocations = relationship(
        "ReceiptAllocation", back_populates="charge",
        lazy="select", cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("contract_id", "period_month", name="uq_rent_charge_contract_month"),
        Index("ix_rent_charges_client_month", "client_id", "period_month"),
        Index("ix_rent_charges_status_month", "status", "period_month"),
    )

    # Column defaults are applied by the database at INSERT, so before a
    # flush `allocated` is still None in Python. Coerce here so status
    # can be computed on a brand-new row.
    def _amount(self) -> float:
        return float(self.amount or 0)

    def _allocated(self) -> float:
        return float(self.allocated or 0)

    def outstanding(self) -> float:
        return round(self._amount() - self._allocated(), 2)

    def recompute_status(self) -> None:
        if self._amount() == 0:
            self.status = "paid"
        elif self.outstanding() <= 0.004:   # cent tolerance
            self.status = "paid"
        elif self._allocated() > 0:
            self.status = "part_paid"
        else:
            self.status = "open"

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("period_month") and not isinstance(data["period_month"], str):
            data["period_month"] = data["period_month"].isoformat()
        for k in ("amount", "allocated"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        data["outstanding"] = self.outstanding()
        if self.client is not None:
            data["client"] = {"id": self.client.id, "code": self.client.code,
                              "name": self.client.name}
        if self.contract is not None:
            data["contract_number"] = self.contract.contract_number
        return data


class Receipt(BaseModel):
    """Money received from a client. Posted once, voided if wrong."""

    __tablename__ = "receipts"

    receipt_number = Column(String(40), unique=True, nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"),
                       nullable=False, index=True)

    receipt_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    mode = Column(String(12), nullable=False)

    # Bank/cheque reference, or the cheque this receipt came from.
    reference = Column(String(80), nullable=True)
    cheque_id = Column(Integer, ForeignKey("cheques.id", ondelete="SET NULL"),
                       nullable=True, index=True)

    status = Column(String(12), default="posted", nullable=False, index=True)
    void_reason = Column(String(160), nullable=True)
    voided_at = Column(Date, nullable=True)
    voided_by = Column(Integer, nullable=True)

    remarks = Column(Text, nullable=True)

    client = relationship("Client", lazy="joined")
    allocations = relationship(
        "ReceiptAllocation", back_populates="receipt",
        lazy="select", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_receipts_client_date", "client_id", "receipt_date"),
    )

    def allocated_total(self) -> float:
        return round(sum(float(a.amount) for a in (self.allocations or [])), 2)

    def unallocated(self) -> float:
        """Money on account — paid but not yet applied to a charge."""
        if self.status == "voided":
            return 0.0
        return round(float(self.amount) - self.allocated_total(), 2)

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("receipt_date", "voided_at"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if data.get("amount") is not None:
            data["amount"] = float(data["amount"])
        data["allocated"] = self.allocated_total()
        data["unallocated"] = self.unallocated()
        if self.client is not None:
            data["client"] = {"id": self.client.id, "code": self.client.code,
                              "name": self.client.name}
        return data


class ReceiptAllocation(BaseModel):
    """How much of a receipt settled which charge."""

    __tablename__ = "receipt_allocations"

    receipt_id = Column(Integer, ForeignKey("receipts.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    charge_id = Column(Integer, ForeignKey("rent_charges.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    # True when the operator picked the charge instead of oldest-first.
    is_manual = Column(Boolean, default=False, nullable=False)

    receipt = relationship("Receipt", back_populates="allocations")
    charge = relationship("RentCharge", back_populates="allocations")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("amount") is not None:
            data["amount"] = float(data["amount"])
        if self.charge is not None:
            data["period_month"] = (
                self.charge.period_month.isoformat() if self.charge.period_month else None
            )
        return data
