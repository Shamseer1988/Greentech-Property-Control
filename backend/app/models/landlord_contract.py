"""Per-unit allocation and amendment history for landlord contracts —
the `LandlordContract` (`property.py`) side of the ledger, mirroring
`ContractUnit`/`ContractAmendment` on the client side (`contract.py`).

Deliberately a separate table pair, not a shared one: a unit rented IN
from a landlord and a unit rented OUT to a client are two different
relationships that can both be true of the same unit at the same time,
so this must never share the client side's occupancy guard
(`services/contracts.units_held_on`) or its `units.occupancy_status`
projection (`services/contracts.recompute_unit_occupancy`).
"""
from sqlalchemy import (
    Column, String, Integer, Date, Numeric, Text, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


LANDLORD_AMENDMENT_TYPES = {
    "rent_change",
    "free_months",       # a grace period the LANDLORD granted us
    "units_added",
    "units_removed",
    "cancellation",
    "renewal",
    "dates_correction",
    "deposit_change",
}


class LandlordContractUnit(BaseModel):
    """One unit sourced from one landlord contract for a dated span.

    Mirrors `ContractUnit` exactly (`to_date` NULL means still held;
    releasing closes the row, never deletes it) except for `unit_rent`,
    which is informational only — a per-unit share for display when a
    floor or store is released and the whole-contract rent renegotiated.
    `LandlordContract.monthly_rent` (via its amendments) stays the one
    source of truth for what's actually due; never sum `unit_rent`.
    """

    __tablename__ = "landlord_contract_units"

    contract_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False, index=True)

    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=True, index=True)
    release_reason = Column(String(120), nullable=True)
    unit_rent = Column(Numeric(12, 2), nullable=True)

    contract = relationship("LandlordContract", back_populates="units")
    unit = relationship("Unit", lazy="joined")

    __table_args__ = (
        Index("ix_landlord_contract_units_unit_open", "unit_id", "to_date"),
    )

    def covers(self, on) -> bool:
        if self.from_date > on:
            return False
        return self.to_date is None or self.to_date >= on

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("from_date", "to_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if data.get("unit_rent") is not None:
            data["unit_rent"] = float(data["unit_rent"])
        if self.unit is not None:
            data["unit"] = {
                "id": self.unit.id,
                "unit_number": self.unit.unit_number,
                "unit_type": self.unit.unit_type,
                "floor_id": self.unit.floor_id,
            }
        return data


class LandlordContractAmendment(BaseModel):
    """A dated, versioned change to a landlord contract. Never edited in
    place — mirrors `ContractAmendment` plus the security-deposit pair,
    since a deposit top-up on renewal has nowhere else to be recorded."""

    __tablename__ = "landlord_contract_amendments"

    contract_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    amendment_number = Column(String(40), unique=True, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)

    amendment_type = Column(String(24), nullable=False, index=True)
    effective_date = Column(Date, nullable=False, index=True)

    old_rent = Column(Numeric(12, 2), nullable=True)
    new_rent = Column(Numeric(12, 2), nullable=True)
    free_months = Column(Integer, nullable=True)
    free_from_month = Column(Date, nullable=True)
    unit_ids = Column(Text, nullable=True)  # comma-separated ids touched

    old_start_date = Column(Date, nullable=True)
    new_start_date = Column(Date, nullable=True)
    old_expiry_date = Column(Date, nullable=True)
    new_expiry_date = Column(Date, nullable=True)

    old_security_deposit = Column(Numeric(12, 2), nullable=True)
    new_security_deposit = Column(Numeric(12, 2), nullable=True)

    reason = Column(String(160), nullable=True)
    remarks = Column(Text, nullable=True)

    contract = relationship("LandlordContract", back_populates="amendments")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("effective_date", "free_from_month",
                  "old_start_date", "new_start_date", "old_expiry_date", "new_expiry_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        for k in ("old_rent", "new_rent", "old_security_deposit", "new_security_deposit"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        data["unit_ids"] = (
            [int(x) for x in self.unit_ids.split(",") if x] if self.unit_ids else []
        )
        return data
