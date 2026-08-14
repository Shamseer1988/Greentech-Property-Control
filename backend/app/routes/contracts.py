"""Client contract routes: the contract itself, its amendments and its PDC book."""
from datetime import date, timedelta

from flask import Blueprint, request

from ..extensions import db
from ..models import Cheque, Client, ClientContract, ContractUnit, Property, Unit
from ..services import (audit, approvals as approval_service,
                        contracts as contract_service, cheques as cheque_service)
from ..utils.auth import require_permission, current_user
from ..utils.pagination import paginate
from ..utils.responses import success_response, error_response

contracts_bp = Blueprint("contracts", __name__)


def _publish_occupancy(event: dict) -> None:
    """Best-effort SSE publish so open floor maps update live."""
    try:
        from ..services import events as event_service
        event_service.publish("occupancy", event)
    except Exception:
        pass


def _view_date(contract: ClientContract) -> date:
    """The date a contract's allocations should be read at.

    Today for a contract that has started; its own start date for one
    that hasn't (a future-dated renewal holds nothing *today*, but the
    units it will carry are what the operator wants to see)."""
    today = date.today()
    return max(today, contract.start_date) if contract.start_date > today else today


def _detail(contract: ClientContract, *, on: date | None = None) -> dict:
    data = contract.to_dict()
    on = on or _view_date(contract)
    data["units"] = [a.to_dict() for a in contract.active_allocations(on)]
    data["units_count"] = len(data["units"])
    data["units_as_of"] = on.isoformat()
    data["amendments"] = [a.to_dict() for a in (contract.amendments or [])]
    data["cheques"] = [c.to_dict() for c in (contract.cheques or [])]
    # A queued change hasn't touched the contract, so without this the
    # page would show the old rent with no hint that a reduction is
    # sitting in someone's approval queue.
    data["pending_approvals"] = [
        r.to_dict() for r in approval_service.pending_for_contract(contract.id)
    ]
    return data


# ----------------------------------------------------------------- list

@contracts_bp.get("")
@require_permission("contract.view")
def list_contracts():
    q = (request.args.get("q") or "").strip().lower()
    status = request.args.get("status")
    mode = request.args.get("mode")
    client_id = request.args.get("client_id", type=int)
    property_id = request.args.get("property_id", type=int)
    expires_within = request.args.get("expires_within", type=int)

    query = ClientContract.query
    if status:
        query = query.filter_by(status=status)
    if mode:
        query = query.filter_by(payment_mode=mode)
    if client_id:
        query = query.filter_by(client_id=client_id)
    if property_id:
        query = query.filter_by(property_id=property_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                db.func.lower(ClientContract.contract_number).like(like),
                ClientContract.client.has(db.func.lower(Client.name).like(like)),
                ClientContract.property.has(db.func.lower(Property.name).like(like)),
            )
        )
    if expires_within is not None:
        today = date.today()
        if expires_within < 0:
            query = query.filter(ClientContract.expiry_date < today)
        else:
            query = query.filter(
                ClientContract.expiry_date >= today,
                ClientContract.expiry_date <= today + timedelta(days=expires_within),
            )

    rows, meta = paginate(query.order_by(ClientContract.expiry_date.asc()))
    today = date.today()
    data = []
    for c in rows:
        d = c.to_dict()
        d["units_count"] = len(c.active_allocations(_view_date(c)))
        d["days_left"] = (c.expiry_date - today).days
        data.append(d)
    meta["count"] = len(rows)
    return success_response(data=data, meta=meta)


@contracts_bp.get("/<int:contract_id>")
@require_permission("contract.view")
def get_contract(contract_id: int):
    return success_response(data=_detail(ClientContract.query.get_or_404(contract_id)))


@contracts_bp.get("/expiring")
@require_permission("contract.view")
def expiring_contracts():
    days = request.args.get("days", default=90, type=int)
    today = date.today()
    from datetime import timedelta
    rows = (
        ClientContract.query
        .filter(ClientContract.status == "active")
        .filter(ClientContract.expiry_date <= today + timedelta(days=days))
        .order_by(ClientContract.expiry_date.asc())
        .all()
    )
    out = []
    for c in rows:
        d = c.to_dict()
        d["days_left"] = (c.expiry_date - today).days
        out.append(d)
    return success_response(data=out, meta={"count": len(out), "within_days": days})


# --------------------------------------------------------------- create

@contracts_bp.post("")
@require_permission("contract.create")
def create_contract():
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        contract = contract_service.create_contract(
            client_id=payload.get("client_id"),
            property_id=payload.get("property_id"),
            unit_ids=payload.get("unit_ids") or [],
            start_date=payload.get("start_date"),
            expiry_date=payload.get("expiry_date"),
            monthly_rent=payload.get("monthly_rent"),
            payment_mode=(payload.get("payment_mode") or "").strip(),
            security_deposit=payload.get("security_deposit"),
            opening_balance=payload.get("opening_balance") or 0,
            remarks=payload.get("remarks"),
            actor=actor,
        )
    except contract_service.ContractError as exc:
        db.session.rollback()
        return error_response(str(exc), 409 if "occupied" in str(exc).lower() else 400)

    db.session.commit()
    _publish_occupancy({"type": "contract.created", "property_id": contract.property_id})
    return success_response(data=_detail(contract), message="Contract created", status=201)


@contracts_bp.get("/available-units")
@require_permission("contract.view")
def available_units():
    """Units in a property that are free on a given date — feeds the picker."""
    property_id = request.args.get("property_id", type=int)
    if not property_id:
        return error_response("property_id is required", 400)
    on_raw = request.args.get("on")
    try:
        on = contract_service._parse_date(on_raw, "on") if on_raw else date.today()
    except contract_service.ContractError as exc:
        return error_response(str(exc), 400)

    units = (
        Unit.query.filter_by(property_id=property_id)
        .order_by(Unit.floor_id.asc(), Unit.unit_number.asc())
        .all()
    )
    held = contract_service.units_held_on([u.id for u in units], on)
    out = []
    for u in units:
        holder = held.get(u.id)
        d = u.to_dict()
        d["is_available"] = (
            holder is None
            and u.occupancy_status not in ("maintenance", "blocked")
            and not (u.is_facility() and u.is_shared_facility)
        )
        d["held_by"] = (
            {"contract_id": holder.id, "contract_number": holder.contract_number,
             "client_name": holder.client.name if holder.client else None}
            if holder else None
        )
        out.append(d)
    return success_response(
        data=out,
        meta={"count": len(out), "available": sum(1 for d in out if d["is_available"]),
              "on": on.isoformat()},
    )


# ------------------------------------------------------------ amendments

def _amend(contract_id: int, handler, *, permission_checked=True):
    contract = ClientContract.query.get_or_404(contract_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        result = handler(contract, payload, actor)
    except contract_service.ContractError as exc:
        db.session.rollback()
        return error_response(str(exc), 409 if "occupied" in str(exc).lower() else 400)
    except approval_service.ApprovalError as exc:
        db.session.rollback()
        return error_response(str(exc), 409)
    db.session.commit()
    _publish_occupancy({"type": "contract.amended", "property_id": contract.property_id})
    return result


def _is_reduction(new_rent, current_rent) -> bool:
    try:
        return float(new_rent) < float(current_rent)
    except (TypeError, ValueError):
        return False


def _queue(contract, *, module: str, summary: str, args: dict, actor):
    """Park an action in the approval queue instead of applying it.

    Answers 202 — the request was accepted, but deliberately nothing on
    the contract has changed yet. `args` is replayed verbatim through the
    same service call when an approver says yes.
    """
    # The same precondition the service would apply, checked now so an
    # impossible request is refused at the desk rather than queued.
    contract_service.require_active(contract)
    req = approval_service.create_request(
        module=module, entity=contract, actor_id=actor.id,
        summary=summary, payload=args,
    )
    audit.record(user=actor, action="request", module="approval",
                 entity_type="approval_request", entity_id=req.id,
                 new_value=req.to_dict(), remarks=summary)
    return success_response(
        data=req.to_dict(), status=202,
        message=f"Sent for approval as {req.transaction_number}. "
                "Nothing has changed on the contract yet.",
    )


@contracts_bp.post("/<int:contract_id>/amendments/rent")
@require_permission("contract.amend")
def amend_rent(contract_id: int):
    def handler(contract, payload, actor):
        args = {
            "new_rent": payload.get("new_rent"),
            "effective_date": payload.get("effective_date"),
            "reason": payload.get("reason"),
            "remarks": payload.get("remarks"),
        }
        # Only a reduction is gated — an increase costs the company
        # nothing and holding it up would just delay billing. A rent
        # that won't parse as a number falls through to change_rent,
        # which raises the proper validation error.
        if _is_reduction(args["new_rent"], contract.monthly_rent) \
                and approval_service.is_required("rent_reduction"):
            return _queue(
                contract, module="rent_reduction", args=args, actor=actor,
                summary=(f"Reduce rent on {contract.contract_number} from "
                         f"{float(contract.monthly_rent):,.2f} to "
                         f"{float(args['new_rent']):,.2f} with effect from "
                         f"{args['effective_date']}"),
            )
        amendment = contract_service.change_rent(contract, actor=actor, **args)
        return success_response(data=amendment.to_dict(), message="Rent amended")
    return _amend(contract_id, handler)


@contracts_bp.post("/<int:contract_id>/amendments/free-months")
@require_permission("contract.amend")
def amend_free_months(contract_id: int):
    def handler(contract, payload, actor):
        amendment = contract_service.grant_free_months(
            contract, months=payload.get("months"),
            from_month=payload.get("from_month"),
            reason=payload.get("reason"), remarks=payload.get("remarks"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Free months granted")
    return _amend(contract_id, handler)


@contracts_bp.post("/<int:contract_id>/amendments/add-units")
@require_permission("contract.amend")
def amend_add_units(contract_id: int):
    def handler(contract, payload, actor):
        amendment = contract_service.add_units(
            contract, unit_ids=payload.get("unit_ids") or [],
            effective_date=payload.get("effective_date"),
            reason=payload.get("reason"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Units added")
    return _amend(contract_id, handler)


@contracts_bp.post("/<int:contract_id>/amendments/remove-units")
@require_permission("contract.amend")
def amend_remove_units(contract_id: int):
    def handler(contract, payload, actor):
        amendment = contract_service.remove_units(
            contract, unit_ids=payload.get("unit_ids") or [],
            effective_date=payload.get("effective_date"),
            reason=payload.get("reason"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Units released")
    return _amend(contract_id, handler)


@contracts_bp.post("/<int:contract_id>/amendments/dates")
@require_permission("contract.amend")
def amend_dates(contract_id: int):
    def handler(contract, payload, actor):
        amendment = contract_service.correct_dates(
            contract, new_start_date=payload.get("new_start_date"),
            new_expiry_date=payload.get("new_expiry_date"),
            reason=payload.get("reason"), remarks=payload.get("remarks"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Contract dates corrected")
    return _amend(contract_id, handler)


@contracts_bp.post("/<int:contract_id>/cancel")
@require_permission("contract.cancel")
def cancel_contract(contract_id: int):
    def handler(contract, payload, actor):
        args = {
            "effective_date": payload.get("effective_date"),
            "reason": payload.get("reason") or "",
            "remarks": payload.get("remarks"),
        }
        if approval_service.is_required("contract_cancellation"):
            if not args["reason"].strip():
                raise contract_service.ContractError(
                    "reason is required to cancel a contract")
            return _queue(
                contract, module="contract_cancellation", args=args, actor=actor,
                summary=(f"Cancel {contract.contract_number} with effect from "
                         f"{args['effective_date']} — {args['reason']}"),
            )
        amendment = contract_service.cancel_contract(contract, actor=actor, **args)
        return success_response(data=amendment.to_dict(), message="Contract cancelled")
    return _amend(contract_id, handler)


@contracts_bp.post("/<int:contract_id>/renew")
@require_permission("contract.create")
def renew_contract(contract_id: int):
    def handler(contract, payload, actor):
        renewal = contract_service.renew_contract(
            contract,
            new_start_date=payload.get("new_start_date"),
            new_expiry_date=payload.get("new_expiry_date"),
            new_monthly_rent=payload.get("new_monthly_rent"),
            remarks=payload.get("remarks"), actor=actor)
        return success_response(data=_detail(renewal), message="Contract renewed", status=201)
    return _amend(contract_id, handler)


# --------------------------------------------------------------- cheques

@contracts_bp.get("/cheques")
@require_permission("contract.view")
def list_all_cheques():
    """Cheques across a client's contracts — feeds the receipt dialog's
    "pick a cheque on file" picker (a client may hold cheques on more
    than one contract) and any due-for-deposit worklist."""
    query = Cheque.query.join(ClientContract, Cheque.contract_id == ClientContract.id)
    client_id = request.args.get("client_id", type=int)
    status = request.args.get("status")
    if client_id:
        query = query.filter(ClientContract.client_id == client_id)
    if status:
        query = query.filter(Cheque.status == status)
    rows = query.order_by(Cheque.cheque_date.asc()).all()
    data = []
    for c in rows:
        d = c.to_dict()
        d["contract_number"] = c.contract.contract_number if c.contract else None
        data.append(d)
    return success_response(data=data, meta={"count": len(data)})


@contracts_bp.get("/<int:contract_id>/cheques")
@require_permission("contract.view")
def list_cheques(contract_id: int):
    contract = ClientContract.query.get_or_404(contract_id)
    rows = sorted(contract.cheques or [], key=lambda c: (c.is_security, c.cheque_date))
    return success_response(data=[c.to_dict() for c in rows], meta={"count": len(rows)})


@contracts_bp.get("/<int:contract_id>/cheques/preview")
@require_permission("contract.view")
def preview_cheques(contract_id: int):
    contract = ClientContract.query.get_or_404(contract_id)
    count = request.args.get("count", default=12, type=int)
    try:
        rows = cheque_service.build_schedule_preview(
            contract, count=count, start_date=request.args.get("start_date"),
            amount=request.args.get("amount"))
    except cheque_service.ChequeError as exc:
        return error_response(str(exc), 400)
    return success_response(data=rows, meta={"count": len(rows)})


@contracts_bp.post("/<int:contract_id>/cheques")
@require_permission("cheque.manage")
def create_cheques(contract_id: int):
    contract = ClientContract.query.get_or_404(contract_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        created = cheque_service.generate_schedule(
            contract, cheques=payload.get("cheques") or [],
            security=payload.get("security"), actor=actor)
    except cheque_service.ChequeError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=[c.to_dict() for c in created],
                            message=f"{len(created)} cheque(s) registered", status=201)


def _cheque_action(cheque_id: int, handler):
    cheque = Cheque.query.get_or_404(cheque_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        result = handler(cheque, payload, actor)
    except cheque_service.ChequeError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return result


@contracts_bp.post("/cheques/<int:cheque_id>/deposit")
@require_permission("cheque.manage")
def deposit_cheque(cheque_id: int):
    return _cheque_action(cheque_id, lambda c, p, a: success_response(
        data=cheque_service.deposit(c, when=p.get("when"),
                                    bank_reference=p.get("bank_reference"), actor=a).to_dict(),
        message="Cheque deposited"))


@contracts_bp.post("/cheques/<int:cheque_id>/clear")
@require_permission("cheque.manage")
def clear_cheque(cheque_id: int):
    return _cheque_action(cheque_id, lambda c, p, a: success_response(
        data=cheque_service.clear(c, when=p.get("when"),
                                  bank_reference=p.get("bank_reference"), actor=a).to_dict(),
        message="Cheque cleared"))


@contracts_bp.post("/cheques/<int:cheque_id>/bounce")
@require_permission("cheque.manage")
def bounce_cheque(cheque_id: int):
    return _cheque_action(cheque_id, lambda c, p, a: success_response(
        data=cheque_service.bounce(c, reason=p.get("reason") or "",
                                   when=p.get("when"), actor=a).to_dict(),
        message="Cheque marked bounced"))


@contracts_bp.post("/cheques/<int:cheque_id>/return")
@require_permission("cheque.manage")
def return_cheque(cheque_id: int):
    return _cheque_action(cheque_id, lambda c, p, a: success_response(
        data=cheque_service.return_cheque(c, when=p.get("when"),
                                          remarks=p.get("remarks"), actor=a).to_dict(),
        message="Cheque returned"))


@contracts_bp.post("/cheques/<int:cheque_id>/replace")
@require_permission("cheque.manage")
def replace_cheque(cheque_id: int):
    return _cheque_action(cheque_id, lambda c, p, a: success_response(
        data=cheque_service.replace(
            c, cheque_number=p.get("cheque_number"), cheque_date=p.get("cheque_date"),
            amount=p.get("amount"), bank_name=p.get("bank_name"),
            remarks=p.get("remarks"), actor=a).to_dict(),
        message="Replacement cheque registered", status=201))


@contracts_bp.get("/cheques/<int:cheque_id>")
@require_permission("contract.view")
def get_cheque(cheque_id: int):
    cheque = Cheque.query.get_or_404(cheque_id)
    data = cheque.to_dict()
    data["events"] = [e.to_dict() for e in (cheque.events or [])]
    return success_response(data=data)
