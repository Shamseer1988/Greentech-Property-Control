"""Landlord-contract lifecycle — the `property_agreements`
(`LandlordContract`) side, mirroring `services/contracts.py` on the
client side so the two amendment histories read the same way.

A unit rented IN from a landlord and a unit rented OUT to a client are
independent relationships that can both be true of the same unit at
once, so nothing here ever touches `units.occupancy_status` or the
client-side exclusivity guard (`services/contracts.units_held_on`) —
see `models/landlord_contract.py`'s module docstring.

Contract *creation* stays on the existing path
(`POST /properties/<id>/agreements`, `routes/properties.py`) — that
already does the confirmed "archive old, insert new" pattern. Units are
optional there (whole-property is the common case, and every migrated
contract has none), and get attached afterwards through `add_units`
below, exactly like the client side's separate creation vs. amendment
steps.
"""
from __future__ import annotations

from datetime import date, datetime

from ..extensions import db
from ..models import (
    LandlordContract, LandlordContractAmendment, LandlordContractUnit, Unit,
)
from ..models.contract import PAYMENT_MODES
from ..models.landlord_contract import LANDLORD_AMENDMENT_TYPES
from . import audit


class LandlordContractError(ValueError):
    """Caller-visible validation failure — surfaced as a 400/409."""


class LandlordContractWarning(Exception):
    """Not an error — a confirmation prompt. Raised when an action is
    legal but worth a second look (releasing a unit a client contract
    still holds). The route returns these as 409 with a `warnings`
    list; retrying with `acknowledge_warnings=True` proceeds."""

    def __init__(self, warnings: list[dict]):
        self.warnings = warnings
        super().__init__("Confirmation required")


# ----------------------------------------------------------------------
# Numbering (gapless per month — ACCOUNTING-RULES rule 4). New contracts
# only: the 14 migrated rows kept their backfilled `LCON-000007`-style
# numbers, which don't collide with this format and are clearly legacy.
# ----------------------------------------------------------------------

def _next_number(model, column, prefix: str) -> str:
    month_key = datetime.utcnow().strftime("%Y%m")
    like = f"{prefix}-{month_key}-%"
    last = (
        db.session.query(column)
        .filter(column.like(like))
        .order_by(column.desc())
        .limit(1)
        .scalar()
    )
    seq = 1
    if last:
        try:
            seq = int(last.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    return f"{prefix}-{month_key}-{seq:04d}"


def next_landlord_contract_number() -> str:
    return _next_number(LandlordContract, LandlordContract.contract_number, "LCON")


def next_amendment_number() -> str:
    return _next_number(LandlordContractAmendment, LandlordContractAmendment.amendment_number, "LAMD")


# ----------------------------------------------------------------------
# Occupancy — read-only lookups. No write path here ever touches
# units.occupancy_status; that projection is client-occupancy only.
# ----------------------------------------------------------------------

def units_leased_in_on(unit_ids: list[int], on: date,
                       exclude_contract_id: int | None = None) -> dict[int, LandlordContract]:
    """Which of `unit_ids` are already sourced from a landlord on `on`,
    and under which contract — the double-sourcing guard. A unit can't
    be rented in from two landlords at once (it CAN simultaneously be
    rented out to a client — that's `services.contracts.units_held_on`,
    a different table, deliberately not consulted here)."""
    if not unit_ids:
        return {}
    q = (
        db.session.query(LandlordContractUnit, LandlordContract)
        .join(LandlordContract, LandlordContractUnit.contract_id == LandlordContract.id)
        .filter(LandlordContractUnit.unit_id.in_(unit_ids))
        .filter(LandlordContractUnit.from_date <= on)
        .filter(db.or_(LandlordContractUnit.to_date.is_(None), LandlordContractUnit.to_date >= on))
        .filter(LandlordContract.status == "active")
    )
    if exclude_contract_id:
        q = q.filter(LandlordContract.id != exclude_contract_id)
    return {lcu.unit_id: contract for lcu, contract in q.all()}


# ----------------------------------------------------------------------
# Amendments
# ----------------------------------------------------------------------

def _parse_date(value, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        raise LandlordContractError(f"{field} must be YYYY-MM-DD")


def _add_amendment(contract: LandlordContract, *, amendment_type: str,
                   effective_date: date, actor, **fields) -> LandlordContractAmendment:
    if amendment_type not in LANDLORD_AMENDMENT_TYPES:
        raise LandlordContractError(f"amendment_type must be one of {sorted(LANDLORD_AMENDMENT_TYPES)}")
    sequence = len(contract.amendments or []) + 1
    amendment = LandlordContractAmendment(
        contract_id=contract.id,
        amendment_number=next_amendment_number(),
        sequence=sequence,
        amendment_type=amendment_type,
        effective_date=effective_date,
        created_by=actor.id,
        updated_by=actor.id,
        **fields,
    )
    db.session.add(amendment)
    db.session.flush()
    return amendment


def require_active(contract: LandlordContract) -> None:
    if contract.status != "active":
        raise LandlordContractError(
            f"Contract is {contract.status}; only an active contract can be amended")


def change_rent(contract: LandlordContract, *, new_rent, effective_date,
                reason: str | None = None, remarks: str | None = None,
                actor) -> LandlordContractAmendment:
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    try:
        value = float(new_rent)
    except (TypeError, ValueError):
        raise LandlordContractError("new_rent must be a number")
    if value < 0:
        raise LandlordContractError("new_rent cannot be negative")
    old = float(contract.monthly_rent) if contract.monthly_rent is not None else None
    if old == value:
        raise LandlordContractError("new_rent is the same as the current rent")

    amendment = _add_amendment(
        contract, amendment_type="rent_change", effective_date=when, actor=actor,
        old_rent=old, new_rent=value, reason=reason, remarks=remarks,
    )
    contract.monthly_rent = value
    contract.updated_by = actor.id
    audit.record(user=actor, action="amend", module="landlord_contract",
                 entity_type="property_agreement", entity_id=contract.id,
                 old_value={"monthly_rent": old}, new_value={"monthly_rent": value},
                 remarks=f"rent_change {amendment.amendment_number}")
    return amendment


def grant_free_months(contract: LandlordContract, *, months: int, from_month,
                      reason: str | None = None, remarks: str | None = None,
                      actor) -> LandlordContractAmendment:
    """A grace period the LANDLORD granted us — months we don't pay
    them. Mirrors the client side's `free_months`, opposite direction."""
    require_active(contract)
    try:
        count = int(months)
    except (TypeError, ValueError):
        raise LandlordContractError("months must be a whole number")
    if count < 1:
        raise LandlordContractError("months must be at least 1")
    start = _parse_date(from_month, "from_month").replace(day=1)

    amendment = _add_amendment(
        contract, amendment_type="free_months", effective_date=start, actor=actor,
        free_months=count, free_from_month=start, reason=reason, remarks=remarks,
    )
    audit.record(user=actor, action="amend", module="landlord_contract",
                 entity_type="property_agreement", entity_id=contract.id,
                 new_value={"free_months": count, "from_month": start.isoformat()},
                 remarks=f"free_months {amendment.amendment_number}")
    return amendment


def add_units(contract: LandlordContract, *, unit_ids: list[int], effective_date,
              unit_rent=None, reason: str | None = None, actor) -> LandlordContractAmendment:
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    if not unit_ids:
        raise LandlordContractError("unit_ids is required")

    already = {a.unit_id for a in contract.active_allocations(when)}
    wanted = [uid for uid in dict.fromkeys(unit_ids) if uid not in already]
    if not wanted:
        raise LandlordContractError("Those units are already on this contract")

    units = Unit.query.filter(Unit.id.in_(wanted)).all()
    if len(units) != len(wanted):
        raise LandlordContractError("One or more unit_ids not found")
    wrong = [u.unit_number for u in units if u.property_id != contract.property_id]
    if wrong:
        raise LandlordContractError(
            f"Units {', '.join(sorted(wrong))} do not belong to this contract's property")

    clashes = units_leased_in_on(wanted, when, exclude_contract_id=contract.id)
    if clashes:
        by_id = {u.id: u.unit_number for u in units}
        detail = ", ".join(f"{by_id[uid]} (already leased under {c.contract_number})"
                           for uid, c in sorted(clashes.items()))
        raise LandlordContractError(f"Already sourced from another landlord on {when.isoformat()}: {detail}")

    unit_rent_value = float(unit_rent) if unit_rent not in (None, "") else None
    for unit in units:
        db.session.add(LandlordContractUnit(
            contract_id=contract.id, unit_id=unit.id, from_date=when,
            unit_rent=unit_rent_value, created_by=actor.id, updated_by=actor.id,
        ))
    db.session.flush()

    amendment = _add_amendment(
        contract, amendment_type="units_added", effective_date=when, actor=actor,
        unit_ids=",".join(str(u.id) for u in units), reason=reason,
    )
    contract.updated_by = actor.id
    audit.record(user=actor, action="amend", module="landlord_contract",
                 entity_type="property_agreement", entity_id=contract.id,
                 new_value={"units_added": [u.unit_number for u in units]},
                 remarks=f"units_added {amendment.amendment_number}")
    return amendment


def remove_units(contract: LandlordContract, *, unit_ids: list[int], effective_date,
                 reason: str | None = None, acknowledge_warnings: bool = False,
                 actor) -> LandlordContractAmendment:
    """Hand units back to the landlord. Unlike the client side, releasing
    every unit is legal — a landlord contract can hold zero explicitly
    tracked units from the start (whole-property is the common case),
    so there's no "cancel instead" floor to hit.

    If a client contract still holds a unit being released, that's not
    blocked — it's a real state (the tenant may be mid-move) — but it
    raises `LandlordContractWarning` unless `acknowledge_warnings=True`,
    naming the client contract so it's never silent.
    """
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    if not unit_ids:
        raise LandlordContractError("unit_ids is required")

    wanted = set(unit_ids)
    open_allocations = {a.unit_id: a for a in contract.active_allocations(when)}
    missing = wanted - set(open_allocations)
    if missing:
        raise LandlordContractError(
            f"Units {sorted(missing)} are not held by this contract on {when.isoformat()}")

    if not acknowledge_warnings:
        from . import contracts as client_contract_service
        held_by_clients = client_contract_service.units_held_on(sorted(wanted), when)
        if held_by_clients:
            raise LandlordContractWarning([
                {
                    "unit_id": uid,
                    "unit_number": open_allocations[uid].unit.unit_number if open_allocations[uid].unit else str(uid),
                    "contract_number": c.contract_number,
                    "client": c.client.name if c.client else None,
                }
                for uid, c in sorted(held_by_clients.items())
            ])

    released = []
    for uid in wanted:
        allocation = open_allocations[uid]
        allocation.to_date = when
        allocation.release_reason = reason
        allocation.updated_by = actor.id
        released.append(allocation.unit.unit_number if allocation.unit else str(uid))
    db.session.flush()

    amendment = _add_amendment(
        contract, amendment_type="units_removed", effective_date=when, actor=actor,
        unit_ids=",".join(str(u) for u in sorted(wanted)), reason=reason,
    )
    contract.updated_by = actor.id
    audit.record(user=actor, action="amend", module="landlord_contract",
                 entity_type="property_agreement", entity_id=contract.id,
                 old_value={"units_held": len(open_allocations)},
                 new_value={"units_released": sorted(released)},
                 remarks=f"units_removed {amendment.amendment_number}")
    return amendment


def change_deposit(contract: LandlordContract, *, new_deposit, effective_date,
                   reason: str | None = None, remarks: str | None = None,
                   actor) -> LandlordContractAmendment:
    """A security-deposit top-up (or refund) on renewal or renegotiation
    — the landlord-side amendment type with no client-side counterpart."""
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    try:
        value = float(new_deposit)
    except (TypeError, ValueError):
        raise LandlordContractError("new_deposit must be a number")
    if value < 0:
        raise LandlordContractError("new_deposit cannot be negative")
    old = float(contract.security_deposit) if contract.security_deposit is not None else None
    if old == value:
        raise LandlordContractError("new_deposit is the same as the current deposit")

    amendment = _add_amendment(
        contract, amendment_type="deposit_change", effective_date=when, actor=actor,
        old_security_deposit=old, new_security_deposit=value, reason=reason, remarks=remarks,
    )
    contract.security_deposit = value
    contract.updated_by = actor.id
    audit.record(user=actor, action="amend", module="landlord_contract",
                 entity_type="property_agreement", entity_id=contract.id,
                 old_value={"security_deposit": old}, new_value={"security_deposit": value},
                 remarks=f"deposit_change {amendment.amendment_number}")
    return amendment


def cancel_contract(contract: LandlordContract, *, effective_date, reason: str,
                    remarks: str | None = None, actor) -> LandlordContractAmendment:
    """End a landlord contract early. Releases every unit as of the
    effective date — mirrors the client side's cancel exactly."""
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    if not (reason or "").strip():
        raise LandlordContractError("reason is required to cancel a contract")

    open_allocations = contract.active_allocations(when)
    touched = []
    for allocation in open_allocations:
        allocation.to_date = when
        allocation.release_reason = reason
        allocation.updated_by = actor.id
        touched.append(allocation.unit_id)

    contract.status = "cancelled"
    contract.cancellation_date = when
    contract.cancellation_reason = reason
    contract.renewal_status = "cancelled"
    contract.updated_by = actor.id
    db.session.flush()

    amendment = _add_amendment(
        contract, amendment_type="cancellation", effective_date=when, actor=actor,
        unit_ids=",".join(str(u) for u in touched), reason=reason, remarks=remarks,
    )
    audit.record(user=actor, action="cancel", module="landlord_contract",
                 entity_type="property_agreement", entity_id=contract.id,
                 old_value={"status": "active"},
                 new_value={"status": "cancelled", "effective_date": when.isoformat(), "reason": reason},
                 remarks=f"cancellation {amendment.amendment_number}")
    return amendment


def correct_dates(contract: LandlordContract, *, new_start_date=None, new_expiry_date=None,
                  reason: str, remarks: str | None = None, actor) -> LandlordContractAmendment:
    """Fix a data-entry mistake in the contract's start or expiry date —
    mirrors the client side's `correct_dates`. Same contract number, no
    unit changes; for a genuine new term, renew instead (`renewals.py`)."""
    if contract.status not in ("active", "expired"):
        raise LandlordContractError(
            f"Contract is {contract.status}; only an active or expired contract's dates can be corrected")
    if not (reason or "").strip():
        raise LandlordContractError("reason is required to correct contract dates")

    old_start = contract.start_date
    old_expiry = contract.expiry_date
    start = _parse_date(new_start_date, "new_start_date") if new_start_date not in (None, "") else old_start
    expiry = _parse_date(new_expiry_date, "new_expiry_date") if new_expiry_date not in (None, "") else old_expiry
    if expiry < start:
        raise LandlordContractError("expiry date cannot be before the start date")
    if start == old_start and expiry == old_expiry:
        raise LandlordContractError("Nothing changed — the new dates match the current ones")

    if start != old_start:
        for allocation in contract.units or []:
            if allocation.from_date == old_start:
                allocation.from_date = start
                allocation.updated_by = actor.id

    contract.start_date = start
    contract.expiry_date = expiry
    contract.updated_by = actor.id
    db.session.flush()

    amendment = _add_amendment(
        contract, amendment_type="dates_correction", effective_date=date.today(), actor=actor,
        old_start_date=old_start, new_start_date=start,
        old_expiry_date=old_expiry, new_expiry_date=expiry,
        reason=reason, remarks=remarks,
    )
    audit.record(user=actor, action="amend", module="landlord_contract",
                 entity_type="property_agreement", entity_id=contract.id,
                 old_value={"start_date": old_start.isoformat(), "expiry_date": old_expiry.isoformat()},
                 new_value={"start_date": start.isoformat(), "expiry_date": expiry.isoformat()},
                 remarks=f"dates_correction {amendment.amendment_number}")
    return amendment
