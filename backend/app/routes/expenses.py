"""Landlord payments, expenses, the P&L import and property-wise P&L."""
from datetime import date, datetime

from flask import Blueprint, request

from ..extensions import db
from ..models import (
    Expense, ExpenseCategory, ExpenseImportBatch, LandlordPayment, LedgerMapping,
)
from ..services import (
    codes, expenses as expense_service, landlord_rent as landlord_rent_service,
    pnl_import as import_service,
)
from ..utils.auth import require_permission, current_user
from ..utils.pagination import paginate
from ..utils.responses import success_response, error_response

expenses_bp = Blueprint("expenses", __name__)

# Parsed files are held here between preview and post so the operator
# doesn't have to upload twice. Keyed by file hash; small and short-lived.
_PREVIEW_CACHE: dict[str, dict] = {}


def _parse(value, field, default=None):
    if not value:
        return default
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD")


# ------------------------------------------------------------ categories

@expenses_bp.get("/categories")
@require_permission("expense.view")
def list_categories():
    query = ExpenseCategory.query
    if request.args.get("active_only") in ("1", "true", "yes"):
        query = query.filter_by(is_active=True)
    query = query.order_by(ExpenseCategory.kind.asc(), ExpenseCategory.name.asc())
    if request.args.get("page") or request.args.get("per_page"):
        rows, meta = paginate(query, default_per_page=25, max_per_page=200)
        return success_response(data=[r.to_dict() for r in rows], meta=meta)
    rows = query.all()
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@expenses_bp.post("/categories")
@require_permission("expense.manage")
def create_category():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip() or codes.next_code(
        ExpenseCategory, codes.prefix_for("expense_category"))
    if not name:
        return error_response("name is required", 400)
    if ExpenseCategory.query.filter(db.func.lower(ExpenseCategory.code) == code.lower()).first():
        return error_response("A category with that code already exists", 409)

    actor = current_user()
    category = ExpenseCategory(
        code=code, name=name,
        kind=(payload.get("kind") or "indirect"),
        is_property_wise=bool(payload.get("is_property_wise", False)),
        created_by=actor.id, updated_by=actor.id,
    )
    db.session.add(category)
    db.session.commit()
    return success_response(data=category.to_dict(), message="Category created", status=201)


@expenses_bp.patch("/categories/<int:category_id>")
@require_permission("expense.manage")
def update_category(category_id: int):
    category = ExpenseCategory.query.get_or_404(category_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        expense_service.update_category(
            category,
            name=payload.get("name"),
            kind=payload.get("kind"),
            is_property_wise=payload.get("is_property_wise"),
            is_active=payload.get("is_active"),
            remarks=payload.get("remarks"),
            actor=actor,
        )
    except expense_service.ExpenseError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=category.to_dict(), message="Category updated")


# -------------------------------------------------------------- expenses

@expenses_bp.get("")
@require_permission("expense.view")
def list_expenses():
    query = Expense.query
    try:
        month = _parse(request.args.get("month"), "month")
    except ValueError as exc:
        return error_response(str(exc), 400)
    property_id = request.args.get("property_id", type=int)
    category_id = request.args.get("category_id", type=int)
    unallocated = request.args.get("unallocated")
    status = request.args.get("status")

    if month:
        query = query.filter(Expense.period_month == month.replace(day=1))
    if property_id:
        query = query.filter(Expense.property_id == property_id)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if unallocated in ("1", "true", "yes"):
        query = query.filter(Expense.property_id.is_(None))
    if status:
        query = query.filter(Expense.status == status)

    # Sum over the full filtered set, not just the current page — pagination
    # must not silently shrink the grand total an operator relies on.
    total_amount = (
        query.filter(Expense.status == "posted")
        .with_entities(db.func.sum(Expense.amount)).scalar()
    ) or 0

    # A month's worth of expenses is small enough (and the page has no
    # pagination controls of its own — a plain month-scoped table) that a
    # generous cap here is the right call rather than building page
    # controls for a view that's always meant to show "this month, in full".
    rows, meta = paginate(query.order_by(Expense.period_month.desc(), Expense.id.desc()),
                          default_per_page=500, max_per_page=1000)
    meta["count"] = len(rows)
    meta["total"] = round(float(total_amount), 2)
    return success_response(data=[r.to_dict() for r in rows], meta=meta)


@expenses_bp.post("")
@require_permission("expense.manage")
def create_expense():
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        expense = expense_service.post_expense(
            category_id=payload.get("category_id"),
            period_month=payload.get("period_month"),
            amount=payload.get("amount"),
            property_id=payload.get("property_id"),
            reference=payload.get("reference"),
            remarks=payload.get("remarks"),
            actor=actor,
        )
    except expense_service.ExpenseError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=expense.to_dict(), message="Expense recorded", status=201)


@expenses_bp.post("/<int:expense_id>/allocate")
@require_permission("expense.manage")
def allocate(expense_id: int):
    expense = Expense.query.get_or_404(expense_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        expense_service.allocate_expense(
            expense, property_id=payload.get("property_id"), actor=actor)
    except expense_service.ExpenseError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=expense.to_dict(), message="Expense allocated")


@expenses_bp.patch("/<int:expense_id>")
@require_permission("expense.manage")
def update_expense(expense_id: int):
    expense = Expense.query.get_or_404(expense_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        expense_service.update_expense(
            expense, remarks=payload.get("remarks"), reference=payload.get("reference"),
            actor=actor)
    except expense_service.ExpenseError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=expense.to_dict(), message="Expense updated")


@expenses_bp.post("/<int:expense_id>/void")
@require_permission("expense.manage")
def void_expense(expense_id: int):
    expense = Expense.query.get_or_404(expense_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        expense_service.void_expense(expense, reason=payload.get("reason"), actor=actor)
    except expense_service.ExpenseError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=expense.to_dict(), message="Expense voided")


# ----------------------------------------------------- landlord payments

@expenses_bp.get("/landlord-payments")
@require_permission("expense.view")
def list_payments():
    query = LandlordPayment.query
    landlord_id = request.args.get("landlord_id", type=int)
    property_id = request.args.get("property_id", type=int)
    status = request.args.get("status")
    try:
        month = _parse(request.args.get("month"), "month")
    except ValueError as exc:
        return error_response(str(exc), 400)
    if landlord_id:
        query = query.filter_by(landlord_id=landlord_id)
    if property_id:
        query = query.filter_by(property_id=property_id)
    if month:
        query = query.filter(LandlordPayment.period_month == month.replace(day=1))
    if status:
        query = query.filter(LandlordPayment.status == status)

    total_amount = (
        query.filter(LandlordPayment.status == "posted")
        .with_entities(db.func.sum(LandlordPayment.amount)).scalar()
    ) or 0

    rows, meta = paginate(query.order_by(LandlordPayment.period_month.desc(),
                                          LandlordPayment.id.desc()),
                          default_per_page=500, max_per_page=1000)
    meta["count"] = len(rows)
    meta["total"] = round(float(total_amount), 2)
    return success_response(data=[r.to_dict() for r in rows], meta=meta)


@expenses_bp.post("/landlord-payments")
@require_permission("expense.manage")
def create_payment():
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        payment = expense_service.post_landlord_payment(
            landlord_id=payload.get("landlord_id"),
            property_id=payload.get("property_id"),
            period_month=payload.get("period_month"),
            amount=payload.get("amount"),
            payment_date=payload.get("payment_date"),
            mode=(payload.get("mode") or "cheque"),
            reference=payload.get("reference"),
            remarks=payload.get("remarks"),
            contract_id=payload.get("contract_id"),
            allocations=payload.get("allocations"),
            actor=actor,
        )
    except expense_service.ExpenseError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=payment.to_dict(),
                            message=f"Voucher {payment.voucher_number} posted", status=201)


@expenses_bp.post("/landlord-payments/<int:payment_id>/void")
@require_permission("expense.manage")
def void_payment(payment_id: int):
    payment = LandlordPayment.query.get_or_404(payment_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        expense_service.void_landlord_payment(
            payment, reason=payload.get("reason") or "", actor=actor)
    except expense_service.ExpenseError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=payment.to_dict(),
                            message=f"Voucher {payment.voucher_number} voided")


@expenses_bp.get("/landlord-statement/<int:landlord_id>")
@require_permission("expense.view")
def landlord_statement(landlord_id: int):
    try:
        data = expense_service.landlord_statement(
            landlord_id,
            from_month=request.args.get("from_month"),
            to_month=request.args.get("to_month"))
    except expense_service.ExpenseError as exc:
        return error_response(str(exc), 404)
    return success_response(data=data)


# ------------------------------------------------------- landlord dues

@expenses_bp.post("/landlord-dues/generate")
@require_permission("expense.manage")
def generate_landlord_dues():
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        upto = _parse(payload.get("upto"), "upto", date.today())
    except ValueError as exc:
        return error_response(str(exc), 400)

    contract_id = payload.get("contract_id")
    if contract_id:
        from ..models import LandlordContract
        contract = LandlordContract.query.get_or_404(contract_id)
        counts = landlord_rent_service.generate_for_contract(contract, upto=upto, actor=actor)
    else:
        counts = landlord_rent_service.generate_all(
            upto=upto, actor=actor, property_id=payload.get("property_id"))
    db.session.commit()
    return success_response(data=counts, message="Landlord dues schedule generated")


@expenses_bp.get("/landlord-charges")
@require_permission("expense.view")
def list_landlord_charges():
    from ..models import LandlordCharge
    query = LandlordCharge.query
    landlord_id = request.args.get("landlord_id", type=int)
    contract_id = request.args.get("contract_id", type=int)
    property_id = request.args.get("property_id", type=int)
    status = request.args.get("status")
    try:
        month = _parse(request.args.get("month"), "month")
    except ValueError as exc:
        return error_response(str(exc), 400)

    if landlord_id:
        query = query.filter_by(landlord_id=landlord_id)
    if contract_id:
        query = query.filter_by(contract_id=contract_id)
    if property_id:
        query = query.filter_by(property_id=property_id)
    if status:
        query = query.filter_by(status=status)
    if month:
        query = query.filter(LandlordCharge.period_month == month.replace(day=1))

    # outstanding() isn't a plain column sum, so the full-set total is
    # computed from every matching row rather than pushed into SQL — cheap
    # at this table's volume, and keeps the one true formula in one place.
    total_due = sum(c.outstanding() for c in query.all())

    rows, meta = paginate(
        query.order_by(LandlordCharge.period_month.desc(), LandlordCharge.id.desc()))
    meta["count"] = len(rows)
    meta["total_due"] = round(total_due, 2)
    return success_response(data=[r.to_dict() for r in rows], meta=meta)


@expenses_bp.get("/landlord-dues/bulk-preview")
@require_permission("expense.view")
def landlord_dues_bulk_preview():
    """Open/part-paid landlord charges within a month range, grouped by
    (landlord, property) — a cheque for one building can't be posted
    against another's arrear, so that pair is the natural row here, same
    as the allocation scope in services/expenses.py."""
    from ..models import LandlordCharge
    try:
        from_month = _parse(request.args.get("from_month"), "from_month")
        to_month = _parse(request.args.get("to_month"), "to_month")
    except ValueError as exc:
        return error_response(str(exc), 400)
    raw_ids = (request.args.get("landlord_ids") or "").strip()
    landlord_ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()] if raw_ids else None

    query = LandlordCharge.query.filter(LandlordCharge.status.in_(("open", "part_paid")))
    if from_month:
        query = query.filter(LandlordCharge.period_month >= from_month.replace(day=1))
    if to_month:
        query = query.filter(LandlordCharge.period_month <= to_month.replace(day=1))
    if landlord_ids:
        query = query.filter(LandlordCharge.landlord_id.in_(landlord_ids))

    rows = query.order_by(LandlordCharge.landlord_id, LandlordCharge.property_id,
                          LandlordCharge.period_month.asc()).all()
    by_pair: dict[tuple[int, int], dict] = {}
    for c in rows:
        key = (c.landlord_id, c.property_id)
        entry = by_pair.setdefault(key, {
            "landlord": {"id": c.landlord.id, "code": c.landlord.code, "name": c.landlord.name}
                       if c.landlord else {"id": c.landlord_id},
            "property": {"id": c.property.id, "code": c.property.code, "name": c.property.name}
                       if c.property else {"id": c.property_id},
            "contract_id": c.contract_id,
            "charges": [], "total_outstanding": 0.0,
        })
        entry["charges"].append(c.to_dict())
        entry["total_outstanding"] = round(entry["total_outstanding"] + c.outstanding(), 2)

    data = sorted(by_pair.values(), key=lambda e: (e["landlord"]["name"], e["property"]["name"]))
    return success_response(
        data=data,
        meta={"count": len(data),
              "total_outstanding": round(sum(e["total_outstanding"] for e in data), 2)},
    )


@expenses_bp.post("/landlord-dues/bulk-post")
@require_permission("expense.manage")
def landlord_dues_bulk_post():
    """One voucher per (landlord, property) pair, mirroring bulk_post_receipts."""
    from ..models import LandlordCharge
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    entries = payload.get("entries") or []
    payment_date = payload.get("payment_date") or date.today().isoformat()
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
        first_charge = LandlordCharge.query.get(allocations[0]["charge_id"])
        period = (first_charge.period_month.isoformat() if first_charge
                 else payload.get("period_month") or payment_date)
        savepoint = db.session.begin_nested()
        try:
            payment = expense_service.post_landlord_payment(
                landlord_id=entry.get("landlord_id"), property_id=entry.get("property_id"),
                period_month=period, amount=total, payment_date=payment_date, mode=mode,
                reference=entry.get("reference"), remarks=entry.get("remarks"),
                contract_id=entry.get("contract_id"), allocations=allocations, actor=actor,
            )
            savepoint.commit()
            posted.append({"landlord_id": entry.get("landlord_id"),
                          "property_id": entry.get("property_id"),
                          "voucher_number": payment.voucher_number, "amount": total})
        except expense_service.ExpenseError as exc:
            savepoint.rollback()
            failed.append({"landlord_id": entry.get("landlord_id"),
                          "property_id": entry.get("property_id"), "error": str(exc)})

    db.session.commit()
    return success_response(
        data={"posted": posted, "failed": failed},
        meta={"posted_count": len(posted), "failed_count": len(failed)},
        message=f"{len(posted)} voucher(s) posted" + (f", {len(failed)} failed" if failed else ""),
        status=201 if posted else 400,
    )


# ---------------------------------------------------------------- import

@expenses_bp.post("/import/preview")
@require_permission("expense.import")
def import_preview():
    if "file" not in request.files:
        return error_response("file is required", 400)
    upload = request.files["file"]
    try:
        parsed = import_service.parse_workbook(upload.stream, original_name=upload.filename or "")
    except import_service.ImportError_ as exc:
        return error_response(str(exc), 400)

    _PREVIEW_CACHE[parsed["file_hash"]] = parsed
    duplicate = import_service.find_duplicate(parsed)
    return success_response(data={
        "file_hash": parsed["file_hash"],
        "original_name": parsed["original_name"],
        "period_from": parsed["period_from"].isoformat(),
        "period_to": parsed["period_to"].isoformat(),
        "period_month": parsed["period_month"].isoformat(),
        "lines": import_service.suggest_mappings(parsed),
        "reconciliation": import_service.reconcile(parsed),
        "duplicate_of": duplicate.batch_number if duplicate else None,
    })


@expenses_bp.post("/import/post")
@require_permission("expense.import")
def import_post():
    payload = request.get_json(silent=True) or {}
    file_hash = payload.get("file_hash")
    parsed = _PREVIEW_CACHE.get(file_hash)
    if parsed is None:
        return error_response(
            "That preview has expired — upload the file again", 400)

    actor = current_user()
    try:
        batch = import_service.post_import(
            parsed,
            mappings={k: int(v) for k, v in (payload.get("mappings") or {}).items() if v},
            allocations={k: int(v) for k, v in (payload.get("allocations") or {}).items() if v},
            force=bool(payload.get("force", False)),
            remarks=payload.get("remarks"),
            actor=actor,
        )
    except import_service.ImportError_ as exc:
        db.session.rollback()
        return error_response(str(exc), 409 if "already imported" in str(exc) else 400)
    db.session.commit()
    _PREVIEW_CACHE.pop(file_hash, None)
    return success_response(data=batch.to_dict(),
                            message=f"{batch.lines_imported} line(s) imported", status=201)


@expenses_bp.get("/import/batches")
@require_permission("expense.view")
def list_batches():
    rows = (ExpenseImportBatch.query
            .order_by(ExpenseImportBatch.id.desc()).limit(100).all())
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@expenses_bp.post("/import/batches/<int:batch_id>/void")
@require_permission("expense.import")
def void_batch(batch_id: int):
    batch = ExpenseImportBatch.query.get_or_404(batch_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        import_service.void_batch(batch, reason=payload.get("reason") or "", actor=actor)
    except import_service.ImportError_ as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=batch.to_dict(),
                            message=f"Batch {batch.batch_number} voided")


@expenses_bp.get("/mappings")
@require_permission("expense.view")
def list_mappings():
    rows = LedgerMapping.query.order_by(LedgerMapping.ledger_name.asc()).all()
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


# -------------------------------------------------------------- P&L

@expenses_bp.get("/pnl")
@require_permission("expense.view")
def property_pnl():
    try:
        month = _parse(request.args.get("month"), "month", date.today())
    except ValueError as exc:
        return error_response(str(exc), 400)
    try:
        data = expense_service.property_pnl(
            period_month=month, property_id=request.args.get("property_id", type=int))
    except expense_service.ExpenseError as exc:
        return error_response(str(exc), 400)
    return success_response(data=data)
