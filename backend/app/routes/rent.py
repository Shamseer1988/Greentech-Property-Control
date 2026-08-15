"""Rent charges, receipts, ageing and statements of account."""
from datetime import date, datetime

from flask import Blueprint, request

from ..extensions import db
from ..models import Client, ClientContract, Receipt, RentCharge
from ..models.landlord_rent import LandlordCharge
from ..services import (
    ageing as ageing_service, approvals as approval_service, audit,
    receipts as receipt_service, rent as rent_service,
)
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

rent_bp = Blueprint("rent", __name__)


def _parse(value, field, default=None):
    if not value:
        return default
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD")


# ------------------------------------------------------------- charges

@rent_bp.post("/generate")
@require_permission("rent.generate")
def generate():
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        upto = _parse(payload.get("upto"), "upto", date.today())
    except ValueError as exc:
        return error_response(str(exc), 400)

    contract_id = payload.get("contract_id")
    if contract_id:
        contract = ClientContract.query.get_or_404(contract_id)
        counts = rent_service.generate_for_contract(contract, upto=upto, actor=actor)
    else:
        counts = rent_service.generate_all(
            upto=upto, actor=actor, property_id=payload.get("property_id"))
    db.session.commit()
    return success_response(data=counts, message="Rent schedule generated")


@rent_bp.get("/charges")
@require_permission("rent.view")
def list_charges():
    query = RentCharge.query
    client_id = request.args.get("client_id", type=int)
    contract_id = request.args.get("contract_id", type=int)
    property_id = request.args.get("property_id", type=int)
    status = request.args.get("status")
    try:
        month = _parse(request.args.get("month"), "month")
    except ValueError as exc:
        return error_response(str(exc), 400)

    if client_id:
        query = query.filter_by(client_id=client_id)
    if contract_id:
        query = query.filter_by(contract_id=contract_id)
    if property_id:
        query = query.filter_by(property_id=property_id)
    if status:
        query = query.filter_by(status=status)
    if month:
        query = query.filter(RentCharge.period_month == rent_service.month_start(month))

    rows = query.order_by(RentCharge.period_month.desc(), RentCharge.id.desc()).limit(1000).all()
    return success_response(
        data=[r.to_dict() for r in rows],
        meta={"count": len(rows),
              "total_due": round(sum(r.outstanding() for r in rows), 2)},
    )


@rent_bp.patch("/charges/<int:charge_id>")
@require_permission("rent.generate")
def amend_charge(charge_id: int):
    charge = RentCharge.query.get_or_404(charge_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()

    old = {"amount": float(charge.amount), "is_free_month": charge.is_free_month,
           "remarks": charge.remarks}

    is_free = payload.get("is_free_month")
    if is_free is True:
        charge.amount = 0
        charge.is_free_month = True
    elif "new_amount" in payload:
        try:
            new_amount = float(payload["new_amount"])
        except (TypeError, ValueError):
            return error_response("new_amount must be a number", 400)
        if new_amount < 0:
            return error_response("new_amount cannot be negative", 400)
        allocated = float(charge.allocated or 0)
        if new_amount < allocated:
            return error_response(
                f"Cannot reduce to {new_amount:.2f} — "
                f"{allocated:.2f} already allocated", 400)
        charge.amount = new_amount
        charge.is_free_month = new_amount == 0

    remarks = (payload.get("remarks") or "").strip()
    if remarks:
        charge.remarks = remarks

    charge.recompute_status()
    audit.record(user=actor, action="amend", module="rent",
                 entity_type="rent_charge", entity_id=charge.id,
                 old_value=old,
                 new_value={"amount": float(charge.amount),
                            "is_free_month": charge.is_free_month,
                            "remarks": charge.remarks})
    db.session.commit()
    return success_response(data=charge.to_dict(), message="Rent charge amended")


@rent_bp.get("/landlord-charges")
@require_permission("rent.view")
def list_landlord_charges():
    query = LandlordCharge.query
    landlord_id = request.args.get("landlord_id", type=int)
    property_id = request.args.get("property_id", type=int)
    contract_id = request.args.get("contract_id", type=int)
    status = request.args.get("status")

    if landlord_id:
        query = query.filter_by(landlord_id=landlord_id)
    if property_id:
        query = query.filter_by(property_id=property_id)
    if contract_id:
        query = query.filter_by(contract_id=contract_id)
    if status:
        query = query.filter_by(status=status)

    rows = query.order_by(LandlordCharge.period_month.desc(),
                          LandlordCharge.id.desc()).limit(1000).all()
    return success_response(
        data=[r.to_dict() for r in rows],
        meta={"count": len(rows)},
    )


@rent_bp.patch("/landlord-charges/<int:charge_id>")
@require_permission("property.amend")
def amend_landlord_charge(charge_id: int):
    charge = LandlordCharge.query.get_or_404(charge_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()

    old = {"amount": float(charge.amount), "is_free_month": charge.is_free_month,
           "remarks": charge.remarks}

    is_free = payload.get("is_free_month")
    if is_free is True:
        charge.amount = 0
        charge.is_free_month = True
    elif "new_amount" in payload:
        try:
            new_amount = float(payload["new_amount"])
        except (TypeError, ValueError):
            return error_response("new_amount must be a number", 400)
        if new_amount < 0:
            return error_response("new_amount cannot be negative", 400)
        allocated = float(charge.allocated or 0)
        if new_amount < allocated:
            return error_response(
                f"Cannot reduce to {new_amount:.2f} — "
                f"{allocated:.2f} already allocated", 400)
        charge.amount = new_amount
        charge.is_free_month = new_amount == 0

    remarks = (payload.get("remarks") or "").strip()
    if remarks:
        charge.remarks = remarks

    charge.recompute_status()
    audit.record(user=actor, action="amend", module="landlord_rent",
                 entity_type="landlord_charge", entity_id=charge.id,
                 old_value=old,
                 new_value={"amount": float(charge.amount),
                            "is_free_month": charge.is_free_month,
                            "remarks": charge.remarks})
    db.session.commit()
    return success_response(data=charge.to_dict(), message="Landlord charge amended")


@rent_bp.get("/bulk-preview")
@require_permission("rent.view")
def bulk_preview():
    """Open/part-paid charges within a month range, grouped by client —
    the grid the bulk entry screen (`/transactions/bulk`) fills in. Each
    charge's `receive_now` defaults to its outstanding balance; the
    operator edits or unticks rows client-side before posting."""
    try:
        from_month = _parse(request.args.get("from_month"), "from_month")
        to_month = _parse(request.args.get("to_month"), "to_month")
    except ValueError as exc:
        return error_response(str(exc), 400)
    raw_ids = (request.args.get("client_ids") or "").strip()
    client_ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()] if raw_ids else None

    query = RentCharge.query.filter(RentCharge.status.in_(("open", "part_paid")))
    if from_month:
        query = query.filter(RentCharge.period_month >= rent_service.month_start(from_month))
    if to_month:
        query = query.filter(RentCharge.period_month <= rent_service.month_start(to_month))
    if client_ids:
        query = query.filter(RentCharge.client_id.in_(client_ids))

    rows = query.order_by(RentCharge.client_id, RentCharge.period_month.asc()).all()
    by_client: dict[int, dict] = {}
    for c in rows:
        entry = by_client.setdefault(c.client_id, {
            "client": {"id": c.client.id, "code": c.client.code, "name": c.client.name}
                      if c.client else {"id": c.client_id},
            "charges": [], "total_outstanding": 0.0,
        })
        entry["charges"].append(c.to_dict())
        entry["total_outstanding"] = round(entry["total_outstanding"] + c.outstanding(), 2)

    data = sorted(by_client.values(), key=lambda e: e["client"]["name"])
    return success_response(
        data=data,
        meta={"count": len(data),
              "total_outstanding": round(sum(e["total_outstanding"] for e in data), 2)},
    )


@rent_bp.post("/bulk-post")
@require_permission("receipt.create")
def bulk_post_receipts():
    """One receipt per client, each carrying explicit allocations across
    the months the operator picked — a thin loop over the same
    `receipts.post_receipt` a single manual entry uses. A failure on one
    client's entry (e.g. a charge someone else just settled) is isolated
    to that entry via a SAVEPOINT so the rest of the batch still posts."""
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    entries = payload.get("entries") or []
    receipt_date = payload.get("receipt_date") or date.today().isoformat()
    mode = (payload.get("mode") or "cash").strip()

    posted, failed = [], []
    for entry in entries:
        allocations = [
            {"charge_id": a.get("charge_id"), "amount": a.get("amount")}
            for a in (entry.get("allocations") or [])
            if a.get("amount") not in (None, "", 0) and float(a.get("amount") or 0) > 0
        ]
        if not allocations:
            continue
        total = round(sum(float(a["amount"]) for a in allocations), 2)
        savepoint = db.session.begin_nested()
        try:
            receipt = receipt_service.post_receipt(
                client_id=entry.get("client_id"), amount=total, receipt_date=receipt_date,
                mode=mode, reference=entry.get("reference"), remarks=entry.get("remarks"),
                allocations=allocations, actor=actor,
            )
            savepoint.commit()
            posted.append({"client_id": entry.get("client_id"),
                          "receipt_number": receipt.receipt_number, "amount": total})
        except receipt_service.ReceiptError as exc:
            savepoint.rollback()
            failed.append({"client_id": entry.get("client_id"), "error": str(exc)})

    db.session.commit()
    return success_response(
        data={"posted": posted, "failed": failed},
        meta={"posted_count": len(posted), "failed_count": len(failed)},
        message=f"{len(posted)} receipt(s) posted" + (f", {len(failed)} failed" if failed else ""),
        status=201 if posted else 400,
    )


@rent_bp.get("/summary")
@require_permission("rent.view")
def summary():
    try:
        month = _parse(request.args.get("month"), "month", date.today())
    except ValueError as exc:
        return error_response(str(exc), 400)
    return success_response(data=receipt_service.collections_summary(month=month))


@rent_bp.get("/cash-due")
@require_permission("rent.view")
def cash_due():
    try:
        period = _parse(request.args.get("month"), "month", date.today())
    except ValueError as exc:
        return error_response(str(exc), 400)
    data = rent_service.cash_due_booking(period=period)
    return success_response(data=data, meta={"count": data["count"]})


@rent_bp.get("/outstanding")
@require_permission("rent.view")
def outstanding():
    try:
        upto = _parse(request.args.get("upto"), "upto", date.today())
    except ValueError as exc:
        return error_response(str(exc), 400)
    rows = ageing_service.outstanding_by_client(upto=upto)
    return success_response(
        data=rows,
        meta={"count": len(rows),
              "total": round(sum(r["outstanding"] for r in rows), 2)},
    )


# ------------------------------------------------------------ receipts

@rent_bp.get("/receipts")
@require_permission("receipt.view")
def list_receipts():
    query = Receipt.query
    client_id = request.args.get("client_id", type=int)
    status = request.args.get("status")
    if client_id:
        query = query.filter_by(client_id=client_id)
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(Receipt.receipt_date.desc(), Receipt.id.desc()).limit(500).all()
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@rent_bp.get("/receipts/<int:receipt_id>")
@require_permission("receipt.view")
def get_receipt(receipt_id: int):
    receipt = Receipt.query.get_or_404(receipt_id)
    data = receipt.to_dict()
    data["allocations"] = [a.to_dict() for a in (receipt.allocations or [])]
    return success_response(data=data)


@rent_bp.post("/receipts")
@require_permission("receipt.create")
def post_receipt():
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        receipt = receipt_service.post_receipt(
            client_id=payload.get("client_id"),
            amount=payload.get("amount"),
            receipt_date=payload.get("receipt_date") or date.today().isoformat(),
            mode=(payload.get("mode") or "").strip(),
            reference=payload.get("reference"),
            remarks=payload.get("remarks"),
            allocations=payload.get("allocations"),
            actor=actor,
        )
    except receipt_service.ReceiptError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()

    data = receipt.to_dict()
    data["allocations"] = [a.to_dict() for a in (receipt.allocations or [])]
    return success_response(data=data, message=f"Receipt {receipt.receipt_number} posted",
                            status=201)


@rent_bp.post("/receipts/<int:receipt_id>/void")
@require_permission("receipt.void")
def void_receipt(receipt_id: int):
    receipt = Receipt.query.get_or_404(receipt_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    reason = payload.get("reason") or ""

    if approval_service.is_required("receipt_void"):
        # The receipt stays posted and its allocations stay attached
        # until an approver agrees; the money on the books does not move
        # on the strength of a request alone.
        if receipt.status == "voided":
            return error_response(
                f"Receipt {receipt.receipt_number} is already voided", 400)
        if not reason.strip():
            return error_response("reason is required to void a receipt", 400)
        try:
            req = approval_service.create_request(
                module="receipt_void", entity=receipt, actor_id=actor.id,
                payload={"reason": reason},
                summary=(f"Void receipt {receipt.receipt_number} for "
                         f"{float(receipt.amount):,.2f} — {reason}"),
            )
        except approval_service.ApprovalError as exc:
            db.session.rollback()
            return error_response(str(exc), 409)
        audit.record(user=actor, action="request", module="approval",
                     entity_type="approval_request", entity_id=req.id,
                     new_value=req.to_dict(), remarks=req.summary)
        db.session.commit()
        return success_response(
            data=req.to_dict(), status=202,
            message=(f"Sent for approval as {req.transaction_number}. "
                     "The receipt is still posted."))

    try:
        receipt_service.void_receipt(receipt, reason=reason, actor=actor)
    except receipt_service.ReceiptError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=receipt.to_dict(),
                            message=f"Receipt {receipt.receipt_number} voided")


# ----------------------------------------------------- ageing + statement

@rent_bp.get("/ageing")
@require_permission("rent.view")
def ageing():
    try:
        upto = _parse(request.args.get("upto"), "upto", date.today())
    except ValueError as exc:
        return error_response(str(exc), 400)
    months = min(request.args.get("months", default=12, type=int), 36)
    return success_response(data=ageing_service.ageing(
        upto=upto, months=months, property_id=request.args.get("property_id", type=int)))


@rent_bp.get("/statement/<int:client_id>")
@require_permission("rent.view")
def statement(client_id: int):
    try:
        from_date = _parse(request.args.get("from_date"), "from_date")
        to_date = _parse(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error_response(str(exc), 400)
    try:
        data = ageing_service.statement_of_account(
            client_id, from_date=from_date, to_date=to_date)
    except ValueError as exc:
        return error_response(str(exc), 404)
    return success_response(data=data)
