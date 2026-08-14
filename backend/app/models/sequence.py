"""Backs race-safe gapless document numbering — see `services/numbering.py`."""
from sqlalchemy import Column, String, Integer, UniqueConstraint

from .base import BaseModel


class NumberSequence(BaseModel):
    """One row per (prefix, period_key) — e.g. ("RV", "202608") — whose
    `next_value` is the last number issued. Locked on read
    (`with_for_update()`) so concurrent allocations within the same
    month never collide."""

    __tablename__ = "number_sequences"

    prefix = Column(String(16), nullable=False, index=True)
    period_key = Column(String(8), nullable=False, index=True)
    next_value = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("prefix", "period_key", name="uq_number_sequences_prefix_period"),
    )
