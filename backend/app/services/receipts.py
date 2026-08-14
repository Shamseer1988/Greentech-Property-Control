"""Receipts — money in, and how it settles the dues.

Allocation is oldest-first (docs/ACCOUNTING-RULES.md rule 8). The
operator may override by naming charges explicitly; the override is
flagged on the allocation row so a reviewer can see it was deliberate.

Receipts are never deleted. Voiding one reverses its allocations, so
the dues it paid reopen, and the receipt stays on the ledger with its
number, reason and who voided it (rule 1).
"""
from __future__ import annotations

from datetime import date, datetime

from ..extensions import db
from ..models import Client, Receipt, ReceiptAllocation, RentCharge
from ..models.rent import RECEIPT_MODES
from . import audit, numbering
from .rent import open_charges_for_client, month_start, month_end


class ReceiptError(ValueError):
    """Caller-visible failure."""


def _legacy_max_receipt_number(month_key: str) -> int:
    like = f"RV-{month_key}-%"
    last = (
        db.session.query(Receipt.receipt_number)
        .filter(Receipt.receipt_number.like(like))
        .order_by(Receipt.receipt_number.desc())
        .limit(1)
        .scalar()
    )
    if not last:
        return 0
    try:
        return int(last.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def next_receipt_number() -> str:
    """Race-safe: locked via `services.numbering` so batch-posting many
    receipts in one transaction (the bulk entry screen) never collides."""
    month_key = datetime.utcnow().strftime("%Y%m")
    return numbering.next_number("RV", month_key,
                                 legacy_seed=lambda: _legacy_max_receipt_number(month_key))


def _parse_date(value, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        raise ReceiptError(f"{field} must be YYYY-MM-DD")


def _apply(receipt: Receipt, charge: RentCharge, amount: float, *, manual: bool, actor) -> float:
    """Put `amount` (capped at what's due) against `charge`."""
    due = charge.outstanding()
    applied = round(min(due, amount), 2)
    if applied <= 0:
        return 0.0
    db.session.add(ReceiptAllocation(
        receipt_id=receipt.id, charge_id=charge.id, amount=applied,
        is_manual=manual, created_by=actor.id, updated_by=actor.id,
    ))
    charge.allocated = round(charge._allocated() + applied, 2)
    charge.recompute_status()
    charge.updated_by = actor.id
    return applied


def post_receipt(*, client_id: int, amount, receipt_date, mode: str,
                 reference: str | None = None, remarks: str | None = None,
                 allocations: list[dict] | None = None,
                 cheque_id: int | None = None, actor) -> Receipt:
    """Record money received and settle dues with it.

    `allocations` is optional: ``[{charge_id, amount}]`` to direct the
    money at specific months. Anything left over — or everything, if no
    allocations are given — flows to the oldest open charges, and any
    remainder stays on the receipt as an advance.
    """
    if mode not in RECEIPT_MODES:
        raise ReceiptError(f"mode must be one of {sorted(RECEIPT_MODES)}")
    client = Client.query.get(client_id)
    if client is None:
        raise ReceiptError("client_id not found")
    try:
        total = round(float(amount), 2)
    except (TypeError, ValueError):
        raise ReceiptError("amount must be a number")
    if total <= 0:
        raise ReceiptError("amount must be greater than zero")

    when = _parse_date(receipt_date, "receipt_date")

    receipt = Receipt(
        receipt_number=next_receipt_number(),
        client_id=client.id,
        receipt_date=when,
        amount=total,
        mode=mode,
        reference=reference,
        cheque_id=cheque_id,
        status="posted",
        remarks=remarks,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.session.add(receipt)
    db.session.flush()

    remaining = total

    # 1. Explicit allocations first — the operator's instruction wins.
    for row in (allocations or []):
        if remaining <= 0:
            break
        charge = RentCharge.query.get(row.get("charge_id"))
        if charge is None:
            raise ReceiptError(f"charge_id {row.get('charge_id')} not found")
        if charge.client_id != client.id:
            raise ReceiptError(
                f"Charge {charge.id} belongs to another client")
        want = row.get("amount")
        want = remaining if want in (None, "") else round(float(want), 2)
        applied = _apply(receipt, charge, min(want, remaining), manual=True, actor=actor)
        remaining = round(remaining - applied, 2)

    # 2. Whatever is left settles the oldest dues.
    if remaining > 0:
        already = {a.charge_id for a in (receipt.allocations or [])}
        for charge in open_charges_for_client(client.id):
            if remaining <= 0:
                break
            if charge.id in already:
                continue
            applied = _apply(receipt, charge, remaining, manual=False, actor=actor)
            remaining = round(remaining - applied, 2)

    db.session.flush()
    audit.record(user=actor, action="post", module="receipt",
                 entity_type="receipt", entity_id=receipt.id,
                 new_value=receipt.to_dict(),
                 remarks=f"{receipt.allocated_total()} allocated, {remaining} on account")
    return receipt


def void_receipt(receipt: Receipt, *, reason: str, actor) -> Receipt:
    """Reverse a receipt. The row stays; the dues it paid reopen."""
    if receipt.status == "voided":
        raise ReceiptError(f"Receipt {receipt.receipt_number} is already voided")
    if not (reason or "").strip():
        raise ReceiptError("reason is required to void a receipt")

    for allocation in list(receipt.allocations or []):
        charge = allocation.charge
        if charge is not None:
            charge.allocated = round(charge._allocated() - float(allocation.amount), 2)
            if charge.allocated < 0:
                charge.allocated = 0
            charge.recompute_status()
            charge.updated_by = actor.id
        db.session.delete(allocation)

    receipt.status = "voided"
    receipt.void_reason = reason
    receipt.voided_at = date.today()
    receipt.voided_by = actor.id
    receipt.updated_by = actor.id
    db.session.flush()

    audit.record(user=actor, action="void", module="receipt",
                 entity_type="receipt", entity_id=receipt.id,
                 old_value={"status": "posted"},
                 new_value={"status": "voided", "reason": reason},
                 remarks=f"voided {receipt.receipt_number}")
    return receipt


def collections_summary(*, month: date | None = None) -> dict:
    """Charged vs collected for a month — the dashboard's headline."""
    period = month_start(month or date.today())
    charged = (
        db.session.query(db.func.coalesce(db.func.sum(RentCharge.amount), 0))
        .filter(RentCharge.period_month == period)
        .scalar() or 0
    )
    allocated = (
        db.session.query(db.func.coalesce(db.func.sum(RentCharge.allocated), 0))
        .filter(RentCharge.period_month == period)
        .scalar() or 0
    )
    # Cash actually banked during the month, whichever month it settled.
    received = (
        db.session.query(db.func.coalesce(db.func.sum(Receipt.amount), 0))
        .filter(Receipt.status == "posted")
        .filter(Receipt.receipt_date >= period)
        .filter(Receipt.receipt_date <= month_end(period))
        .scalar() or 0
    )

    charged, allocated, received = float(charged), float(allocated), float(received)
    return {
        "month": period.isoformat(),
        "charged": round(charged, 2),
        "collected": round(allocated, 2),
        "outstanding": round(charged - allocated, 2),
        "received_in_month": round(received, 2),
        "collection_percent": round(allocated * 100 / charged, 1) if charged else 0.0,
    }
