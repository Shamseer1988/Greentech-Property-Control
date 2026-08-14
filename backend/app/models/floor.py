from sqlalchemy import Column, String, Integer, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import BaseModel


class Floor(BaseModel):
    __tablename__ = "floors"

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    floor_number = Column(String(16), nullable=False)  # e.g. "G", "1", "2", "M"
    floor_name = Column(String(80), nullable=True)
    floor_type = Column(String(32), nullable=True)
    status = Column(String(16), default="active", nullable=False, index=True)
    remarks = Column(Text, nullable=True)

    property = relationship("Property")
    units = relationship("Unit", back_populates="floor", lazy="select", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("property_id", "floor_number", name="uq_floor_property_number"),
        Index("ix_floors_property_status", "property_id", "status"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        data["unit_count"] = len(self.units) if self.units is not None else 0
        return data
