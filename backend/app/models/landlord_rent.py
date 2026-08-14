"""Landlord charges — what GreenTech owes a landlord for one month on
one landlord contract, mirroring `models/rent.py::RentCharge` exactly so
`services/landlord_rent.py` can mirror `services/rent.py` line for line.

One difference from the client side: `seq` lets a second row exist for
the same contract/month (a one-off municipality fee, a negotiated
catch-up) without editing a posted charge — ACCOUNTING-RULES rule 2.
"""
from sqlalchemy import (
    Column, String, Integer, Date, Numeric, Text, Boolean, ForeignKey, Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


LANDLORD_CHARGE_STATUSES = {"open", "part_paid", "paid", "cancelled"}


class LandlordCharge(BaseModel):
    """What GreenTech owes a landlord for one month on one contract."""

    __tablename__ = "landlord_charges"

    contract_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="RESTRICT"),
                         nullable=False, index=True)

    # Always the 1st of the month the charge belongs to.
    period_month = Column(Date, nullable=False, index=True)
    # Discriminator: a second row for the same contract/month is a
    # deliberate extra charge (a fee, a catch-up), not an edit.
    seq = Column(Integer, default=1, nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)
    allocated = Column(Numeric(12, 2), default=0, nullable=False)

    is_free_month = Column(Boolean, default=False, nullable=False)
    proration_note = Column(String(120), nullable=True)

    status = Column(String(12), default="open", nullable=False, index=True)
    remarks = Column(Text, nullable=True)

    contract = relationship("LandlordContract", lazy="joined")
    landlord = relationship("Landlord", lazy="joined")
    property = relationship("Property", lazy="joined")
    allocations = relationship(
        "LandlordPaymentAllocation", back_populates="charge",
        lazy="select", cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("contract_id", "period_month", "seq",
                         name="uq_landlord_charge_contract_month_seq"),
        Index("ix_landlord_charges_landlord_month", "landlord_id", "period_month"),
        Index("ix_landlord_charges_status_month", "status", "period_month"),
    )

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
        if self.landlord is not None:
            data["landlord"] = {"id": self.landlord.id, "code": self.landlord.code,
                                "name": self.landlord.name}
        if self.property is not None:
            data["property"] = {"id": self.property.id, "code": self.property.code,
                                "name": self.property.name}
        if self.contract is not None:
            data["contract_number"] = self.contract.contract_number
        return data


class LandlordPaymentAllocation(BaseModel):
    """How much of a landlord payment settled which charge."""

    __tablename__ = "landlord_payment_allocations"

    payment_id = Column(Integer, ForeignKey("landlord_payments.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    charge_id = Column(Integer, ForeignKey("landlord_charges.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    is_manual = Column(Boolean, default=False, nullable=False)

    payment = relationship("LandlordPayment", back_populates="allocations")
    charge = relationship("LandlordCharge", back_populates="allocations")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("amount") is not None:
            data["amount"] = float(data["amount"])
        if self.charge is not None:
            data["period_month"] = (
                self.charge.period_month.isoformat() if self.charge.period_month else None
            )
        return data
