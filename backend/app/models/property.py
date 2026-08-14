from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Date,
    Numeric,
    ForeignKey,
    Text,
    Index,
    Computed,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


class PropertyType(BaseModel):
    """A property type the operator can pick when creating a property.

    Mirrors `ExpenseCategory` — a user-manageable master, deactivate-only,
    never hard-deleted. `Property.property_type` stores the `code`, not an
    FK, matching the free-text column that was already there; this table
    only replaces the hardcoded Python set that used to validate it.
    """

    __tablename__ = "property_types"

    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(80), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    remarks = Column(Text, nullable=True)

    def to_dict(self, exclude=None):
        return super().to_dict(exclude=exclude)


class Property(BaseModel):
    __tablename__ = "properties"

    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(160), nullable=False)
    property_type = Column(String(32), nullable=False)  # full_building, villa, etc.

    building_number = Column(String(64), nullable=True)
    zone = Column(String(64), nullable=True)
    street = Column(String(120), nullable=True)
    area = Column(String(120), nullable=True)
    city = Column(String(120), nullable=True, index=True)
    map_link = Column(Text, nullable=True)
    gps_lat = Column(Numeric(10, 7), nullable=True)
    gps_lng = Column(Numeric(10, 7), nullable=True)

    ownership_type = Column(String(16), default="rented", nullable=False)  # rented, company_owned, temporary
    status = Column(String(16), default="active", nullable=False, index=True)  # active, inactive, maintenance, vacated
    managed_by = Column(String(120), nullable=True)

    landlord_id = Column(Integer, ForeignKey("landlords.id", ondelete="SET NULL"), nullable=True, index=True)

    # Phase 6: total_floors / total_rooms / total_bed_capacity were
    # nullable, never written, and lived alongside the live aggregations
    # in routes.properties._counts_for(). Dropped to avoid two sources of
    # truth; the migrate-all CLI handles existing DBs.

    remarks = Column(Text, nullable=True)

    landlord = relationship("Landlord", lazy="joined")
    agreements = relationship(
        "LandlordContract", back_populates="property", lazy="select", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_properties_status_type", "status", "property_type"),
    )

    def active_agreement(self):
        return next((a for a in self.agreements if a.is_active), None)

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        # Decimal serialization
        for k in ("gps_lat", "gps_lng"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        active = self.active_agreement()
        data["active_agreement"] = active.to_dict() if active else None

        if self.landlord is not None:
            data["landlord"] = {
                "id": self.landlord.id,
                "code": self.landlord.code,
                "name": self.landlord.name,
                "mobile": self.landlord.mobile,
            }
        else:
            data["landlord"] = None
        return data


LANDLORD_CONTRACT_STATUSES = {"active", "expired", "cancelled", "renewed"}


class LandlordContract(BaseModel):
    """A landlord agreement — what GreenTech pays to rent a property in.

    Physically still the `property_agreements` table (renamed in Python
    only, so the ~10 existing read paths — reminders, dashboards, the
    agreement-expiry report, notification rules, `Property.to_dict()` —
    keep working unchanged against the `PropertyAgreement` alias below).

    `is_active` is a generated column, not a plain boolean, because its
    meaning predates this rename and is subtler than "status == active":
    the nightly expiry sweep (`tasks/expiry.py`) flips `renewal_status`
    to "expired" on a lapsed agreement but has always deliberately left
    `is_active` untouched, so a lapsed-but-not-yet-renewed agreement
    still counts as "current" everywhere that reads it. Redefining it as
    `status IN ('active', 'expired')` reproduces that exactly and makes
    the two flags impossible to drift apart (rule 10) — write `status`,
    never `is_active` directly (the DB rejects it: generated columns
    can't be set).
    """

    __tablename__ = "property_agreements"

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id", ondelete="RESTRICT"), nullable=False, index=True)

    # System-assigned, distinct from `agreement_number` (the landlord's
    # own paper reference, free text, optional).
    contract_number = Column(String(40), unique=True, nullable=True, index=True)
    agreement_number = Column(String(64), nullable=True)
    start_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False, index=True)

    monthly_rent = Column(Numeric(12, 2), nullable=True)
    security_deposit = Column(Numeric(12, 2), nullable=True)
    payment_terms = Column(String(120), nullable=True)
    notice_period = Column(String(64), nullable=True)
    renewal_status = Column(String(16), default="pending", nullable=False)

    kahramaa_account = Column(String(64), nullable=True)
    municipality_ref = Column(String(64), nullable=True)

    reminder_days_before_expiry = Column(Integer, default=90, nullable=False)

    status = Column(String(16), default="active", nullable=False, index=True)
    cancellation_date = Column(Date, nullable=True)
    cancellation_reason = Column(String(160), nullable=True)
    # Set when a renewal supersedes this contract — mirrors
    # ClientContract.renewed_to_id.
    renewed_to_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="SET NULL"), nullable=True)
    # How GreenTech pays the landlord — mirrors ClientContract.payment_mode.
    payment_mode = Column(String(8), default="cheque", nullable=False)
    # What was already owed at cutover, carried in like ClientContract's.
    opening_balance = Column(Numeric(12, 2), default=0, nullable=False)

    is_active = Column(
        Boolean,
        Computed("status IN ('active', 'expired')", persisted=True),
    )

    remarks = Column(Text, nullable=True)

    property = relationship("Property", back_populates="agreements")
    landlord = relationship("Landlord", lazy="joined")
    units = relationship(
        "LandlordContractUnit", back_populates="contract",
        lazy="select", cascade="all, delete-orphan",
    )
    amendments = relationship(
        "LandlordContractAmendment", back_populates="contract",
        lazy="select", cascade="all, delete-orphan",
        order_by="LandlordContractAmendment.id",
    )

    __table_args__ = (
        Index("ix_property_agreements_active_expiry", "is_active", "expiry_date"),
        Index("ix_property_agreements_status_expiry", "status", "expiry_date"),
    )

    def active_allocations(self, on=None):
        """Units held on `on` (default today) — mirrors
        ClientContract.active_allocations for the amendment/detail code
        that treats both contract types the same way."""
        from datetime import date as _date
        on = on or _date.today()
        return [a for a in (self.units or []) if a.covers(on)]

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("monthly_rent", "security_deposit", "opening_balance"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        for k in ("start_date", "expiry_date", "cancellation_date"):
            if data.get(k) is not None and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if self.landlord is not None:
            data["landlord"] = {
                "id": self.landlord.id,
                "code": self.landlord.code,
                "name": self.landlord.name,
            }
        if self.property is not None:
            data["property"] = {
                "id": self.property.id,
                "code": self.property.code,
                "name": self.property.name,
            }
        return data


# Back-compat alias — every existing import (`from ..models import
# PropertyAgreement`) keeps working unchanged. Note this covers the
# class name only: `relationship("PropertyAgreement", ...)` *strings*
# resolve through SQLAlchemy's declarative registry by the real class
# name, so those three call sites (Property.agreements,
# LandlordRenewal.old/new_agreement) must reference "LandlordContract".
PropertyAgreement = LandlordContract
