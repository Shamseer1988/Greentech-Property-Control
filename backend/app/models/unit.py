from sqlalchemy import (
    Column, String, Integer, Boolean, Text, ForeignKey, Index, UniqueConstraint, Numeric,
)
from sqlalchemy.orm import relationship

from .base import BaseModel


# A Unit is the atom of occupancy — the smallest thing GreenTech can let
# to a client, plus the facilities that come with a property. Everything
# the master file calls a "room", "store", "shop", "cafeteria" or
# "flat" is a Unit with a different unit_type.
UNIT_TYPES = {
    "room", "flat_1bhk", "flat_2bhk", "floor", "villa",
    "store", "shop", "cafeteria", "supermarket",
    "kitchen", "bathroom", "play_area", "mess", "other",
}

# Facility units are not let on their own; they are either common to the
# whole property (shared) or attached to one client contract (dedicated).
FACILITY_TYPES = {"kitchen", "bathroom", "play_area", "mess"}

UNIT_STATUSES = {"empty", "occupied", "maintenance", "blocked"}


class Unit(BaseModel):
    """A lettable or facility unit inside a property."""

    __tablename__ = "units"

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    floor_id = Column(Integer, ForeignKey("floors.id", ondelete="CASCADE"), nullable=False, index=True)

    unit_number = Column(String(32), nullable=False)
    unit_name = Column(String(80), nullable=True)
    unit_type = Column(String(16), default="room", nullable=False)
    # Free text on purpose — a room is described by dimensions ("4/4",
    # meaning 4m x 4m), a store/shop by floor area ("450 Sqm"). Different
    # unit types are sized in genuinely different units; a single numeric
    # column would force one convention on both.
    size = Column(String(32), nullable=True)
    # Facility units only: shared (common) vs dedicated (assignable).
    is_shared_facility = Column(Boolean, default=False, nullable=False)
    has_bathroom = Column(Boolean, default=False, nullable=False)
    has_ac = Column(Boolean, default=True, nullable=False)
    occupancy_status = Column(String(20), default="empty", nullable=False, index=True)
    monthly_rent = Column(Numeric(12, 2), nullable=True)
    remarks = Column(Text, nullable=True)

    floor = relationship("Floor", back_populates="units")
    property = relationship("Property")

    __table_args__ = (
        UniqueConstraint("property_id", "floor_id", "unit_number", name="uq_unit_property_floor_number"),
        Index("ix_units_property_status", "property_id", "occupancy_status"),
    )

    # NB: no @property decorator anywhere in this class — the `property`
    # relationship above shadows the builtin inside the class body.
    def is_facility(self) -> bool:
        return self.unit_type in FACILITY_TYPES

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("monthly_rent") is not None:
            data["monthly_rent"] = float(data["monthly_rent"])
        data["is_facility"] = self.is_facility()
        return data
