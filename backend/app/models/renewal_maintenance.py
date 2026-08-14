from datetime import date, datetime
from sqlalchemy import (
    Column, String, Integer, Date, Numeric, Text, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


MAINTENANCE_ENTITY_TYPES = {"property", "unit"}
MAINTENANCE_STATUSES = {"in_progress", "completed", "cancelled"}


class LandlordRenewal(BaseModel):
    __tablename__ = "landlord_renewals"

    transaction_number = Column(String(40), unique=True, nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    landlord_id = Column(Integer, ForeignKey("landlords.id", ondelete="RESTRICT"), nullable=False, index=True)

    old_agreement_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="SET NULL"), nullable=True)
    new_agreement_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="SET NULL"), nullable=True)

    renewal_date = Column(Date, nullable=False, default=date.today)
    old_expiry_date = Column(Date, nullable=True)
    new_start_date = Column(Date, nullable=False)
    new_expiry_date = Column(Date, nullable=False)

    old_monthly_rent = Column(Numeric(12, 2), nullable=True)
    new_monthly_rent = Column(Numeric(12, 2), nullable=True)

    remarks = Column(Text, nullable=True)
    approved_by = Column(Integer, nullable=True)
    status = Column(String(20), default="completed", nullable=False, index=True)

    property = relationship("Property", lazy="joined")
    landlord = relationship("Landlord", lazy="joined")
    old_agreement = relationship("LandlordContract", foreign_keys=[old_agreement_id], lazy="joined")
    new_agreement = relationship("LandlordContract", foreign_keys=[new_agreement_id], lazy="joined")

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("renewal_date", "old_expiry_date", "new_start_date", "new_expiry_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        for k in ("old_monthly_rent", "new_monthly_rent"):
            if data.get(k) is not None:
                data[k] = float(data[k])
        data["property"] = {
            "id": self.property.id, "code": self.property.code, "name": self.property.name,
        } if self.property else None
        data["landlord"] = {
            "id": self.landlord.id, "code": self.landlord.code, "name": self.landlord.name,
        } if self.landlord else None
        data["old_agreement"] = self.old_agreement.to_dict() if self.old_agreement else None
        data["new_agreement"] = self.new_agreement.to_dict() if self.new_agreement else None
        return data


class MaintenanceRecord(BaseModel):
    __tablename__ = "maintenance_records"

    transaction_number = Column(String(40), unique=True, nullable=False, index=True)
    entity_type = Column(String(16), nullable=False, index=True)  # property / unit
    entity_id = Column(Integer, nullable=False, index=True)

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True)

    start_date = Column(Date, nullable=False, default=date.today)
    expected_end_date = Column(Date, nullable=True)
    actual_end_date = Column(Date, nullable=True)

    reason = Column(String(120), nullable=True)
    prior_status = Column(String(20), nullable=False)
    status = Column(String(16), default="in_progress", nullable=False, index=True)
    remarks = Column(Text, nullable=True)
    approved_by = Column(Integer, nullable=True)

    property = relationship("Property", lazy="joined")

    __table_args__ = (
        Index("ix_maintenance_entity", "entity_type", "entity_id"),
        Index("ix_maintenance_status_entity", "status", "entity_type"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("start_date", "expected_end_date", "actual_end_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if self.property:
            data["property"] = {
                "id": self.property.id, "code": self.property.code, "name": self.property.name,
            }
        return data


def generate_renewal_or_maintenance_number(prefix: str) -> str:
    from ..extensions import db

    today = datetime.utcnow().date()
    month_key = today.strftime("%Y%m")
    like = f"{prefix}-{month_key}-%"
    model_map = {
        "LRENEW": LandlordRenewal,
        "MAINT": MaintenanceRecord,
    }
    model = model_map[prefix]
    last = (
        db.session.query(model.transaction_number)
        .filter(model.transaction_number.like(like))
        .order_by(model.transaction_number.desc())
        .limit(1)
        .scalar()
    )
    if last:
        try:
            seq = int(last.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}-{month_key}-{seq:04d}"
