"""Post-dated cheque (PDC) register.

A one-year cheque contract means 12 monthly rent cheques plus one
security cheque. Per docs/ACCOUNTING-RULES.md rule 9 a cheque is never
edited into a new state: every transition appends a ``ChequeEvent``, and
a bounced cheque is superseded by a *replacement* that links back to it.
"""
from __future__ import annotations

from datetime import date, datetime

from ..extensions import db
from ..models import Cheque, ChequeEvent, ClientContract
from . import audit


class ChequeError(ValueError):
    """Caller-visible validation failure."""


# Which transitions are legal from each state.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "received":  {"deposited", "returned"},
    # "returned" here covers a rent cheque the client asks back before
    # it clears — they pay cash instead — not just the security cheque.
    "deposited": {"cleared", "bounced", "returned"},
    "bounced":   {"replaced", "deposited"},   # re-present or replace
    "cleared":   set(),                        # terminal
    "replaced":  set(),                        # terminal
    "returned":  set(),                        # terminal (security handed back, or swapped for cash)
}


def _parse_date(value, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        raise ChequeError(f"{field} must be YYYY-MM-DD")


def _add_months(anchor: date, months: int) -> date:
    """Same day-of-month `months` later, clamped to the month's length."""
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp: 31 Jan + 1 month -> 28/29 Feb.
    for day in range(anchor.day, 0, -1):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ChequeError("Could not compute the cheque date")


def _event(cheque: Cheque, event_type: str, when: date, *, actor,
           bank_reference: str | None = None, reason: str | None = None,
           remarks: str | None = None) -> ChequeEvent:
    ev = ChequeEvent(
        cheque_id=cheque.id, event_type=event_type, event_date=when,
        bank_reference=bank_reference, reason=reason, remarks=remarks,
        created_by=actor.id, updated_by=actor.id,
    )
    db.session.add(ev)
    return ev


# ----------------------------------------------------------------------
# Registering cheques
# ----------------------------------------------------------------------

def add_cheque(contract: ClientContract, *, cheque_number: str, cheque_date,
               amount, bank_name: str | None = None, is_security: bool = False,
               for_month=None, remarks: str | None = None, actor) -> Cheque:
    number = (cheque_number or "").strip()
    if not number:
        raise ChequeError("cheque_number is required")
    when = _parse_date(cheque_date, "cheque_date")
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise ChequeError("amount must be a number")
    if value <= 0:
        raise ChequeError("amount must be greater than zero")

    duplicate = (
        Cheque.query
        .filter(Cheque.contract_id == contract.id)
        .filter(db.func.lower(Cheque.cheque_number) == number.lower())
        .first()
    )
    if duplicate is not None:
        raise ChequeError(f"Cheque {number} is already registered on this contract")

    cheque = Cheque(
        contract_id=contract.id,
        cheque_number=number,
        bank_name=bank_name,
        cheque_date=when,
        amount=value,
        is_security=bool(is_security),
        for_month=_parse_date(for_month, "for_month").replace(day=1) if for_month else None,
        status="received",
        remarks=remarks,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.session.add(cheque)
    db.session.flush()
    _event(cheque, "received", when, actor=actor)
    return cheque


def generate_schedule(contract: ClientContract, *, cheques: list[dict],
                      security: dict | None = None, actor) -> list[Cheque]:
    """Register a whole PDC book in one transaction.

    `cheques` is the rent book — one entry per month, each
    ``{cheque_number, bank_name, cheque_date, amount}``. `security` is
    the optional security cheque. Either every cheque is stored or none
    is, so a typo in the 11th row can't leave a half-entered book.
    """
    if contract.payment_mode != "cheque":
        raise ChequeError(
            f"Contract {contract.contract_number} is a {contract.payment_mode} "
            "contract — PDC cheques apply to cheque contracts")
    if not cheques and not security:
        raise ChequeError("Provide at least one cheque")

    created: list[Cheque] = []
    anchor = contract.start_date
    for index, row in enumerate(cheques or []):
        for_month = row.get("for_month") or _add_months(anchor.replace(day=1), index)
        created.append(add_cheque(
            contract,
            cheque_number=row.get("cheque_number"),
            bank_name=row.get("bank_name"),
            cheque_date=row.get("cheque_date") or _add_months(anchor, index),
            amount=row.get("amount", contract.monthly_rent),
            for_month=for_month,
            actor=actor,
        ))

    if security:
        created.append(add_cheque(
            contract,
            cheque_number=security.get("cheque_number"),
            bank_name=security.get("bank_name"),
            cheque_date=security.get("cheque_date") or contract.start_date,
            amount=security.get("amount", contract.monthly_rent),
            is_security=True,
            actor=actor,
        ))

    audit.record(user=actor, action="create", module="cheque",
                 entity_type="client_contract", entity_id=contract.id,
                 new_value={"cheques": len(created),
                            "security": bool(security)},
                 remarks=f"PDC book for {contract.contract_number}")
    return created


def build_schedule_preview(contract: ClientContract, *, count: int = 12,
                           start_date=None, amount=None) -> list[dict]:
    """Dates and amounts for a `count`-month book — for the entry grid."""
    anchor = _parse_date(start_date, "start_date") if start_date else contract.start_date
    value = float(amount) if amount not in (None, "") else float(contract.monthly_rent)
    return [
        {
            "sequence": i + 1,
            "cheque_date": _add_months(anchor, i).isoformat(),
            "for_month": _add_months(anchor.replace(day=1), i).isoformat(),
            "amount": value,
        }
        for i in range(count)
    ]


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------

def _transition(cheque: Cheque, to_status: str, when: date, *, actor, **event_kwargs) -> Cheque:
    allowed = ALLOWED_TRANSITIONS.get(cheque.status, set())
    if to_status not in allowed:
        raise ChequeError(
            f"Cheque {cheque.cheque_number} is '{cheque.status}' — "
            f"cannot move to '{to_status}'"
            + (f" (allowed: {sorted(allowed)})" if allowed else " (terminal state)")
        )
    old = cheque.status
    cheque.status = to_status
    cheque.updated_by = actor.id
    _event(cheque, to_status, when, actor=actor, **event_kwargs)
    db.session.flush()
    audit.record(user=actor, action=to_status, module="cheque",
                 entity_type="cheque", entity_id=cheque.id,
                 old_value={"status": old}, new_value={"status": to_status},
                 remarks=event_kwargs.get("reason"))
    return cheque


def deposit(cheque: Cheque, *, when=None, bank_reference: str | None = None, actor) -> Cheque:
    """Bank has the cheque — that is rent received.

    Depositing, not clearing, is the revenue-recognition point: a
    deposited rent cheque posts a receipt for its amount immediately,
    directed at the month it covers, so the cheque register and the
    rent ledger can never drift apart and the SOA reflects it right
    away. `clear()` afterwards only confirms the funds actually
    settled. The security cheque is not rent and posts nothing.

    A re-presented cheque (bounced -> deposited again) posts a fresh
    receipt each time it lands here — the one from the presentation
    that bounced was already voided by `bounce()` below, so there is
    never more than one posted receipt open against a given cheque.
    """
    settled = _parse_date(when, "when") if when else date.today()
    _transition(cheque, "deposited", settled, actor=actor, bank_reference=bank_reference)

    if not cheque.is_security:
        from . import receipts as receipt_service
        from ..models import RentCharge

        allocations = None
        if cheque.for_month:
            charge = (
                RentCharge.query
                .filter_by(contract_id=cheque.contract_id, period_month=cheque.for_month)
                .first()
            )
            if charge is not None:
                allocations = [{"charge_id": charge.id, "amount": float(cheque.amount)}]

        receipt_service.post_receipt(
            client_id=cheque.contract.client_id,
            amount=float(cheque.amount),
            receipt_date=settled,
            mode="cheque",
            reference=f"Cheque {cheque.cheque_number}",
            allocations=allocations,
            cheque_id=cheque.id,
            actor=actor,
        )
    return cheque


def clear(cheque: Cheque, *, when=None, bank_reference: str | None = None, actor) -> Cheque:
    """Bank confirmed the funds settled. The receipt was already posted
    at deposit — clearing is confirmation only, nothing further to book."""
    settled = _parse_date(when, "when") if when else date.today()
    return _transition(cheque, "cleared", settled, actor=actor, bank_reference=bank_reference)


def bounce(cheque: Cheque, *, reason: str, when=None, actor) -> Cheque:
    """Bank returned the cheque unpaid — reverse what deposit() booked.

    The receipt posted when this cheque was deposited is voided so its
    months reopen; the cheque itself becomes `bounced`, from which it
    can be replaced or re-presented.
    """
    if not (reason or "").strip():
        raise ChequeError("reason is required when a cheque bounces")
    when_parsed = _parse_date(when, "when") if when else date.today()
    _transition(cheque, "bounced", when_parsed, actor=actor, reason=reason)

    if not cheque.is_security:
        from . import receipts as receipt_service
        from ..models import Receipt

        receipt = Receipt.query.filter_by(cheque_id=cheque.id, status="posted").first()
        if receipt is not None:
            receipt_service.void_receipt(
                receipt, reason=f"Cheque {cheque.cheque_number} bounced", actor=actor)
    return cheque


def return_cheque(cheque: Cheque, *, when=None, remarks: str | None = None, actor) -> Cheque:
    """Hand a cheque back — the security cheque at contract end, or a
    rent cheque the client asks back before it clears because they're
    paying cash (or another cheque) instead.

    If the cheque had already been deposited, the receipt that posted
    is voided so its month reopens — the operator then records the
    replacement payment separately (the UI chains straight into it).
    """
    was_deposited = cheque.status == "deposited"
    when_parsed = _parse_date(when, "when") if when else date.today()
    _transition(cheque, "returned", when_parsed, actor=actor, remarks=remarks)

    if was_deposited and not cheque.is_security:
        from . import receipts as receipt_service
        from ..models import Receipt

        receipt = Receipt.query.filter_by(cheque_id=cheque.id, status="posted").first()
        if receipt is not None:
            receipt_service.void_receipt(
                receipt, reason=f"Cheque {cheque.cheque_number} returned to client", actor=actor)
    return cheque


def replace(cheque: Cheque, *, cheque_number: str, cheque_date, amount=None,
            bank_name: str | None = None, remarks: str | None = None, actor) -> Cheque:
    """Register a replacement for a bounced cheque.

    The bounced cheque becomes `replaced` (terminal) and the new one
    links back to it, so the trail from the original stays intact.
    """
    if cheque.status != "bounced":
        raise ChequeError("Only a bounced cheque can be replaced")

    contract = cheque.contract
    replacement = add_cheque(
        contract,
        cheque_number=cheque_number,
        bank_name=bank_name or cheque.bank_name,
        cheque_date=cheque_date,
        amount=amount if amount not in (None, "") else float(cheque.amount),
        is_security=cheque.is_security,
        for_month=cheque.for_month,
        remarks=remarks,
        actor=actor,
    )
    replacement.replaces_cheque_id = cheque.id

    _transition(cheque, "replaced", replacement.cheque_date, actor=actor,
                remarks=f"replaced by {replacement.cheque_number}")
    db.session.flush()
    return replacement


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

def due_for_deposit(within_days: int = 7, today: date | None = None) -> list[Cheque]:
    """Rent cheques whose date has arrived (or is about to) and are still held."""
    today = today or date.today()
    from datetime import timedelta
    cutoff = today + timedelta(days=within_days)
    return (
        Cheque.query
        .filter(Cheque.status == "received")
        .filter(Cheque.is_security.is_(False))
        .filter(Cheque.cheque_date <= cutoff)
        .order_by(Cheque.cheque_date.asc())
        .all()
    )


def bounced(today: date | None = None) -> list[Cheque]:
    """Cheques that bounced and have not yet been replaced."""
    return (
        Cheque.query
        .filter(Cheque.status == "bounced")
        .order_by(Cheque.cheque_date.asc())
        .all()
    )
