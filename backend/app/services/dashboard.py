"""Dashboard aggregations.

`summary()` is the main dashboard's single call: the estate (properties,
units, landlords), the money (collections, ageing, month P&L), and what
needs attention (expiring contracts and documents, cheques due and
bounced, approvals waiting).

Every figure here is read from the same services the pages and reports
use — `collections_summary`, `ageing`, `property_pnl` and friends — so a
number on the dashboard cannot disagree with the same number on its
report. Nothing is computed twice.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import (
    Property, Unit, Landlord, PropertyAgreement, MaintenanceRecord,
    AuditLog, User, ClientContract, Client, Cheque, Receipt,
)
from .reminders import reminder_summary, expiring_agreements
from .approvals import pending_counts
from .documents import expiring_documents
from .rent import month_start, add_months
from .receipts import collections_summary
from .ageing import ageing
from .expenses import property_pnl, landlord_statement
from . import cheques as cheque_service
from .cache import cache_get, cache_set

# The dashboard's aggregate queries (P&L trend alone runs property_pnl()
# 12 times per request) are expensive enough, and tolerant enough of a
# few seconds' staleness, that a short cache is a clear win — this is
# the single most-hit read in the app.
_CACHE_TTL = 60


def _property_counts() -> dict:
    rows = (
        db.session.query(Property.status, func.count(Property.id))
        .group_by(Property.status)
        .all()
    )
    counts = {"total": 0, "active": 0, "inactive": 0, "maintenance": 0, "vacated": 0}
    for status, n in rows:
        counts[status] = counts.get(status, 0) + n
        counts["total"] += n
    return counts


def _unit_counts() -> dict:
    rows = (
        db.session.query(Unit.occupancy_status, func.count(Unit.id))
        .group_by(Unit.occupancy_status)
        .all()
    )
    counts = {"total": 0, "empty": 0, "occupied": 0, "maintenance": 0, "blocked": 0}
    for status, n in rows:
        counts[status] = counts.get(status, 0) + n
        counts["total"] += n
    counts["occupancy_percent"] = (
        round(counts["occupied"] * 100.0 / counts["total"], 1) if counts["total"] else 0.0
    )
    return counts


def contract_expiry(today: date | None = None) -> dict:
    """Active client contracts bucketed by how soon they run out.

    Buckets are cumulative-free — a contract lands in exactly one — so
    the four numbers add up to the count of contracts expiring within 90
    days plus those already past their date.
    """
    today = today or date.today()
    rows = (
        db.session.query(ClientContract, Client)
        .join(Client, ClientContract.client_id == Client.id)
        .filter(ClientContract.status == "active")
        .filter(ClientContract.expiry_date <= today + timedelta(days=90))
        .order_by(ClientContract.expiry_date)
        .all()
    )
    buckets = {"expired": 0, "d30": 0, "d60": 0, "d90": 0}
    soonest = []
    for contract, client in rows:
        days = (contract.expiry_date - today).days
        if days < 0:
            key = "expired"
        elif days <= 30:
            key = "d30"
        elif days <= 60:
            key = "d60"
        else:
            key = "d90"
        buckets[key] += 1
        if len(soonest) < 10:
            soonest.append({
                "contract_id": contract.id,
                "contract_number": contract.contract_number,
                "client_name": client.name,
                "expiry_date": contract.expiry_date.isoformat(),
                "days_left": days,
                "monthly_rent": float(contract.monthly_rent),
                "bucket": key,
            })
    buckets["total"] = sum(v for k, v in buckets.items() if k != "total")
    return {"buckets": buckets, "soonest": soonest}


def cheque_watch(today: date | None = None) -> dict:
    """PDCs to bank this week, and the ones that came back."""
    today = today or date.today()
    due = cheque_service.due_for_deposit(within_days=7, today=today)
    bounced = cheque_service.bounced(today=today)
    return {
        "due_this_week": {
            "count": len(due),
            "amount": round(sum(float(c.amount) for c in due), 2),
            "cheques": [c.to_dict() for c in due[:10]],
        },
        "bounced": {
            "count": len(bounced),
            "amount": round(sum(float(c.amount) for c in bounced), 2),
            "cheques": [c.to_dict() for c in bounced[:10]],
        },
    }


def summary(month: date | None = None) -> dict:
    period = month_start(month or date.today())
    cache_key = f"dashboard:summary:{period.isoformat()}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    landlords = db.session.query(func.count(Landlord.id)).scalar() or 0
    clients = db.session.query(func.count(Client.id)).scalar() or 0
    active_contracts = (
        db.session.query(func.count(ClientContract.id))
        .filter(ClientContract.status == "active")
        .scalar() or 0
    )
    open_maintenance = (
        db.session.query(func.count(MaintenanceRecord.id))
        .filter(MaintenanceRecord.status == "in_progress")
        .scalar() or 0
    )

    aged = ageing(upto=period)
    pnl = property_pnl(period_month=period)

    result = {
        "month": period.isoformat(),
        "properties": _property_counts(),
        "units": _unit_counts(),
        "landlords": {"total": int(landlords)},
        "clients": {"total": int(clients)},
        "contracts": {"active": int(active_contracts)},
        "collections": collections_summary(month=period),
        "ageing": {
            "total_outstanding": aged["grand_total"],
            "clients_in_arrears": len(aged["rows"]),
            "worst": aged["rows"][:5],
        },
        "pnl": pnl["totals"],
        "contract_expiry": contract_expiry(),
        "agreement_expiry": reminder_summary(),
        "cheques": cheque_watch(),
        "open_maintenance": int(open_maintenance),
        "approvals": pending_counts(),
    }
    cache_set(cache_key, result, _CACHE_TTL)
    return result


def recent_activity(limit: int = 15) -> list[dict]:
    rows = (
        db.session.query(AuditLog, User.username)
        .outerjoin(User, AuditLog.user_id == User.id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    out = []
    for log, username in rows:
        d = log.to_dict()
        d["username"] = username
        out.append(d)
    return out


def _agreement_alert(a: PropertyAgreement, today: date) -> dict:
    return {
        "agreement_id": a.id,
        "property_id": a.property_id,
        "property_name": a.property.name if a.property else None,
        "landlord_name": a.landlord.name if a.landlord else None,
        "expiry_date": a.expiry_date.isoformat(),
        "days_left": (a.expiry_date - today).days,
        "bucket": "expired" if a.expiry_date < today else str((a.expiry_date - today).days),
    }


def alerts() -> dict:
    """Tiered alert-center payload for the Alerts page and bell.

    Rent-due / cheque-bounce tiers join in Phases 3+."""
    today = date.today()
    rows = expiring_agreements(within_days=90, today=today)
    expired, within_7, within_30, within_90 = [], [], [], []
    for a in rows:
        d = _agreement_alert(a, today)
        days = d["days_left"]
        if days < 0:
            expired.append(d)
        elif days <= 7:
            within_7.append(d)
        elif days <= 30:
            within_30.append(d)
        else:
            within_90.append(d)

    maintenance = [
        {
            "id": m.id,
            "transaction_number": m.transaction_number,
            "entity_type": m.entity_type,
            "entity_id": m.entity_id,
            "start_date": m.start_date.isoformat() if m.start_date else None,
            "expected_end_date": m.expected_end_date.isoformat() if m.expected_end_date else None,
            "reason": m.reason,
        }
        for m in MaintenanceRecord.query.filter_by(status="in_progress")
        .order_by(MaintenanceRecord.id.desc()).limit(50).all()
    ]

    # Document expiry (CR / QID) splits across the same tiers.
    docs = expiring_documents(within_days=90, today=today)
    docs_expired = [d for d in docs if d["days_left"] < 0]
    docs_soon = [d for d in docs if 0 <= d["days_left"] <= 30]
    docs_later = [d for d in docs if d["days_left"] > 30]

    critical = {
        "expired_agreements": expired,
        "expiring_within_7_days": within_7,
        "expired_documents": docs_expired,
    }
    warning = {
        "expiring_within_30_days": within_30,
        "documents_expiring_within_30_days": docs_soon,
    }
    info = {
        "expiring_within_90_days": within_90,
        "documents_expiring_within_90_days": docs_later,
        "maintenance_in_progress": maintenance,
    }
    return {
        "critical": critical,
        "warning": warning,
        "info": info,
        "counts": {
            "critical": sum(len(v) for v in critical.values()),
            "warning": sum(len(v) for v in warning.values()),
            "info": sum(len(v) for v in info.values()),
        },
        "approvals": pending_counts(),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def occupancy_by_property(limit: int = 20) -> list[dict]:
    # Short TTL, deliberately much shorter than _CACHE_TTL — this chart is
    # wired to the occupancy SSE channel on the frontend
    # (useEvents("occupancy", ...) invalidates it the instant a unit's
    # status changes), so a long cache would visibly fight that real-time
    # update instead of just adding ordinary staleness.
    cache_key = f"dashboard:occupancy-by-property:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    rows = (
        db.session.query(
            Property.id, Property.code, Property.name,
            func.count(Unit.id).label("total"),
            func.sum(func.cast(Unit.occupancy_status == "occupied", db.Integer)).label("occupied"),
        )
        .outerjoin(Unit, Unit.property_id == Property.id)
        .filter(Property.status == "active")
        .group_by(Property.id, Property.code, Property.name)
        .order_by(func.count(Unit.id).desc())
        .limit(limit)
        .all()
    )
    out = []
    for pid, code, name, total, occupied in rows:
        total = int(total or 0)
        occupied = int(occupied or 0)
        out.append({
            "property_id": pid,
            "code": code,
            "name": name,
            "total_units": total,
            "occupied": occupied,
            "empty": total - occupied,
            "occupancy_percent": round(occupied * 100.0 / total, 1) if total else 0.0,
        })
    cache_set(cache_key, out, 10)
    return out


# ======================================================================
# Entity dashboards
# ======================================================================

def _pnl_trend(property_id: int, upto: date, months: int = 12) -> list[dict]:
    """Month-by-month margin for one property — the workbook's row of
    monthly Profit-Or-Loss figures, as a series."""
    out = []
    for offset in range(months - 1, -1, -1):
        period = add_months(upto, -offset)
        result = property_pnl(period_month=period, property_id=property_id)
        row = result["rows"][0] if result["rows"] else {}
        out.append({
            "month": period.isoformat(),
            "rent_charged": row.get("rent_charged", 0.0),
            "rent_collected": row.get("rent_collected", 0.0),
            "rent_paid": row.get("rent_paid", 0.0),
            "expense_total": row.get("expense_total", 0.0),
            "profit": row.get("profit", 0.0),
        })
    return out


def property_dashboard(property_id: int, month: date | None = None) -> dict:
    """Everything about one property on a single screen — the New-2026
    block for that building, plus its structure and who is in it."""
    prop = Property.query.get(property_id)
    if prop is None:
        raise ValueError("property_id not found")
    period = month_start(month or date.today())

    units = Unit.query.filter_by(property_id=property_id).all()
    by_status: dict[str, int] = {}
    for unit in units:
        by_status[unit.occupancy_status] = by_status.get(unit.occupancy_status, 0) + 1
    occupied = by_status.get("occupied", 0)

    contracts = (
        db.session.query(ClientContract, Client)
        .join(Client, ClientContract.client_id == Client.id)
        .filter(ClientContract.property_id == property_id)
        .filter(ClientContract.status == "active")
        .order_by(ClientContract.contract_number)
        .all()
    )
    today = date.today()
    contract_rows = []
    for contract, client in contracts:
        held = contract.active_allocations(max(today, contract.start_date))
        contract_rows.append({
            "contract_id": contract.id,
            "contract_number": contract.contract_number,
            "client_id": client.id,
            "client_name": client.name,
            "payment_mode": contract.payment_mode,
            "monthly_rent": float(contract.monthly_rent),
            "expiry_date": contract.expiry_date.isoformat(),
            "days_left": (contract.expiry_date - today).days,
            "units": [a.unit.unit_number for a in held if a.unit],
        })

    pnl = property_pnl(period_month=period, property_id=property_id)
    agreement = (
        PropertyAgreement.query
        .filter_by(property_id=property_id, is_active=True)
        .first()
    )

    return {
        "property": prop.to_dict(),
        "landlord": prop.landlord.to_dict() if prop.landlord else None,
        "agreement": agreement.to_dict() if agreement else None,
        "units": {
            "total": len(units),
            "occupied": occupied,
            "empty": by_status.get("empty", 0),
            "by_status": by_status,
            "occupancy_percent": round(occupied * 100.0 / len(units), 1) if units else 0.0,
        },
        "contracts": contract_rows,
        "month": period.isoformat(),
        "pnl": pnl["rows"][0] if pnl["rows"] else None,
        "trend": _pnl_trend(property_id, period),
    }


def client_dashboard(client_id: int, month: date | None = None) -> dict:
    """One tenant: what they hold, what they owe, and how it aged."""
    client = Client.query.get(client_id)
    if client is None:
        raise ValueError("client_id not found")
    period = month_start(month or date.today())

    contracts = (
        db.session.query(ClientContract, Property)
        .join(Property, ClientContract.property_id == Property.id)
        .filter(ClientContract.client_id == client_id)
        .order_by(ClientContract.start_date.desc())
        .all()
    )
    today = date.today()
    rows = []
    for contract, prop in contracts:
        held = contract.active_allocations(max(today, contract.start_date))
        rows.append({
            "contract_id": contract.id,
            "contract_number": contract.contract_number,
            "property_id": prop.id,
            "property_name": prop.name,
            "status": contract.status,
            "payment_mode": contract.payment_mode,
            "monthly_rent": float(contract.monthly_rent),
            "start_date": contract.start_date.isoformat(),
            "expiry_date": contract.expiry_date.isoformat(),
            "days_left": (contract.expiry_date - today).days,
            "units": [a.unit.unit_number for a in held if a.unit],
        })

    aged = ageing(upto=period)
    mine = next((r for r in aged["rows"] if r["client_id"] == client_id), None)

    receipts = (
        Receipt.query
        .filter_by(client_id=client_id, status="posted")
        .order_by(Receipt.receipt_date.desc(), Receipt.id.desc())
        .limit(10).all()
    )
    # "On hand" means still ours to bank or chase: held, with the bank,
    # or returned unpaid. Cleared, replaced and returned cheques are
    # closed and would only pad the list.
    cheques = (
        db.session.query(Cheque)
        .join(ClientContract, Cheque.contract_id == ClientContract.id)
        .filter(ClientContract.client_id == client_id)
        .filter(Cheque.status.in_(("received", "deposited", "bounced")))
        .order_by(Cheque.cheque_date)
        .limit(20).all()
    )

    return {
        "client": client.to_dict(),
        "contracts": rows,
        "active_contracts": sum(1 for r in rows if r["status"] == "active"),
        "outstanding": mine["total"] if mine else 0.0,
        "ageing": mine,
        "recent_receipts": [r.to_dict() for r in receipts],
        "cheques": [c.to_dict() for c in cheques],
        "month": period.isoformat(),
    }


def landlord_dashboard(landlord_id: int, month: date | None = None) -> dict:
    """One owner: their buildings, what we agreed, and what we paid."""
    landlord = Landlord.query.get(landlord_id)
    if landlord is None:
        raise ValueError("landlord_id not found")
    period = month_start(month or date.today())
    today = date.today()

    properties = Property.query.filter_by(landlord_id=landlord_id).order_by(
        Property.name).all()
    agreements = (
        db.session.query(PropertyAgreement, Property)
        .join(Property, PropertyAgreement.property_id == Property.id)
        .filter(PropertyAgreement.landlord_id == landlord_id)
        .filter(PropertyAgreement.is_active.is_(True))
        .order_by(PropertyAgreement.expiry_date)
        .all()
    )
    agreement_rows = [{
        "agreement_id": a.id,
        "property_id": p.id,
        "property_name": p.name,
        "agreement_number": a.agreement_number,
        "start_date": a.start_date.isoformat(),
        "expiry_date": a.expiry_date.isoformat(),
        "days_left": (a.expiry_date - today).days,
        "monthly_rent": float(a.monthly_rent) if a.monthly_rent is not None else None,
        "security_deposit": float(a.security_deposit) if a.security_deposit is not None else None,
        "renewal_status": a.renewal_status,
    } for a, p in agreements]

    statement = landlord_statement(landlord_id)
    committed = sum(r["monthly_rent"] or 0 for r in agreement_rows)

    # What each of their properties earned us this month, so the owner
    # page answers "is this building worth keeping?".
    per_property = []
    for prop in properties:
        result = property_pnl(period_month=period, property_id=prop.id)
        row = result["rows"][0] if result["rows"] else {}
        per_property.append({
            "property_id": prop.id,
            "property_name": prop.name,
            "rent_charged": row.get("rent_charged", 0.0),
            "rent_paid": row.get("rent_paid", 0.0),
            "expense_total": row.get("expense_total", 0.0),
            "profit": row.get("profit", 0.0),
        })

    return {
        "landlord": landlord.to_dict(),
        "properties": [p.to_dict() for p in properties],
        "agreements": agreement_rows,
        "monthly_commitment": round(float(committed), 2),
        "total_paid_to_date": statement["total_paid"],
        "recent_payments": statement["payments"][-10:],
        "month": period.isoformat(),
        "per_property": per_property,
    }


def renewals_at_risk(within_days: int = 60) -> dict:
    """Client contracts, landlord contracts, and generated agreements
    expiring within `within_days` that have no successor yet — the
    "someone needs to act on this soon" list. Reuses the exact
    expiring-soon filter shape from routes/contracts.py and
    services/agreements.py::bulk_renew(), just for display rather than
    action, so the dashboard number and the bulk-renew count can never
    disagree."""
    from .agreements import expiring_generated_agreements
    today = date.today()
    cutoff = today + timedelta(days=within_days)

    client_contracts = (
        ClientContract.query
        .filter(ClientContract.status == "active")
        .filter(ClientContract.expiry_date <= cutoff)
        .order_by(ClientContract.expiry_date.asc())
        .all()
    )
    landlord_contracts = (
        PropertyAgreement.query
        .filter(PropertyAgreement.status == "active")
        .filter(PropertyAgreement.expiry_date <= cutoff)
        .order_by(PropertyAgreement.expiry_date.asc())
        .all()
    )
    agreements = expiring_generated_agreements(within_days=within_days, today=today)

    return {
        "within_days": within_days,
        "client_contracts": [
            {"id": c.id, "contract_number": c.contract_number,
             "client_name": c.client.name if c.client else None,
             "expiry_date": c.expiry_date.isoformat(),
             "days_left": (c.expiry_date - today).days}
            for c in client_contracts
        ],
        "landlord_contracts": [
            {"id": c.id, "property_name": c.property.name if c.property else None,
             "landlord_name": c.landlord.name if c.landlord else None,
             "expiry_date": c.expiry_date.isoformat(),
             "days_left": (c.expiry_date - today).days}
            for c in landlord_contracts
        ],
        "generated_agreements": [
            {"id": a.id, "agreement_number": a.agreement_number,
             "party_role": a.party_role,
             "end_date": a.end_date.isoformat(),
             "days_left": (a.end_date - today).days}
            for a in agreements
        ],
        "total": len(client_contracts) + len(landlord_contracts) + len(agreements),
    }


def cheque_ageing() -> dict:
    """Cheques past their due date and still sitting unresolved (never
    deposited/cleared), plus anything already bounced — bucketed by days
    overdue the same way rent ageing buckets by days late, just applied
    to Cheque instead of RentCharge."""
    today = date.today()
    rows = (
        Cheque.query
        .filter(db.or_(
            Cheque.status == "bounced",
            db.and_(Cheque.status.in_(("received", "deposited")), Cheque.cheque_date < today),
        ))
        .order_by(Cheque.cheque_date.asc())
        .all()
    )
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    out_rows = []
    for c in rows:
        days_overdue = (today - c.cheque_date).days
        bucket = "0-30" if days_overdue <= 30 else "31-60" if days_overdue <= 60 else "61-90" if days_overdue <= 90 else "90+"
        amount = float(c.amount)
        buckets[bucket] += amount
        out_rows.append({
            "id": c.id, "cheque_number": c.cheque_number,
            "amount": amount, "status": c.status,
            "cheque_date": c.cheque_date.isoformat(), "days_overdue": days_overdue,
        })
    return {
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "total": round(sum(buckets.values()), 2),
        "rows": out_rows[:20],
    }
