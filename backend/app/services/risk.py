"""Client risk scoring — a read/report concern, not an operational
attribute the rest of the system depends on (same reasoning as
GeneratedAgreement's standalone-snapshot design: this is a point-in-time
assessment, computed on demand and cached, not a column anything else
joins against).

Three signals, each already available elsewhere in the codebase rather
than computed fresh:
  * ageing — services/ageing.py::outstanding_by_client() already
    computes days_overdue per client.
  * bounced cheques — ChequeEvent rows with event_type == "bounced",
    over the trailing 12 months, joined through Cheque -> ClientContract
    to reach client_id (Cheque has no client_id column of its own).
  * late payments — a receipt that settled a charge after that charge's
    period_month ended. Computed in Python from the raw rows (matching
    outstanding_by_client()'s own convention of computing days_overdue
    in Python rather than in SQL) rather than pushing date arithmetic
    into SQL, since the test suite runs on SQLite where Postgres date
    arithmetic wouldn't work the same way.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..extensions import db
from ..models import Cheque, ChequeEvent, Client, ClientContract, Receipt, ReceiptAllocation, RentCharge
from .ageing import outstanding_by_client
from .cache import cache_get, cache_set
from .rent import month_end

_CACHE_TTL = 6 * 3600
_TRAILING_DAYS = 365

# Score weights — ageing dominates (it's today's actual exposure), the
# other two are frequency signals over the trailing year.
_WEIGHT_DAYS_OVERDUE = 1.0
_WEIGHT_BOUNCED_CHEQUE = 15.0
_WEIGHT_LATE_PAYMENT = 5.0

_TIER_HIGH = 60
_TIER_MEDIUM = 20


def _bounced_cheque_counts(since: date) -> dict[int, int]:
    rows = (
        db.session.query(ClientContract.client_id, db.func.count(ChequeEvent.id))
        .select_from(ChequeEvent)
        .join(Cheque, ChequeEvent.cheque_id == Cheque.id)
        .join(ClientContract, Cheque.contract_id == ClientContract.id)
        .filter(ChequeEvent.event_type == "bounced")
        .filter(ChequeEvent.event_date >= since)
        .group_by(ClientContract.client_id)
        .all()
    )
    return {client_id: int(count) for client_id, count in rows}


def _late_payment_counts(since: date) -> dict[int, int]:
    rows = (
        db.session.query(
            RentCharge.client_id, Receipt.receipt_date, RentCharge.period_month)
        .select_from(ReceiptAllocation)
        .join(Receipt, ReceiptAllocation.receipt_id == Receipt.id)
        .join(RentCharge, ReceiptAllocation.charge_id == RentCharge.id)
        .filter(Receipt.status == "posted")
        .filter(Receipt.receipt_date >= since)
        .all()
    )
    counts: dict[int, int] = {}
    for client_id, receipt_date, period_month in rows:
        if receipt_date > month_end(period_month):
            counts[client_id] = counts.get(client_id, 0) + 1
    return counts


def _tier(score: float) -> str:
    if score >= _TIER_HIGH:
        return "high"
    if score >= _TIER_MEDIUM:
        return "medium"
    return "low"


def client_risk_report(*, as_of: date | None = None) -> list[dict]:
    """Every client with any outstanding balance, ranked by risk score
    descending. Clients with nothing owing and a clean cheque/payment
    history simply don't appear — there's nothing to assess."""
    as_of = as_of or date.today()
    cache_key = f"risk:client_report:{as_of.isoformat()}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    since = as_of - timedelta(days=_TRAILING_DAYS)
    ageing_rows = outstanding_by_client(upto=as_of)
    bounced = _bounced_cheque_counts(since)
    late = _late_payment_counts(since)

    # Clients with no outstanding balance but a bounce/late-payment
    # history in the window still deserve a line — they're the ones
    # about to become a problem, not already one.
    client_ids = {r["client_id"] for r in ageing_rows} | set(bounced) | set(late)
    if not client_ids:
        return []
    ageing_by_client = {r["client_id"]: r for r in ageing_rows}
    names = {c.id: c for c in Client.query.filter(Client.id.in_(client_ids)).all()}

    out = []
    for client_id in client_ids:
        client = names.get(client_id)
        if client is None:
            continue
        ageing = ageing_by_client.get(client_id, {})
        days_overdue = ageing.get("days_overdue", 0)
        bounced_count = bounced.get(client_id, 0)
        late_count = late.get(client_id, 0)
        score = round(
            days_overdue * _WEIGHT_DAYS_OVERDUE
            + bounced_count * _WEIGHT_BOUNCED_CHEQUE
            + late_count * _WEIGHT_LATE_PAYMENT, 1)
        out.append({
            "client_id": client_id,
            "client_code": client.code,
            "client_name": client.name,
            "outstanding": ageing.get("outstanding", 0.0),
            "days_overdue": days_overdue,
            "bounced_cheques_12m": bounced_count,
            "late_payments_12m": late_count,
            "score": score,
            "tier": _tier(score),
        })

    out.sort(key=lambda r: r["score"], reverse=True)
    cache_set(cache_key, out, _CACHE_TTL)
    return out
