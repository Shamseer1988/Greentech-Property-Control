"""Landlord payments and expenses — the outgoing side of the ledger.

This is the module that closes the gap the accounting software leaves:
it has no property-wise allocation, so it can tell you the company paid
139,175 for electricity in June but not which camp burnt it. Here every
expense either names a property or is explicitly company-level, which is
what makes per-property profit and loss computable.

Follows docs/ACCOUNTING-RULES.md: payments carry gapless `PV-` numbers,
are voided rather than deleted, and imported rows keep a pointer back to
the file and line they came from (rule 6).
"""
from datetime import date

from sqlalchemy import (
    Column, String, Integer, Date, Numeric, Text, Boolean, ForeignKey, Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


PAYMENT_MODES = {"cash", "cheque", "online", "adjustment"}
PAYMENT_STATUSES = {"posted", "voided"}

# Direct costs belong to a property and feed its P&L; indirect ones are
# company overhead (salary, fuel, telephone) and stay at company level.
CATEGORY_KINDS = {"direct", "indirect", "income"}

EXPENSE_SOURCES = {"manual", "import"}


class ExpenseCategory(BaseModel):
    """A line of the P&L, named as the accounting software names it."""

    __tablename__ = "expense_categories"

    code = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(12), default="indirect", nullable=False, index=True)
    # Direct costs are expected to name a property; the import warns when
    # one arrives unallocated.
    is_property_wise = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    remarks = Column(Text, nullable=True)

    def to_dict(self, exclude=None):
        return super().to_dict(exclude=exclude)


class LedgerMapping(BaseModel):
    """Remembers which accounting ledger name feeds which category.

    Mapped once on the first import, reused every month after
    (ACCOUNTING-RULES rule 4 of the plan: "mapping saved once, reused").
    """

    __tablename__ = "ledger_mappings"

    ledger_name = Column(String(160), unique=True, nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("expense_categories.id", ondelete="CASCADE"),
                         nullable=False, index=True)

    category = relationship("ExpenseCategory", lazy="joined")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if self.category is not None:
            data["category"] = {
                "id": self.category.id, "code": self.category.code,
                "name": self.category.name, "kind": self.category.kind,
                "is_property_wise": self.category.is_property_wise,
            }
        return data


class ExpenseImportBatch(BaseModel):
    """One accounting-software file, imported once.

    `file_hash` makes a re-import of the same file for the same period a
    detectable duplicate rather than a silent double-post.
    """

    __tablename__ = "expense_import_batches"

    batch_number = Column(String(40), unique=True, nullable=False, index=True)
    original_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)

    period_from = Column(Date, nullable=True)
    period_to = Column(Date, nullable=True)
    period_month = Column(Date, nullable=False, index=True)

    # What the file said its own totals were, so a later reader can see
    # the import reconciled at the time it was posted.
    reported_revenue = Column(Numeric(14, 2), nullable=True)
    reported_direct = Column(Numeric(14, 2), nullable=True)
    reported_indirect = Column(Numeric(14, 2), nullable=True)
    reported_net_profit = Column(Numeric(14, 2), nullable=True)

    lines_imported = Column(Integer, default=0, nullable=False)
    status = Column(String(12), default="posted", nullable=False, index=True)
    remarks = Column(Text, nullable=True)

    expenses = relationship("Expense", back_populates="batch", lazy="select")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("period_from", "period_to", "period_month"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        for k in ("reported_revenue", "reported_direct", "reported_indirect",
                  "reported_net_profit"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        return data


class Expense(BaseModel):
    """One cost, for one month, optionally against one property."""

    __tablename__ = "expenses"

    category_id = Column(Integer, ForeignKey("expense_categories.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    # NULL means company-level overhead, not attributable to a property.
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="RESTRICT"),
                         nullable=True, index=True)

    period_month = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)

    source = Column(String(8), default="manual", nullable=False)
    batch_id = Column(Integer, ForeignKey("expense_import_batches.id", ondelete="SET NULL"),
                      nullable=True, index=True)
    # The ledger name exactly as the file spelled it — the audit trail
    # back to the source document.
    ledger_name = Column(String(160), nullable=True)

    reference = Column(String(80), nullable=True)
    remarks = Column(Text, nullable=True)

    # Void support, mirroring LandlordPayment: a posted expense is
    # corrected by voiding it and posting a fresh one, never edited
    # (docs/ACCOUNTING-RULES.md rule 2).
    status = Column(String(12), default="posted", nullable=False, index=True)
    void_reason = Column(String(160), nullable=True)
    voided_at = Column(Date, nullable=True)
    voided_by = Column(Integer, nullable=True)

    category = relationship("ExpenseCategory", lazy="joined")
    property = relationship("Property", lazy="joined")
    batch = relationship("ExpenseImportBatch", back_populates="expenses")

    __table_args__ = (
        Index("ix_expenses_property_month", "property_id", "period_month"),
        Index("ix_expenses_month_category", "period_month", "category_id"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("period_month") and not isinstance(data["period_month"], str):
            data["period_month"] = data["period_month"].isoformat()
        if data.get("amount") is not None:
            data["amount"] = float(data["amount"])
        if data.get("voided_at") and not isinstance(data["voided_at"], str):
            data["voided_at"] = data["voided_at"].isoformat()
        if self.category is not None:
            data["category"] = {
                "id": self.category.id, "code": self.category.code,
                "name": self.category.name, "kind": self.category.kind,
            }
        if self.property is not None:
            data["property"] = {"id": self.property.id, "code": self.property.code,
                                "name": self.property.name}
        return data


class LandlordPayment(BaseModel):
    """Rent paid to a landlord for a property — the workbook's
    "Rent Paid" line, but property-wise by construction."""

    __tablename__ = "landlord_payments"

    voucher_number = Column(String(40), unique=True, nullable=False, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    # Nullable: older payments (and any manual one-off) may not name a
    # contract. When present, allocation is scoped to it via the
    # contract's (landlord_id, property_id) — see services/landlord_rent.py.
    contract_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="SET NULL"),
                         nullable=True, index=True)

    period_month = Column(Date, nullable=False, index=True)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    mode = Column(String(12), nullable=False)
    reference = Column(String(80), nullable=True)

    status = Column(String(12), default="posted", nullable=False, index=True)
    void_reason = Column(String(160), nullable=True)
    voided_at = Column(Date, nullable=True)
    voided_by = Column(Integer, nullable=True)

    remarks = Column(Text, nullable=True)

    landlord = relationship("Landlord", lazy="joined")
    property = relationship("Property", lazy="joined")
    allocations = relationship(
        "LandlordPaymentAllocation", back_populates="payment",
        lazy="select", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_landlord_payments_property_month", "property_id", "period_month"),
    )

    def allocated_total(self) -> float:
        return round(sum(float(a.amount) for a in (self.allocations or [])), 2)

    def unallocated(self) -> float:
        if self.status == "voided":
            return 0.0
        return round(float(self.amount) - self.allocated_total(), 2)

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("period_month", "payment_date", "voided_at"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if data.get("amount") is not None:
            data["amount"] = float(data["amount"])
        data["allocated"] = self.allocated_total()
        data["unallocated"] = self.unallocated()
        if self.landlord is not None:
            data["landlord"] = {"id": self.landlord.id, "code": self.landlord.code,
                                "name": self.landlord.name}
        if self.property is not None:
            data["property"] = {"id": self.property.id, "code": self.property.code,
                                "name": self.property.name}
        return data
