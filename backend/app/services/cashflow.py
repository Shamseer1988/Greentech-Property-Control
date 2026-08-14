"""Portfolio-wide cash-flow forecast — 30/60/90 day buckets of expected
incoming and outgoing cash, built from what's already on the books.

Reuses the same "open charges as of a cutoff" filter shape already used
per-entity in services/rent.py::open_charges_for_client(),
services/landlord_rent.py::open_charges_for(), and
services/cheques.py::due_for_deposit() — this is the same query, just
without the per-entity scope.

One thing those per-entity helpers don't have to worry about that a
portfolio-wide forecast does: double counting. A cheque-mode client's
RentCharge and the Cheque instrument that will settle it represent the
same expected cash — the charge doesn't clear until the cheque does
(receipts are posted from cheque deposit/clear, not from the charge
existing). So incoming cash for cheque-mode contracts comes from their
Cheques; RentCharge is only used directly for cash/online-mode
contracts, where no cheque instrument exists to double-count against.
Security-deposit cheques are excluded from "expected in" — they're a
refundable hold, not rent income.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..models import ClientContract, LandlordCharge, RentCharge, Cheque
from .rent import month_start

BUCKET_DAYS = (30, 60, 90)


def _rent_due_excluding_cheque_mode(cutoff: date) -> float:
    rows = (
        RentCharge.query
        .join(ClientContract, RentCharge.contract_id == ClientContract.id)
        .filter(RentCharge.status.in_(("open", "part_paid")))
        .filter(RentCharge.period_month <= month_start(cutoff))
        .filter(ClientContract.payment_mode != "cheque")
        .all()
    )
    return sum(c.outstanding() for c in rows)


def _cheques_due(as_of: date, cutoff: date) -> float:
    rows = (
        Cheque.query
        .filter(Cheque.status.in_(("received", "deposited")))
        .filter(Cheque.is_security.is_(False))
        .filter(Cheque.cheque_date >= as_of)
        .filter(Cheque.cheque_date <= cutoff)
        .all()
    )
    return sum(float(c.amount) for c in rows)


def _landlord_due(cutoff: date) -> float:
    rows = (
        LandlordCharge.query
        .filter(LandlordCharge.status.in_(("open", "part_paid")))
        .filter(LandlordCharge.period_month <= month_start(cutoff))
        .all()
    )
    return sum(c.outstanding() for c in rows)


def forecast(as_of: date | None = None) -> dict:
    """{"as_of": iso date, "buckets": {"30": {...}, "60": {...}, "90": {...}}}
    each bucket = {"expected_in", "expected_out", "net"}, all cumulative
    from `as_of` through that many days out — not per-bucket deltas, so
    the 90-day figure already includes the 30- and 60-day windows."""
    today = as_of or date.today()
    buckets: dict[str, dict] = {}
    for days in BUCKET_DAYS:
        cutoff = today + timedelta(days=days)
        expected_in = round(
            _rent_due_excluding_cheque_mode(cutoff) + _cheques_due(today, cutoff), 2)
        expected_out = round(_landlord_due(cutoff), 2)
        buckets[str(days)] = {
            "expected_in": expected_in,
            "expected_out": expected_out,
            "net": round(expected_in - expected_out, 2),
        }
    return {"as_of": today.isoformat(), "buckets": buckets}
