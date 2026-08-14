"""Client-contract lifecycle.

Everything that changes a contract after it is posted goes through an
amendment (docs/ACCOUNTING-RULES.md rule 3), and unit occupancy is
derived from the dated allocations rather than typed by hand (rule 10).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import (
    Client, ClientContract, ContractAmendment, ContractUnit, Property, Unit,
)
from ..models.contract import AMENDMENT_TYPES, PAYMENT_MODES
from . import audit


class ContractError(ValueError):
    """Caller-visible validation failure — surfaced as a 400/409."""


# ----------------------------------------------------------------------
# Numbering (gapless per month — ACCOUNTING-RULES rule 4)
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


def next_contract_number() -> str:
    return _next_number(ClientContract, ClientContract.contract_number, "CON")


def next_amendment_number() -> str:
    return _next_number(ContractAmendment, ContractAmendment.amendment_number, "AMD")


# ----------------------------------------------------------------------
# Occupancy derivation
# ----------------------------------------------------------------------

def recompute_unit_occupancy(unit_ids: list[int], on: date | None = None) -> None:
    """Set each unit's cached occupancy_status from its live allocations.

    `units.occupancy_status` is a projection, not a source of truth: a
    unit is occupied exactly when an open ContractUnit row covers `on`
    and its contract is active. Units parked in maintenance/blocked keep
    that status — those are deliberate operational states.
    """
    if not unit_ids:
        return
    on = on or date.today()

    held = {
        row.unit_id
        for row in (
            db.session.query(ContractUnit)
            .join(ClientContract, ContractUnit.contract_id == ClientContract.id)
            .filter(ContractUnit.unit_id.in_(unit_ids))
            .filter(ContractUnit.from_date <= on)
            .filter(db.or_(ContractUnit.to_date.is_(None), ContractUnit.to_date >= on))
            .filter(ClientContract.status == "active")
            .all()
        )
    }

    for unit in Unit.query.filter(Unit.id.in_(unit_ids)).all():
        if unit.occupancy_status in ("maintenance", "blocked"):
            continue
        unit.occupancy_status = "occupied" if unit.id in held else "empty"


def units_held_on(unit_ids: list[int], on: date,
                  exclude_contract_id: int | None = None) -> dict[int, ClientContract]:
    """Which of `unit_ids` are already held on `on`, and by whom."""
    if not unit_ids:
        return {}
    q = (
        db.session.query(ContractUnit, ClientContract)
        .join(ClientContract, ContractUnit.contract_id == ClientContract.id)
        .filter(ContractUnit.unit_id.in_(unit_ids))
        .filter(ContractUnit.from_date <= on)
        .filter(db.or_(ContractUnit.to_date.is_(None), ContractUnit.to_date >= on))
        .filter(ClientContract.status == "active")
    )
    if exclude_contract_id:
        q = q.filter(ClientContract.id != exclude_contract_id)
    return {cu.unit_id: contract for cu, contract in q.all()}


# ----------------------------------------------------------------------
# Create
# ----------------------------------------------------------------------

def _parse_date(value, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        raise ContractError(f"{field} must be YYYY-MM-DD")


def create_contract(
    *,
    client_id: int,
    property_id: int,
    unit_ids: list[int],
    start_date,
    expiry_date,
    monthly_rent,
    payment_mode: str,
    security_deposit=None,
    opening_balance=0,
    remarks: str | None = None,
    actor,
) -> ClientContract:
    """Post a new contract holding exactly `unit_ids`.

    Refuses if any unit is already held on the start date — that guard is
    what makes double-letting impossible.
    """
    if payment_mode not in PAYMENT_MODES:
        raise ContractError(f"payment_mode must be one of {sorted(PAYMENT_MODES)}")

    start = _parse_date(start_date, "start_date")
    expiry = _parse_date(expiry_date, "expiry_date")
    if expiry < start:
        raise ContractError("expiry_date must be on or after start_date")

    client = Client.query.get(client_id)
    if client is None:
        raise ContractError("client_id not found")
    prop = Property.query.get(property_id)
    if prop is None:
        raise ContractError("property_id not found")

    if not unit_ids:
        raise ContractError("At least one unit must be allocated")

    units = Unit.query.filter(Unit.id.in_(unit_ids)).all()
    if len(units) != len(set(unit_ids)):
        raise ContractError("One or more unit_ids not found")
    wrong_property = [u.unit_number for u in units if u.property_id != prop.id]
    if wrong_property:
        raise ContractError(
            f"Units {', '.join(sorted(wrong_property))} do not belong to {prop.code}")

    shared = [u.unit_number for u in units
              if u.is_facility() and u.is_shared_facility]
    if shared:
        raise ContractError(
            f"Units {', '.join(sorted(shared))} are shared facilities and "
            "cannot be allocated to one contract")

    clashes = units_held_on(list(unit_ids), start)
    if clashes:
        by_number = {u.id: u.unit_number for u in units}
        detail = ", ".join(
            f"{by_number[uid]} (held by {c.contract_number})"
            for uid, c in sorted(clashes.items())
        )
        raise ContractError(f"Already occupied on {start.isoformat()}: {detail}")

    try:
        rent = float(monthly_rent)
    except (TypeError, ValueError):
        raise ContractError("monthly_rent must be a number")
    if rent < 0:
        raise ContractError("monthly_rent cannot be negative")

    contract = ClientContract(
        contract_number=next_contract_number(),
        client_id=client.id,
        property_id=prop.id,
        start_date=start,
        expiry_date=expiry,
        monthly_rent=rent,
        payment_mode=payment_mode,
        security_deposit=float(security_deposit) if security_deposit not in (None, "") else None,
        opening_balance=float(opening_balance or 0),
        status="active",
        remarks=remarks,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.session.add(contract)
    db.session.flush()

    for unit in units:
        db.session.add(ContractUnit(
            contract_id=contract.id, unit_id=unit.id, from_date=start,
            created_by=actor.id, updated_by=actor.id,
        ))
    db.session.flush()

    recompute_unit_occupancy([u.id for u in units], on=max(start, date.today()))
    audit.record(user=actor, action="create", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 new_value=contract.to_dict(),
                 remarks=f"{len(units)} unit(s) allocated")
    return contract


# ----------------------------------------------------------------------
# Amendments
# ----------------------------------------------------------------------

def _add_amendment(contract: ClientContract, *, amendment_type: str,
                   effective_date: date, actor, **fields) -> ContractAmendment:
    if amendment_type not in AMENDMENT_TYPES:
        raise ContractError(f"amendment_type must be one of {sorted(AMENDMENT_TYPES)}")
    sequence = len(contract.amendments or []) + 1
    amendment = ContractAmendment(
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


def require_active(contract: ClientContract) -> None:
    """Public so the approval gate can reject an impossible request at the
    point it is raised, rather than letting it sit in the queue and fail
    on the approver's screen."""
    if contract.status != "active":
        raise ContractError(f"Contract is {contract.status}; only active contracts can be amended")


def change_rent(contract: ClientContract, *, new_rent, effective_date,
                reason: str | None = None, remarks: str | None = None,
                actor) -> ContractAmendment:
    """Rent reduction or increase — the 28,000 → 26,000 case."""
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    try:
        value = float(new_rent)
    except (TypeError, ValueError):
        raise ContractError("new_rent must be a number")
    if value < 0:
        raise ContractError("new_rent cannot be negative")
    old = float(contract.monthly_rent)
    if value == old:
        raise ContractError("new_rent is the same as the current rent")

    amendment = _add_amendment(
        contract, amendment_type="rent_change", effective_date=when, actor=actor,
        old_rent=old, new_rent=value, reason=reason, remarks=remarks,
    )
    contract.monthly_rent = value
    contract.updated_by = actor.id
    audit.record(user=actor, action="amend", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 old_value={"monthly_rent": old}, new_value={"monthly_rent": value},
                 remarks=f"rent_change {amendment.amendment_number}")
    return amendment


def grant_free_months(contract: ClientContract, *, months: int, from_month,
                      reason: str | None = None, remarks: str | None = None,
                      actor) -> ContractAmendment:
    """Rent-free period. The rent schedule (Phase 3) reads these."""
    require_active(contract)
    try:
        count = int(months)
    except (TypeError, ValueError):
        raise ContractError("months must be a whole number")
    if count < 1:
        raise ContractError("months must be at least 1")
    start = _parse_date(from_month, "from_month").replace(day=1)

    amendment = _add_amendment(
        contract, amendment_type="free_months", effective_date=start, actor=actor,
        free_months=count, free_from_month=start, reason=reason, remarks=remarks,
    )
    audit.record(user=actor, action="amend", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 new_value={"free_months": count, "from_month": start.isoformat()},
                 remarks=f"free_months {amendment.amendment_number}")
    return amendment


def add_units(contract: ClientContract, *, unit_ids: list[int], effective_date,
              reason: str | None = None, actor) -> ContractAmendment:
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    if not unit_ids:
        raise ContractError("unit_ids is required")

    already = {a.unit_id for a in contract.active_allocations(when)}
    wanted = [uid for uid in dict.fromkeys(unit_ids) if uid not in already]
    if not wanted:
        raise ContractError("Those units are already on this contract")

    units = Unit.query.filter(Unit.id.in_(wanted)).all()
    if len(units) != len(wanted):
        raise ContractError("One or more unit_ids not found")
    wrong = [u.unit_number for u in units if u.property_id != contract.property_id]
    if wrong:
        raise ContractError(f"Units {', '.join(sorted(wrong))} belong to another property")

    clashes = units_held_on(wanted, when, exclude_contract_id=contract.id)
    if clashes:
        by_number = {u.id: u.unit_number for u in units}
        detail = ", ".join(f"{by_number[uid]} (held by {c.contract_number})"
                           for uid, c in sorted(clashes.items()))
        raise ContractError(f"Already occupied on {when.isoformat()}: {detail}")

    for unit in units:
        db.session.add(ContractUnit(
            contract_id=contract.id, unit_id=unit.id, from_date=when,
            created_by=actor.id, updated_by=actor.id,
        ))
    db.session.flush()

    amendment = _add_amendment(
        contract, amendment_type="units_added", effective_date=when, actor=actor,
        unit_ids=",".join(str(u.id) for u in units), reason=reason,
    )
    contract.updated_by = actor.id
    recompute_unit_occupancy([u.id for u in units], on=max(when, date.today()))
    audit.record(user=actor, action="amend", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 new_value={"units_added": [u.unit_number for u in units]},
                 remarks=f"units_added {amendment.amendment_number}")
    return amendment


def remove_units(contract: ClientContract, *, unit_ids: list[int], effective_date,
                 reason: str | None = None, actor) -> ContractAmendment:
    """Reduce the room count — release specific unit numbers.

    The allocation row is closed with `to_date`, never deleted, so past
    months still show the client holding the unit.
    """
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    if not unit_ids:
        raise ContractError("unit_ids is required")

    wanted = set(unit_ids)
    open_allocations = {a.unit_id: a for a in contract.active_allocations(when)}
    missing = wanted - set(open_allocations)
    if missing:
        raise ContractError(f"Units {sorted(missing)} are not held by this contract on {when.isoformat()}")
    if wanted == set(open_allocations):
        raise ContractError(
            "That would release every unit — cancel the contract instead")

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
    recompute_unit_occupancy(sorted(wanted), on=max(when, date.today()))
    audit.record(user=actor, action="amend", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 old_value={"units_held": len(open_allocations)},
                 new_value={"units_released": sorted(released)},
                 remarks=f"units_removed {amendment.amendment_number}")
    return amendment


def cancel_contract(contract: ClientContract, *, effective_date, reason: str,
                    remarks: str | None = None, actor) -> ContractAmendment:
    """End a contract early. Releases every unit as of the effective date."""
    require_active(contract)
    when = _parse_date(effective_date, "effective_date")
    if not (reason or "").strip():
        raise ContractError("reason is required to cancel a contract")

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
    contract.updated_by = actor.id
    db.session.flush()

    amendment = _add_amendment(
        contract, amendment_type="cancellation", effective_date=when, actor=actor,
        unit_ids=",".join(str(u) for u in touched), reason=reason, remarks=remarks,
    )
    recompute_unit_occupancy(touched, on=max(when, date.today()))
    audit.record(user=actor, action="cancel", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 old_value={"status": "active"},
                 new_value={"status": "cancelled", "effective_date": when.isoformat(),
                            "reason": reason},
                 remarks=f"cancellation {amendment.amendment_number}")
    return amendment


def correct_dates(contract: ClientContract, *, new_start_date=None, new_expiry_date=None,
                  reason: str, remarks: str | None = None, actor) -> ContractAmendment:
    """Fix a data-entry mistake in the contract's start or expiry date.

    Unlike `renew_contract`, this does not supersede the contract with a
    new one and does not touch which units it holds — it is for typos on
    the original agreement, not a genuine new term. Kept as a dated
    amendment (never a silent overwrite) so the wrong value stays visible
    in the history.
    """
    if contract.status not in ("active", "expired"):
        raise ContractError(
            f"Contract is {contract.status}; only an active or expired contract's dates can be corrected")
    if not (reason or "").strip():
        raise ContractError("reason is required to correct contract dates")

    old_start = contract.start_date
    old_expiry = contract.expiry_date
    old_status = contract.status
    start = _parse_date(new_start_date, "new_start_date") if new_start_date not in (None, "") else old_start
    expiry = _parse_date(new_expiry_date, "new_expiry_date") if new_expiry_date not in (None, "") else old_expiry
    if expiry < start:
        raise ContractError("expiry date cannot be before the start date")
    if start == old_start and expiry == old_expiry:
        raise ContractError("Nothing changed — the new dates match the current ones")

    touched_units: set[int] = set()

    # Units allocated when the contract was created got from_date == the
    # (wrong) start date — keep them in sync. Units added later via a
    # separate amendment keep their own effective date untouched.
    if start != old_start:
        for allocation in contract.allocations or []:
            if allocation.from_date == old_start:
                allocation.from_date = start
                allocation.updated_by = actor.id
                touched_units.add(allocation.unit_id)

    # A contract that only lapsed because the old expiry date was wrong
    # was auto-closed by the nightly sweep: its allocations were cut off
    # at that (wrong) date. Reopen them so the correction actually takes.
    if old_status == "expired" and expiry != old_expiry:
        for allocation in contract.allocations or []:
            if allocation.to_date == old_expiry:
                allocation.to_date = None if expiry >= date.today() else expiry
                allocation.updated_by = actor.id
                touched_units.add(allocation.unit_id)

    contract.start_date = start
    contract.expiry_date = expiry
    contract.status = "expired" if expiry < date.today() else "active"
    contract.updated_by = actor.id
    db.session.flush()

    amendment = _add_amendment(
        contract, amendment_type="dates_correction", effective_date=date.today(), actor=actor,
        old_start_date=old_start, new_start_date=start,
        old_expiry_date=old_expiry, new_expiry_date=expiry,
        reason=reason, remarks=remarks,
    )
    if touched_units:
        recompute_unit_occupancy(sorted(touched_units), on=date.today())
    audit.record(user=actor, action="amend", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 old_value={"start_date": old_start.isoformat(), "expiry_date": old_expiry.isoformat(),
                            "status": old_status},
                 new_value={"start_date": start.isoformat(), "expiry_date": expiry.isoformat(),
                            "status": contract.status},
                 remarks=f"dates_correction {amendment.amendment_number}")
    return amendment


def renew_contract(contract: ClientContract, *, new_start_date, new_expiry_date,
                   new_monthly_rent=None, remarks: str | None = None,
                   actor) -> ClientContract:
    """Supersede a contract with a fresh one carrying the same units."""
    require_active(contract)
    start = _parse_date(new_start_date, "new_start_date")
    expiry = _parse_date(new_expiry_date, "new_expiry_date")
    if expiry < start:
        raise ContractError("new_expiry_date must be on or after new_start_date")

    carried = contract.active_allocations(contract.expiry_date)
    if not carried:
        raise ContractError("Contract holds no units to carry forward")

    # Close the old contract the day the new one starts.
    handover = start - timedelta(days=1)
    for allocation in carried:
        allocation.to_date = handover
        allocation.updated_by = actor.id

    rent = float(new_monthly_rent) if new_monthly_rent not in (None, "") else float(contract.monthly_rent)

    renewal = ClientContract(
        contract_number=next_contract_number(),
        client_id=contract.client_id,
        property_id=contract.property_id,
        start_date=start,
        expiry_date=expiry,
        monthly_rent=rent,
        payment_mode=contract.payment_mode,
        security_deposit=contract.security_deposit,
        opening_balance=0,
        status="active",
        remarks=remarks,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.session.add(renewal)
    db.session.flush()

    for allocation in carried:
        db.session.add(ContractUnit(
            contract_id=renewal.id, unit_id=allocation.unit_id, from_date=start,
            created_by=actor.id, updated_by=actor.id,
        ))

    contract.status = "renewed"
    contract.renewed_to_id = renewal.id
    contract.updated_by = actor.id
    db.session.flush()

    _add_amendment(contract, amendment_type="renewal", effective_date=start, actor=actor,
                   old_rent=float(contract.monthly_rent), new_rent=rent,
                   unit_ids=",".join(str(a.unit_id) for a in carried),
                   remarks=f"renewed as {renewal.contract_number}")

    recompute_unit_occupancy([a.unit_id for a in carried], on=max(start, date.today()))
    audit.record(user=actor, action="renew", module="contract",
                 entity_type="client_contract", entity_id=contract.id,
                 old_value={"contract_number": contract.contract_number},
                 new_value={"contract_number": renewal.contract_number,
                            "monthly_rent": rent},
                 remarks=f"renewed into {renewal.contract_number}")
    return renewal


# ----------------------------------------------------------------------
# Expiry sweep
# ----------------------------------------------------------------------

def expire_due_contracts(today: date | None = None) -> list[int]:
    """Flip active contracts past their expiry date to `expired`.

    Returns the ids touched. Idempotent — safe to run daily.
    """
    today = today or date.today()
    rows = (
        ClientContract.query
        .filter(ClientContract.status == "active")
        .filter(ClientContract.expiry_date < today)
        .all()
    )
    touched_units: list[int] = []
    ids: list[int] = []
    for contract in rows:
        contract.status = "expired"
        for allocation in contract.active_allocations(today):
            allocation.to_date = contract.expiry_date
            touched_units.append(allocation.unit_id)
        ids.append(contract.id)
    if ids:
        db.session.flush()
        recompute_unit_occupancy(touched_units, on=today)
    return ids
