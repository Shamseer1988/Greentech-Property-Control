"""Landlord rent schedule generation — the dues side of what GreenTech
owes each landlord, mirroring `services/rent.py` on the client side so
the same month-by-month, amendment-aware logic governs both directions
of the ledger.

A contract with no rent set (`monthly_rent` is NULL and no `rent_change`
amendment has ever given it one) is not an error — some live agreements
genuinely have no confirmed figure yet. Such contracts are skipped and
counted in `skipped_no_rent`, never raised.
"""
from __future__ import annotations

from datetime import date

from ..extensions import db
from ..models import LandlordContract, LandlordCharge
from .rent import month_start, month_end, add_months, months_between


class LandlordRentError(ValueError):
    """Caller-visible failure."""


# ----------------------------------------------------------------------
# What does this contract charge for this month?
# ----------------------------------------------------------------------

def rent_in_force(contract: LandlordContract, period: date) -> float | None:
    """The monthly rent that applies during `period`'s month, or None
    if the contract has never had a rent figure at all."""
    changes = sorted(
        [a for a in (contract.amendments or []) if a.amendment_type == "rent_change"],
        key=lambda a: (a.effective_date, a.sequence),
    )
    if not changes:
        return float(contract.monthly_rent) if contract.monthly_rent is not None else None

    first_old = changes[0].old_rent
    rent = float(first_old) if first_old is not None else (
        float(contract.monthly_rent) if contract.monthly_rent is not None else None
    )
    end = month_end(period)
    for change in changes:
        if change.effective_date <= end:
            rent = float(change.new_rent)
    return rent


def is_free_month(contract: LandlordContract, period: date) -> bool:
    start = month_start(period)
    for a in (contract.amendments or []):
        if a.amendment_type != "free_months" or not a.free_from_month or not a.free_months:
            continue
        first = month_start(a.free_from_month)
        if first <= start < add_months(first, int(a.free_months)):
            return True
    return False


def has_any_rent(contract: LandlordContract) -> bool:
    if contract.monthly_rent is not None:
        return True
    return any(a.amendment_type == "rent_change" for a in (contract.amendments or []))


def charge_for_month(contract: LandlordContract, period: date) -> dict | None:
    """Compute one month's charge, or None if the contract isn't live
    then (or has no rent figure at all).

    Returns ``{amount, is_free_month, proration_note}``.
    """
    period = month_start(period)
    first_day, last_day = period, month_end(period)

    if contract.start_date > last_day:
        return None
    if contract.expiry_date < first_day:
        return None

    effective_end = contract.expiry_date
    if contract.status == "cancelled" and contract.cancellation_date:
        effective_end = min(effective_end, contract.cancellation_date)
    if contract.status == "renewed":
        effective_end = min(effective_end, contract.expiry_date)
    if effective_end < first_day:
        return None

    if is_free_month(contract, period):
        return {"amount": 0.0, "is_free_month": True,
                "proration_note": "Rent-free month (landlord-granted)"}

    full = rent_in_force(contract, period)
    if full is None:
        return None

    days_in_month = (last_day - first_day).days + 1

    occupied_from = max(contract.start_date, first_day)
    occupied_to = min(effective_end, last_day)
    days_occupied = (occupied_to - occupied_from).days + 1

    if days_occupied >= days_in_month:
        return {"amount": round(full, 2), "is_free_month": False, "proration_note": None}

    amount = round(full * days_occupied / days_in_month, 2)
    note = f"{days_occupied}/{days_in_month} days ({occupied_from.isoformat()} → {occupied_to.isoformat()})"
    return {"amount": amount, "is_free_month": False, "proration_note": note}


# ----------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------

def _upsert_charge(contract: LandlordContract, period: date, spec: dict, *, actor) -> tuple[LandlordCharge, str]:
    """Create or refresh one month's charge (seq=1). Returns (charge, action)."""
    existing = (
        LandlordCharge.query
        .filter_by(contract_id=contract.id, period_month=period, seq=1)
        .first()
    )
    if existing is None:
        charge = LandlordCharge(
            contract_id=contract.id,
            landlord_id=contract.landlord_id,
            property_id=contract.property_id,
            period_month=period,
            seq=1,
            amount=spec["amount"],
            is_free_month=spec["is_free_month"],
            proration_note=spec["proration_note"],
            created_by=actor.id,
            updated_by=actor.id,
        )
        charge.recompute_status()
        db.session.add(charge)
        db.session.flush()
        return charge, "created"

    if existing._allocated() > 0:
        return existing, "skipped_paid"

    if (float(existing.amount) == float(spec["amount"])
            and existing.is_free_month == spec["is_free_month"]):
        return existing, "unchanged"

    existing.amount = spec["amount"]
    existing.is_free_month = spec["is_free_month"]
    existing.proration_note = spec["proration_note"]
    existing.updated_by = actor.id
    existing.recompute_status()
    db.session.flush()
    return existing, "updated"


def ensure_opening_balance(contract: LandlordContract, *, actor) -> tuple[LandlordCharge | None, bool]:
    opening = float(contract.opening_balance or 0)
    if opening <= 0:
        return None, False
    period = add_months(month_start(contract.start_date), -1)
    existing = (
        LandlordCharge.query
        .filter_by(contract_id=contract.id, period_month=period, seq=1)
        .first()
    )
    if existing is not None:
        return existing, False
    charge = LandlordCharge(
        contract_id=contract.id,
        landlord_id=contract.landlord_id,
        property_id=contract.property_id,
        period_month=period,
        seq=1,
        amount=opening,
        proration_note="Balance carried forward",
        created_by=actor.id,
        updated_by=actor.id,
    )
    charge.recompute_status()
    db.session.add(charge)
    db.session.flush()
    return charge, True


def generate_for_contract(contract: LandlordContract, *, upto: date | None = None,
                          actor) -> dict:
    """Generate every month's charge for one landlord contract up to
    `upto`. Idempotent, and never touches a month that already has
    money against it."""
    upto = month_start(upto or date.today())
    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped_paid": 0}

    if not has_any_rent(contract):
        return {**counts, "skipped_no_rent": True}

    _, opening_created = ensure_opening_balance(contract, actor=actor)
    if opening_created:
        counts["created"] += 1

    last = min(month_start(contract.expiry_date), upto)
    if contract.status == "cancelled" and contract.cancellation_date:
        last = min(last, month_start(contract.cancellation_date))

    for period in months_between(contract.start_date, last):
        spec = charge_for_month(contract, period)
        if spec is None:
            continue
        _, action = _upsert_charge(contract, period, spec, actor=actor)
        counts[action] += 1
    return {**counts, "skipped_no_rent": False}


def generate_all(*, upto: date | None = None, actor, property_id: int | None = None) -> dict:
    """Generate charges for every landlord contract that has run this far."""
    from . import audit

    upto = month_start(upto or date.today())
    query = LandlordContract.query.filter(LandlordContract.status.in_(
        ("active", "cancelled", "expired", "renewed")))
    if property_id:
        query = query.filter(LandlordContract.property_id == property_id)

    totals = {"created": 0, "updated": 0, "unchanged": 0, "skipped_paid": 0,
              "skipped_no_rent": 0, "contracts": 0}
    for contract in query.all():
        counts = generate_for_contract(contract, upto=upto, actor=actor)
        if counts.pop("skipped_no_rent", False):
            totals["skipped_no_rent"] += 1
        else:
            for k, v in counts.items():
                totals[k] += v
        totals["contracts"] += 1

    if totals["created"] or totals["updated"]:
        audit.record(user=actor, action="generate", module="landlord_rent",
                     entity_type="landlord_charge", entity_id=0,
                     new_value=totals,
                     remarks=f"landlord dues generated up to {upto.isoformat()}")
    return totals


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

def open_charges_for(landlord_id: int, property_id: int, *, upto: date | None = None) -> list[LandlordCharge]:
    """A landlord's unpaid charges for one property, oldest first — the
    allocation scope is `(landlord_id, property_id)`, never landlord
    alone, so one building's cheque can never settle another's arrear."""
    query = (
        LandlordCharge.query
        .filter(LandlordCharge.landlord_id == landlord_id)
        .filter(LandlordCharge.property_id == property_id)
        .filter(LandlordCharge.status.in_(("open", "part_paid")))
    )
    if upto:
        query = query.filter(LandlordCharge.period_month <= month_start(upto))
    return query.order_by(LandlordCharge.period_month.asc(), LandlordCharge.id.asc()).all()


def outstanding_for(landlord_id: int, property_id: int, *, upto: date | None = None) -> float:
    return round(sum(c.outstanding() for c in open_charges_for(landlord_id, property_id, upto=upto)), 2)
