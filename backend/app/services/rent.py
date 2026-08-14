"""Rent schedule generation.

The whole point: for any month, work out what a contract *actually*
charges — after rent changes, free months, a mid-month start and an
early cancellation. Nothing is stored twice; the answer is always
derived from the contract plus its dated amendments, so a past month
can be regenerated and come out identical.

Conventions, chosen to match how the master workbook was kept by hand:

  * A **rent change** applies to the whole month containing its
    effective date. A cut effective 2026-04-01 makes April cheaper; one
    effective 2026-04-15 does too.
  * **Free months** run from `free_from_month` for N whole months.
  * **Pro-rata** applies only at the two ends of a tenancy: a contract
    starting mid-month pays for the days it occupies, and one cancelled
    mid-month pays to the cancellation date.
  * The **opening balance** (the workbook's "OP Dec-2025" column) is
    posted once as its own charge dated the month before the contract
    starts, so it ages like any other due.
"""
from __future__ import annotations

import calendar
from datetime import date

from ..extensions import db
from ..models import ClientContract, RentCharge
from . import audit


class RentError(ValueError):
    """Caller-visible failure."""


# ----------------------------------------------------------------------
# Month helpers
# ----------------------------------------------------------------------

def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def add_months(anchor: date, months: int) -> date:
    index = anchor.month - 1 + months
    year = anchor.year + index // 12
    month = index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def months_between(first: date, last: date) -> list[date]:
    """Every month-start from `first` to `last`, inclusive."""
    out, cursor = [], month_start(first)
    stop = month_start(last)
    while cursor <= stop:
        out.append(cursor)
        cursor = add_months(cursor, 1)
    return out


# ----------------------------------------------------------------------
# What does this contract charge for this month?
# ----------------------------------------------------------------------

def rent_in_force(contract: ClientContract, period: date) -> float:
    """The monthly rent that applies during `period`'s month.

    Walks the rent_change amendments in effective-date order. The
    contract's own `monthly_rent` holds the *current* figure, so the
    original is recovered from the first amendment's `old_rent`.
    """
    changes = sorted(
        [a for a in (contract.amendments or []) if a.amendment_type == "rent_change"],
        key=lambda a: (a.effective_date, a.sequence),
    )
    if not changes:
        return float(contract.monthly_rent)

    rent = float(changes[0].old_rent if changes[0].old_rent is not None else contract.monthly_rent)
    end = month_end(period)
    for change in changes:
        if change.effective_date <= end:
            rent = float(change.new_rent)
    return rent


def is_free_month(contract: ClientContract, period: date) -> bool:
    start = month_start(period)
    for a in (contract.amendments or []):
        if a.amendment_type != "free_months" or not a.free_from_month or not a.free_months:
            continue
        first = month_start(a.free_from_month)
        if first <= start < add_months(first, int(a.free_months)):
            return True
    return False


def charge_for_month(contract: ClientContract, period: date) -> dict | None:
    """Compute one month's charge, or None if the contract isn't live then.

    Returns ``{amount, is_free_month, proration_note}``.
    """
    period = month_start(period)
    first_day, last_day = period, month_end(period)

    # Outside the tenancy entirely?
    if contract.start_date > last_day:
        return None
    if contract.expiry_date < first_day:
        return None

    # A cancelled contract stops charging after its cancellation date.
    effective_end = contract.expiry_date
    if contract.status == "cancelled" and contract.cancellation_date:
        effective_end = min(effective_end, contract.cancellation_date)
    # A renewed contract hands over to its successor.
    if contract.status == "renewed":
        effective_end = min(effective_end, contract.expiry_date)
    if effective_end < first_day:
        return None

    if is_free_month(contract, period):
        return {"amount": 0.0, "is_free_month": True,
                "proration_note": "Rent-free month"}

    full = rent_in_force(contract, period)
    days_in_month = calendar.monthrange(period.year, period.month)[1]

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

def _upsert_charge(contract: ClientContract, period: date, spec: dict, *, actor) -> tuple[RentCharge, str]:
    """Create or refresh one month's charge. Returns (charge, action)."""
    existing = (
        RentCharge.query
        .filter_by(contract_id=contract.id, period_month=period)
        .first()
    )
    if existing is None:
        charge = RentCharge(
            contract_id=contract.id,
            client_id=contract.client_id,
            property_id=contract.property_id,
            period_month=period,
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

    # Money already applied? Leave it alone — changing a paid charge
    # would rewrite history (ACCOUNTING-RULES rule 2).
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


def ensure_opening_balance(contract: ClientContract, *, actor) -> tuple[RentCharge | None, bool]:
    """Post the carried-forward balance once, dated the month before start.

    Returns ``(charge, created)`` — `created` is False on a re-run so the
    caller doesn't count it again.
    """
    opening = float(contract.opening_balance or 0)
    if opening <= 0:
        return None, False
    period = add_months(month_start(contract.start_date), -1)
    existing = (
        RentCharge.query
        .filter_by(contract_id=contract.id, period_month=period)
        .first()
    )
    if existing is not None:
        return existing, False
    charge = RentCharge(
        contract_id=contract.id,
        client_id=contract.client_id,
        property_id=contract.property_id,
        period_month=period,
        amount=opening,
        is_opening_balance=True,
        proration_note="Balance carried forward",
        created_by=actor.id,
        updated_by=actor.id,
    )
    charge.recompute_status()
    db.session.add(charge)
    db.session.flush()
    return charge, True


def generate_for_contract(contract: ClientContract, *, upto: date | None = None,
                          actor) -> dict:
    """Generate every month's charge for one contract up to `upto`.

    Idempotent: re-running produces the same figures and never touches a
    month that already has money against it.
    """
    upto = month_start(upto or date.today())
    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped_paid": 0}

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
    return counts


def generate_all(*, upto: date | None = None, actor, property_id: int | None = None) -> dict:
    """Generate charges for every contract that has run this far."""
    upto = month_start(upto or date.today())
    query = ClientContract.query.filter(ClientContract.status.in_(
        ("active", "cancelled", "expired", "renewed")))
    if property_id:
        query = query.filter(ClientContract.property_id == property_id)

    totals = {"created": 0, "updated": 0, "unchanged": 0, "skipped_paid": 0, "contracts": 0}
    for contract in query.all():
        counts = generate_for_contract(contract, upto=upto, actor=actor)
        for k, v in counts.items():
            totals[k] += v
        totals["contracts"] += 1

    if totals["created"] or totals["updated"]:
        audit.record(user=actor, action="generate", module="rent",
                     entity_type="rent_charge", entity_id=0,
                     new_value=totals,
                     remarks=f"rent generated up to {upto.isoformat()}")
    return totals


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

def open_charges_for_client(client_id: int, *, upto: date | None = None) -> list[RentCharge]:
    """A client's unpaid charges, oldest first — the allocation order."""
    query = (
        RentCharge.query
        .filter(RentCharge.client_id == client_id)
        .filter(RentCharge.status.in_(("open", "part_paid")))
    )
    if upto:
        query = query.filter(RentCharge.period_month <= month_start(upto))
    return query.order_by(RentCharge.period_month.asc(), RentCharge.id.asc()).all()


def outstanding_for_client(client_id: int, *, upto: date | None = None) -> float:
    return round(sum(c.outstanding() for c in open_charges_for_client(client_id, upto=upto)), 2)


# Cash tenancies are collected door-to-door once a month rather than
# paid in on their own; the operator's own process boxes that collection
# run into the 5th-15th of the month. window_open() is informational —
# it does not gate anything, since a run can slip a day either way.
CASH_WINDOW_START_DAY = 5
CASH_WINDOW_END_DAY = 15


def cash_window_open(on: date | None = None) -> bool:
    on = on or date.today()
    return CASH_WINDOW_START_DAY <= on.day <= CASH_WINDOW_END_DAY


def cash_due_booking(*, period: date | None = None) -> dict:
    """This month's rent charges for cash-mode contracts, property-wise.

    One row per open/part-paid charge on a contract whose payment_mode
    is 'cash' — the list a collector works down between the 5th and the
    15th, marking each as received (posting a receipt) as cash comes in.
    """
    from ..models import Client, Property

    period = month_start(period or date.today())
    rows = (
        RentCharge.query
        .join(ClientContract, RentCharge.contract_id == ClientContract.id)
        .join(Client, RentCharge.client_id == Client.id)
        .join(Property, RentCharge.property_id == Property.id)
        .filter(ClientContract.payment_mode == "cash")
        .filter(RentCharge.period_month == period)
        .filter(RentCharge.status.in_(("open", "part_paid")))
        .order_by(Property.code, Client.name)
        .all()
    )

    by_property: dict[int, dict] = {}
    for charge in rows:
        prop = charge.contract.property
        entry = by_property.setdefault(prop.id, {
            "property_id": prop.id, "property_code": prop.code,
            "property_name": prop.name, "charges": [], "total_due": 0.0,
        })
        entry["charges"].append({
            **charge.to_dict(),
            "contract_id": charge.contract_id,
        })
        entry["total_due"] = round(entry["total_due"] + charge.outstanding(), 2)

    properties = sorted(by_property.values(), key=lambda p: p["property_code"])
    return {
        "period": period.isoformat(),
        "window_open": cash_window_open(),
        "window": {"start_day": CASH_WINDOW_START_DAY, "end_day": CASH_WINDOW_END_DAY},
        "properties": properties,
        "total_due": round(sum(p["total_due"] for p in properties), 2),
        "count": len(rows),
    }
