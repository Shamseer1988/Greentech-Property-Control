"""Gapless per-month document numbering (PREFIX-YYYYMM-NNNN), race-safe
under concurrent inserts in the same month — ACCOUNTING-RULES rule 4.

Before this, `next_receipt_number()`/`next_voucher_number()` did an
unlocked `LIKE 'RV-YYYYMM-%'` max-scan: two requests reading the same
max in the gap before either commits would both propose the same next
number. Harmless one at a time; guaranteed to collide once the bulk
entry screen posts many receipts/vouchers in one go.

The fix is a `NumberSequence` row locked with `SELECT ... FOR UPDATE`
(Postgres) — a harmless no-op on SQLite, which already serializes
writes at the whole-database level, so the tests' single-threaded
client sees identical, correct behavior either way. The row is seeded
once per (prefix, month), from whatever numbers already exist for that
scheme via the old LIKE-scan — a narrow one-time race, closed by
retrying on the unique-constraint conflict a concurrent seed would
raise.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.sequence import NumberSequence


def next_number(prefix: str, period_key: str, *, legacy_seed: Callable[[], int]) -> str:
    """Allocate and return the next "PREFIX-period_key-NNNN" number."""
    row = (
        NumberSequence.query
        .filter_by(prefix=prefix, period_key=period_key)
        .with_for_update()
        .first()
    )
    if row is not None:
        row.next_value += 1
        db.session.flush()
        return f"{prefix}-{period_key}-{row.next_value:04d}"

    start = legacy_seed() + 1
    row = NumberSequence(prefix=prefix, period_key=period_key, next_value=start)
    db.session.add(row)
    try:
        db.session.flush()
    except IntegrityError:
        # A concurrent request seeded the row first — lock it and take
        # the next value from there instead of the one we proposed.
        db.session.rollback()
        row = (
            NumberSequence.query
            .filter_by(prefix=prefix, period_key=period_key)
            .with_for_update()
            .first()
        )
        row.next_value += 1
        db.session.flush()
    return f"{prefix}-{period_key}-{row.next_value:04d}"
