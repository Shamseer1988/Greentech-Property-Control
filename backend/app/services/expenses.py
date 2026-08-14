"""Landlord payments, expense entry, and property-wise profit & loss.

The P&L here is the point of the whole system: the accounting software
reports company totals, this reports **per property per month**

    rent charged  −  rent paid to the landlord  −  direct expenses
    ────────────────────────────────────────────────────────────────
                       = profit or loss

which is exactly the "Profit Or Loss" line at the bottom of each block
in the New-2026 sheet.
"""
from __future__ import annotations

from datetime import date, datetime

from ..extensions import db
from ..models import (
    Expense, ExpenseCategory, Landlord, LandlordCharge, LandlordContract,
    LandlordPayment, LandlordPaymentAllocation, Property, RentCharge,
)
from ..models.expense import PAYMENT_MODES
from . import audit, numbering
from .landlord_rent import open_charges_for
from .rent import month_start


class ExpenseError(ValueError):
    """Caller-visible failure."""


def _parse_date(value, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        raise ExpenseError(f"{field} must be YYYY-MM-DD")


# ----------------------------------------------------------------------
# Landlord payments
# ----------------------------------------------------------------------

def _legacy_max_voucher_number(month_key: str) -> int:
    like = f"PV-{month_key}-%"
    last = (
        db.session.query(LandlordPayment.voucher_number)
        .filter(LandlordPayment.voucher_number.like(like))
        .order_by(LandlordPayment.voucher_number.desc())
        .limit(1)
        .scalar()
    )
    if not last:
        return 0
    try:
        return int(last.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def next_voucher_number() -> str:
    """Race-safe: locked via `services.numbering` so batch-posting many
    vouchers in one transaction (the bulk entry screen) never collides."""
    month_key = datetime.utcnow().strftime("%Y%m")
    return numbering.next_number("PV", month_key,
                                 legacy_seed=lambda: _legacy_max_voucher_number(month_key))


def _apply_to_landlord_charge(payment: LandlordPayment, charge: LandlordCharge,
                              amount: float, *, manual: bool, actor) -> float:
    """Put `amount` (capped at what's due) against `charge`."""
    due = charge.outstanding()
    applied = round(min(due, amount), 2)
    if applied <= 0:
        return 0.0
    db.session.add(LandlordPaymentAllocation(
        payment_id=payment.id, charge_id=charge.id, amount=applied,
        is_manual=manual, created_by=actor.id, updated_by=actor.id,
    ))
    charge.allocated = round(charge._allocated() + applied, 2)
    charge.recompute_status()
    charge.updated_by = actor.id
    return applied


def post_landlord_payment(*, landlord_id: int, property_id: int, period_month,
                          amount, payment_date=None, mode: str = "cheque",
                          reference: str | None = None, remarks: str | None = None,
                          contract_id: int | None = None,
                          allocations: list[dict] | None = None,
                          actor) -> LandlordPayment:
    """Record money paid to a landlord and settle open dues with it.

    Allocation mirrors `receipts.post_receipt`, scoped to
    `(landlord_id, property_id)` — never landlord alone, so a
    multi-building landlord's cheque for Building A can never settle a
    Building B arrear (that would corrupt per-property P&L). `contract_id`
    is informational tagging; explicit `allocations` (``[{charge_id,
    amount}]``) direct money at specific months first, and whatever's
    left flows to the oldest open charge in scope.
    """
    if mode not in PAYMENT_MODES:
        raise ExpenseError(f"mode must be one of {sorted(PAYMENT_MODES)}")
    landlord = Landlord.query.get(landlord_id)
    if landlord is None:
        raise ExpenseError("landlord_id not found")
    prop = Property.query.get(property_id)
    if prop is None:
        raise ExpenseError("property_id not found")
    if contract_id is not None:
        contract = LandlordContract.query.get(contract_id)
        if contract is None:
            raise ExpenseError("contract_id not found")
        if contract.landlord_id != landlord.id or contract.property_id != prop.id:
            raise ExpenseError("contract_id does not belong to this landlord/property")
    try:
        value = round(float(amount), 2)
    except (TypeError, ValueError):
        raise ExpenseError("amount must be a number")
    if value <= 0:
        raise ExpenseError("amount must be greater than zero")

    period = month_start(_parse_date(period_month, "period_month"))
    when = _parse_date(payment_date, "payment_date") if payment_date else date.today()

    payment = LandlordPayment(
        voucher_number=next_voucher_number(),
        landlord_id=landlord.id,
        property_id=prop.id,
        contract_id=contract_id,
        period_month=period,
        payment_date=when,
        amount=value,
        mode=mode,
        reference=reference,
        status="posted",
        remarks=remarks,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.session.add(payment)
    db.session.flush()

    remaining = value

    for row in (allocations or []):
        if remaining <= 0:
            break
        charge = LandlordCharge.query.get(row.get("charge_id"))
        if charge is None:
            raise ExpenseError(f"charge_id {row.get('charge_id')} not found")
        if charge.landlord_id != landlord.id or charge.property_id != prop.id:
            raise ExpenseError(f"Charge {charge.id} is outside this landlord/property")
        want = row.get("amount")
        want = remaining if want in (None, "") else round(float(want), 2)
        applied = _apply_to_landlord_charge(payment, charge, min(want, remaining),
                                            manual=True, actor=actor)
        remaining = round(remaining - applied, 2)

    if remaining > 0:
        already = {a.charge_id for a in (payment.allocations or [])}
        for charge in open_charges_for(landlord.id, prop.id):
            if remaining <= 0:
                break
            if charge.id in already:
                continue
            applied = _apply_to_landlord_charge(payment, charge, remaining,
                                                manual=False, actor=actor)
            remaining = round(remaining - applied, 2)

    db.session.flush()
    audit.record(user=actor, action="post", module="landlord_payment",
                 entity_type="landlord_payment", entity_id=payment.id,
                 new_value=payment.to_dict(),
                 remarks=f"{prop.code} {period.strftime('%b %Y')}")
    return payment


def void_landlord_payment(payment: LandlordPayment, *, reason: str, actor) -> LandlordPayment:
    """Reverse a landlord payment. The row stays; the dues it settled
    reopen — the allocation-reversal mirror of `receipts.void_receipt`."""
    if payment.status == "voided":
        raise ExpenseError(f"Voucher {payment.voucher_number} is already voided")
    if not (reason or "").strip():
        raise ExpenseError("reason is required to void a payment")

    for allocation in list(payment.allocations or []):
        charge = allocation.charge
        if charge is not None:
            charge.allocated = round(charge._allocated() - float(allocation.amount), 2)
            if charge.allocated < 0:
                charge.allocated = 0
            charge.recompute_status()
            charge.updated_by = actor.id
        db.session.delete(allocation)

    payment.status = "voided"
    payment.void_reason = reason
    payment.voided_at = date.today()
    payment.voided_by = actor.id
    payment.updated_by = actor.id
    db.session.flush()
    audit.record(user=actor, action="void", module="landlord_payment",
                 entity_type="landlord_payment", entity_id=payment.id,
                 old_value={"status": "posted"},
                 new_value={"status": "voided", "reason": reason})
    return payment


def landlord_statement(landlord_id: int, *, from_month=None, to_month=None) -> dict:
    """What was agreed vs what was paid, per property per month."""
    landlord = Landlord.query.get(landlord_id)
    if landlord is None:
        raise ExpenseError("landlord_id not found")

    query = LandlordPayment.query.filter_by(landlord_id=landlord_id, status="posted")
    if from_month:
        query = query.filter(LandlordPayment.period_month >= month_start(
            _parse_date(from_month, "from_month")))
    if to_month:
        query = query.filter(LandlordPayment.period_month <= month_start(
            _parse_date(to_month, "to_month")))

    rows = query.order_by(LandlordPayment.period_month.asc(),
                          LandlordPayment.id.asc()).all()
    return {
        "landlord": {"id": landlord.id, "code": landlord.code, "name": landlord.name,
                     "name_ar": landlord.name_ar},
        "payments": [p.to_dict() for p in rows],
        "total_paid": round(sum(float(p.amount) for p in rows), 2),
    }


# ----------------------------------------------------------------------
# Expenses
# ----------------------------------------------------------------------

def post_expense(*, category_id: int, period_month, amount,
                 property_id: int | None = None, reference: str | None = None,
                 remarks: str | None = None, actor) -> Expense:
    category = ExpenseCategory.query.get(category_id)
    if category is None:
        raise ExpenseError("category_id not found")
    try:
        value = round(float(amount), 2)
    except (TypeError, ValueError):
        raise ExpenseError("amount must be a number")
    if value <= 0:
        raise ExpenseError("amount must be greater than zero")
    if property_id is not None and Property.query.get(property_id) is None:
        raise ExpenseError("property_id not found")

    expense = Expense(
        category_id=category.id,
        property_id=property_id,
        period_month=month_start(_parse_date(period_month, "period_month")),
        amount=value,
        source="manual",
        reference=reference,
        remarks=remarks,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.session.add(expense)
    db.session.flush()
    audit.record(user=actor, action="create", module="expense",
                 entity_type="expense", entity_id=expense.id,
                 new_value=expense.to_dict())
    return expense


def allocate_expense(expense: Expense, *, property_id: int | None, actor) -> Expense:
    """Attach an imported company-level cost to a property (or detach it)."""
    if property_id is not None and Property.query.get(property_id) is None:
        raise ExpenseError("property_id not found")
    old = expense.property_id
    expense.property_id = property_id
    expense.updated_by = actor.id
    db.session.flush()
    audit.record(user=actor, action="allocate", module="expense",
                 entity_type="expense", entity_id=expense.id,
                 old_value={"property_id": old},
                 new_value={"property_id": property_id})
    return expense


def update_expense(expense: Expense, *, remarks: str | None = None,
                   reference: str | None = None, actor) -> Expense:
    """Non-financial metadata only. Amount/category/month/property are
    correction-only (void + repost) per docs/ACCOUNTING-RULES.md rule 2."""
    if expense.status == "voided":
        raise ExpenseError("A voided expense cannot be edited")
    old = {"remarks": expense.remarks, "reference": expense.reference}
    if remarks is not None:
        expense.remarks = remarks
    if reference is not None:
        expense.reference = reference
    expense.updated_by = actor.id
    db.session.flush()
    audit.record(user=actor, action="update", module="expense",
                 entity_type="expense", entity_id=expense.id,
                 old_value=old,
                 new_value={"remarks": expense.remarks, "reference": expense.reference})
    return expense


def void_expense(expense: Expense, *, reason: str, actor) -> Expense:
    if expense.status == "voided":
        raise ExpenseError("This expense is already voided")
    if not (reason or "").strip():
        raise ExpenseError("reason is required to void an expense")
    expense.status = "voided"
    expense.void_reason = reason
    expense.voided_at = date.today()
    expense.voided_by = actor.id
    expense.updated_by = actor.id
    db.session.flush()
    audit.record(user=actor, action="void", module="expense",
                 entity_type="expense", entity_id=expense.id,
                 old_value={"status": "posted"},
                 new_value={"status": "voided", "reason": reason})
    return expense


def update_category(category: ExpenseCategory, *, name: str | None = None,
                    kind: str | None = None, is_property_wise: bool | None = None,
                    is_active: bool | None = None, remarks: str | None = None,
                    actor) -> ExpenseCategory:
    from ..models.expense import CATEGORY_KINDS
    if kind is not None and kind not in CATEGORY_KINDS:
        raise ExpenseError(f"kind must be one of {sorted(CATEGORY_KINDS)}")
    old = category.to_dict()
    if name is not None:
        stripped = name.strip()
        if not stripped:
            raise ExpenseError("name cannot be empty")
        category.name = stripped
    if kind is not None:
        category.kind = kind
    if is_property_wise is not None:
        category.is_property_wise = is_property_wise
    if is_active is not None:
        category.is_active = is_active
    if remarks is not None:
        category.remarks = remarks
    category.updated_by = actor.id
    db.session.flush()
    audit.record(user=actor, action="update", module="expense_category",
                 entity_type="expense_category", entity_id=category.id,
                 old_value=old, new_value=category.to_dict())
    return category


# ----------------------------------------------------------------------
# Property-wise profit & loss
# ----------------------------------------------------------------------

def property_pnl(*, period_month, property_id: int | None = None) -> dict:
    """Per-property income, costs and margin for one month."""
    period = month_start(_parse_date(period_month, "period_month"))

    props_q = Property.query
    if property_id:
        props_q = props_q.filter(Property.id == property_id)
    properties = {p.id: p for p in props_q.order_by(Property.name.asc()).all()}
    if not properties:
        return {"month": period.isoformat(), "rows": [], "totals": {}}

    ids = list(properties)

    charged = dict(
        db.session.query(RentCharge.property_id,
                         db.func.coalesce(db.func.sum(RentCharge.amount), 0))
        .filter(RentCharge.period_month == period)
        .filter(RentCharge.property_id.in_(ids))
        # A carried-forward balance is booked as income in the month the
        # tenancy actually started, not whatever month it happens to be
        # collected — counting it here too would report it twice.
        .filter(RentCharge.is_opening_balance.is_(False))
        .group_by(RentCharge.property_id).all()
    )
    collected = dict(
        db.session.query(RentCharge.property_id,
                         db.func.coalesce(db.func.sum(RentCharge.allocated), 0))
        .filter(RentCharge.period_month == period)
        .filter(RentCharge.property_id.in_(ids))
        .group_by(RentCharge.property_id).all()
    )
    rent_paid = dict(
        db.session.query(LandlordPayment.property_id,
                         db.func.coalesce(db.func.sum(LandlordPayment.amount), 0))
        .filter(LandlordPayment.period_month == period)
        .filter(LandlordPayment.status == "posted")
        .filter(LandlordPayment.property_id.in_(ids))
        .group_by(LandlordPayment.property_id).all()
    )
    # Accrual rent expense: what's *due* to the landlord this month, from
    # the dues ledger (landlord_charges), not what was actually paid.
    # A property with no charges generated yet (the ledger hasn't been
    # backfilled for it) falls back to the cash figure — this is what
    # keeps the switch a no-op until `landlord-dues generate` has run.
    rent_due = dict(
        db.session.query(LandlordCharge.property_id,
                         db.func.coalesce(db.func.sum(LandlordCharge.amount), 0))
        .filter(LandlordCharge.period_month == period)
        .filter(LandlordCharge.property_id.in_(ids))
        .group_by(LandlordCharge.property_id).all()
    )

    # Direct expenses, broken out by category so the row reads like the
    # workbook's block (sewage, electricity, maintenance…). RENT_PAID is
    # excluded — it would double-count "rent_due_landlord"/"rent_paid"
    # above, already sourced from landlord_charges/LandlordPayment.
    expense_rows = (
        db.session.query(Expense.property_id, ExpenseCategory.name,
                         db.func.coalesce(db.func.sum(Expense.amount), 0))
        .join(ExpenseCategory, Expense.category_id == ExpenseCategory.id)
        .filter(Expense.period_month == period)
        .filter(Expense.property_id.in_(ids))
        .filter(Expense.status == "posted")
        .filter(ExpenseCategory.code != "RENT_PAID")
        .filter(ExpenseCategory.kind != "income")
        .group_by(Expense.property_id, ExpenseCategory.name)
        .all()
    )
    by_property_expense: dict[int, dict[str, float]] = {}
    for pid, name, total in expense_rows:
        by_property_expense.setdefault(pid, {})[name] = round(float(total or 0), 2)

    rows = []
    for pid, prop in properties.items():
        income = round(float(charged.get(pid, 0) or 0), 2)
        got = round(float(collected.get(pid, 0) or 0), 2)
        paid = round(float(rent_paid.get(pid, 0) or 0), 2)
        due_landlord = round(float(rent_due[pid]), 2) if pid in rent_due else paid
        expenses = by_property_expense.get(pid, {})
        expense_total = round(sum(expenses.values()), 2)
        rows.append({
            "property_id": pid,
            "property_code": prop.code,
            "property_name": prop.name,
            "rent_charged": income,
            "rent_collected": got,
            "rent_paid": paid,
            "rent_due_landlord": due_landlord,
            "expenses": expenses,
            "expense_total": expense_total,
            "profit": round(income - due_landlord - expense_total, 2),
            "cash_profit": round(got - paid - expense_total, 2),
        })

    totals = {
        "rent_charged": round(sum(r["rent_charged"] for r in rows), 2),
        "rent_collected": round(sum(r["rent_collected"] for r in rows), 2),
        "rent_paid": round(sum(r["rent_paid"] for r in rows), 2),
        "rent_due_landlord": round(sum(r["rent_due_landlord"] for r in rows), 2),
        "expense_total": round(sum(r["expense_total"] for r in rows), 2),
        "profit": round(sum(r["profit"] for r in rows), 2),
    }

    # Company overhead isn't attributable to a property; report it beside
    # the property rows so the net figure can still be reconciled.
    overhead = (
        db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0))
        .join(ExpenseCategory, Expense.category_id == ExpenseCategory.id)
        .filter(Expense.period_month == period)
        .filter(Expense.property_id.is_(None))
        .filter(ExpenseCategory.kind == "indirect")
        .filter(Expense.status == "posted")
        .scalar() or 0
    )
    unallocated_direct = (
        db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0))
        .join(ExpenseCategory, Expense.category_id == ExpenseCategory.id)
        .filter(Expense.period_month == period)
        .filter(Expense.property_id.is_(None))
        .filter(ExpenseCategory.kind == "direct")
        .filter(ExpenseCategory.code != "RENT_PAID")
        .filter(Expense.status == "posted")
        .scalar() or 0
    )
    totals["company_overhead"] = round(float(overhead), 2)
    totals["unallocated_direct"] = round(float(unallocated_direct), 2)
    totals["net_profit"] = round(
        totals["profit"] - totals["company_overhead"] - totals["unallocated_direct"], 2)

    return {"month": period.isoformat(), "rows": rows, "totals": totals}
