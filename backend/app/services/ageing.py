"""Ageing and statements of account.

Two views of the same ledger, replacing two sheets of the master file:

  * **Ageing** — one row per client, one column per month, showing what
    is still outstanding for that month. This is the "Ageing" sheet.
  * **Statement of account** — one client's charges and receipts in date
    order with a running balance. This is the "Soa" sheet.
"""
from __future__ import annotations

from datetime import date

from ..extensions import db
from ..models import Client, ClientContract, Receipt, ReceiptAllocation, RentCharge
from .rent import add_months, month_start, month_end


def _month_labels(first: date, last: date) -> list[date]:
    out, cursor = [], month_start(first)
    stop = month_start(last)
    while cursor <= stop:
        out.append(cursor)
        cursor = add_months(cursor, 1)
    return out


def ageing(*, upto: date | None = None, months: int = 12,
           property_id: int | None = None) -> dict:
    """Outstanding per client per month, oldest month first.

    `months` limits how many columns are returned; anything older than
    the window is rolled into a single "older" bucket so nothing is
    silently dropped.
    """
    upto = month_start(upto or date.today())
    window_start = add_months(upto, -(months - 1))

    query = (
        db.session.query(RentCharge)
        .filter(RentCharge.period_month <= upto)
        .filter(RentCharge.status.in_(("open", "part_paid")))
    )
    if property_id:
        query = query.filter(RentCharge.property_id == property_id)

    rows: dict[int, dict] = {}
    for charge in query.all():
        due = charge.outstanding()
        if due <= 0:
            continue
        entry = rows.setdefault(charge.client_id, {
            "client_id": charge.client_id,
            "client_code": charge.client.code if charge.client else None,
            "client_name": charge.client.name if charge.client else None,
            "older": 0.0,
            "months": {},
            "total": 0.0,
        })
        key = charge.period_month
        if key < window_start:
            entry["older"] = round(entry["older"] + due, 2)
        else:
            entry["months"][key.isoformat()] = round(
                entry["months"].get(key.isoformat(), 0.0) + due, 2)
        entry["total"] = round(entry["total"] + due, 2)

    labels = [m.isoformat() for m in _month_labels(window_start, upto)]
    data = sorted(rows.values(), key=lambda r: r["total"], reverse=True)
    return {
        "months": labels,
        "rows": data,
        "grand_total": round(sum(r["total"] for r in data), 2),
        "upto": upto.isoformat(),
    }


def statement_of_account(client_id: int, *, from_date: date | None = None,
                         to_date: date | None = None) -> dict:
    """One client's ledger in date order with a running balance."""
    client = Client.query.get(client_id)
    if client is None:
        raise ValueError("client_id not found")

    charge_q = RentCharge.query.filter(RentCharge.client_id == client_id)
    receipt_q = (
        Receipt.query
        .filter(Receipt.client_id == client_id)
        .filter(Receipt.status == "posted")
    )
    if from_date:
        charge_q = charge_q.filter(RentCharge.period_month >= month_start(from_date))
        receipt_q = receipt_q.filter(Receipt.receipt_date >= from_date)
    if to_date:
        charge_q = charge_q.filter(RentCharge.period_month <= month_end(to_date))
        receipt_q = receipt_q.filter(Receipt.receipt_date <= to_date)

    lines: list[dict] = []
    for c in charge_q.all():
        label = "Opening balance" if c.is_opening_balance else (
            f"Rent {c.period_month.strftime('%b %Y')}")
        if c.is_free_month:
            label += " (rent-free)"
        lines.append({
            "date": c.period_month.isoformat(),
            "type": "charge",
            "reference": c.contract.contract_number if c.contract else None,
            "particulars": label,
            "debit": float(c.amount),
            "credit": 0.0,
            "note": c.proration_note,
        })
    for r in receipt_q.all():
        lines.append({
            "date": r.receipt_date.isoformat(),
            "type": "receipt",
            "reference": r.receipt_number,
            "particulars": f"Receipt — {r.mode}" + (f" ({r.reference})" if r.reference else ""),
            "debit": 0.0,
            "credit": float(r.amount),
            "note": None,
        })

    # Charges before receipts on the same date, so a month's rent is
    # raised before the money that settles it.
    lines.sort(key=lambda l: (l["date"], 0 if l["type"] == "charge" else 1))

    balance = 0.0
    for line in lines:
        balance = round(balance + line["debit"] - line["credit"], 2)
        line["balance"] = balance

    total_debit = round(sum(l["debit"] for l in lines), 2)
    total_credit = round(sum(l["credit"] for l in lines), 2)
    return {
        "client": {"id": client.id, "code": client.code, "name": client.name,
                   "name_ar": client.name_ar},
        "lines": lines,
        "totals": {
            "debit": total_debit,
            "credit": total_credit,
            "balance": round(total_debit - total_credit, 2),
        },
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": (to_date or date.today()).isoformat(),
    }


def outstanding_by_client(*, upto: date | None = None) -> list[dict]:
    """Every client with money owing — drives the collections screen."""
    upto = month_start(upto or date.today())
    rows = (
        db.session.query(
            RentCharge.client_id,
            db.func.sum(RentCharge.amount - RentCharge.allocated).label("due"),
            db.func.min(RentCharge.period_month).label("oldest"),
            db.func.count(RentCharge.id).label("open_months"),
        )
        .filter(RentCharge.period_month <= upto)
        .filter(RentCharge.status.in_(("open", "part_paid")))
        .group_by(RentCharge.client_id)
        .all()
    )
    if not rows:
        return []

    clients = {
        c.id: c for c in Client.query.filter(
            Client.id.in_([r.client_id for r in rows])).all()
    }
    today = date.today()
    out = []
    for r in rows:
        due = round(float(r.due or 0), 2)
        if due <= 0:
            continue
        client = clients.get(r.client_id)
        oldest = r.oldest
        out.append({
            "client_id": r.client_id,
            "client_code": client.code if client else None,
            "client_name": client.name if client else None,
            "outstanding": due,
            "open_months": int(r.open_months),
            "oldest_month": oldest.isoformat() if oldest else None,
            "days_overdue": (today - month_end(oldest)).days if oldest else 0,
        })
    return sorted(out, key=lambda r: r["outstanding"], reverse=True)
