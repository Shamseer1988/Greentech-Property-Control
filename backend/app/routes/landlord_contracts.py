"""Landlord contract routes: list/detail plus the amendment actions
(rent, free months, units, deposit, dates, cancel) — mirrors
`routes/contracts.py` on the client side.

Contract *creation* deliberately stays on the existing
`POST /properties/<id>/agreements` route (`routes/properties.py`); see
`services/landlord_contracts.py`'s module docstring for why.
"""
from datetime import date, timedelta

from flask import Blueprint, request

from ..extensions import db
from ..models import Landlord, LandlordContract, Property
from ..services import audit
from ..services import landlord_contracts as lc_service
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

landlord_contracts_bp = Blueprint("landlord_contracts", __name__)


def _view_date(contract: LandlordContract) -> date:
    """The date a contract's allocations should be read at.

    Today for a contract that has started; its own start date for one
    that hasn't (a future-dated renewal holds nothing *today*, but the
    units it will carry are what the operator wants to see) — mirrors
    `routes/contracts.py`'s `_view_date` on the client side."""
    today = date.today()
    return contract.start_date if contract.start_date > today else today


def _detail(contract: LandlordContract) -> dict:
    data = contract.to_dict()
    on = _view_date(contract)
    data["units"] = [a.to_dict() for a in contract.active_allocations(on)]
    data["units_count"] = len(data["units"])
    data["units_as_of"] = on.isoformat()
    data["amendments"] = [a.to_dict() for a in (contract.amendments or [])]
    return data


@landlord_contracts_bp.get("")
@require_permission("property.view")
def list_landlord_contracts():
    q = (request.args.get("q") or "").strip().lower()
    status = request.args.get("status")
    property_id = request.args.get("property_id", type=int)
    landlord_id = request.args.get("landlord_id", type=int)
    expires_within = request.args.get("expires_within", type=int)

    query = LandlordContract.query
    if status:
        query = query.filter_by(status=status)
    if property_id:
        query = query.filter_by(property_id=property_id)
    if landlord_id:
        query = query.filter_by(landlord_id=landlord_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                db.func.lower(LandlordContract.contract_number).like(like),
                LandlordContract.landlord.has(db.func.lower(Landlord.name).like(like)),
                LandlordContract.property.has(db.func.lower(Property.name).like(like)),
            )
        )
    if expires_within is not None:
        today = date.today()
        if expires_within < 0:
            query = query.filter(LandlordContract.expiry_date < today)
        else:
            query = query.filter(
                LandlordContract.expiry_date >= today,
                LandlordContract.expiry_date <= today + timedelta(days=expires_within),
            )

    rows = query.order_by(LandlordContract.expiry_date.asc()).all()
    today = date.today()
    data = []
    for c in rows:
        d = c.to_dict()
        d["units_count"] = len(c.active_allocations(_view_date(c)))
        d["days_left"] = (c.expiry_date - today).days
        data.append(d)
    return success_response(data=data, meta={"count": len(rows)})


@landlord_contracts_bp.get("/<int:contract_id>")
@require_permission("property.view")
def get_landlord_contract(contract_id: int):
    contract = LandlordContract.query.get_or_404(contract_id)
    return success_response(data=_detail(contract))


def _amend(contract_id: int, handler):
    contract = LandlordContract.query.get_or_404(contract_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        result = handler(contract, payload, actor)
    except lc_service.LandlordContractWarning as warn:
        db.session.rollback()
        return success_response(
            data={"warnings": warn.warnings},
            message="Confirm to proceed — see warnings", status=409)
    except lc_service.LandlordContractError as exc:
        db.session.rollback()
        return error_response(str(exc), 409 if "sourced from another landlord" in str(exc).lower() else 400)
    db.session.commit()
    return result


@landlord_contracts_bp.post("/<int:contract_id>/amendments/rent")
@require_permission("property.amend")
def amend_rent(contract_id: int):
    def handler(contract, payload, actor):
        amendment = lc_service.change_rent(
            contract, new_rent=payload.get("new_rent"),
            effective_date=payload.get("effective_date"),
            reason=payload.get("reason"), remarks=payload.get("remarks"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Rent changed")
    return _amend(contract_id, handler)


@landlord_contracts_bp.post("/<int:contract_id>/amendments/free-months")
@require_permission("property.amend")
def amend_free_months(contract_id: int):
    def handler(contract, payload, actor):
        amendment = lc_service.grant_free_months(
            contract, months=payload.get("months"), from_month=payload.get("from_month"),
            reason=payload.get("reason"), remarks=payload.get("remarks"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Free months recorded")
    return _amend(contract_id, handler)


@landlord_contracts_bp.post("/<int:contract_id>/amendments/add-units")
@require_permission("property.amend")
def amend_add_units(contract_id: int):
    def handler(contract, payload, actor):
        amendment = lc_service.add_units(
            contract, unit_ids=payload.get("unit_ids") or [],
            effective_date=payload.get("effective_date"),
            unit_rent=payload.get("unit_rent"),
            reason=payload.get("reason"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Units added")
    return _amend(contract_id, handler)


@landlord_contracts_bp.post("/<int:contract_id>/amendments/remove-units")
@require_permission("property.amend")
def amend_remove_units(contract_id: int):
    def handler(contract, payload, actor):
        amendment = lc_service.remove_units(
            contract, unit_ids=payload.get("unit_ids") or [],
            effective_date=payload.get("effective_date"),
            reason=payload.get("reason"),
            acknowledge_warnings=bool(payload.get("acknowledge_warnings")),
            actor=actor)
        return success_response(data=amendment.to_dict(), message="Units released")
    return _amend(contract_id, handler)


@landlord_contracts_bp.post("/<int:contract_id>/amendments/deposit")
@require_permission("property.amend")
def amend_deposit(contract_id: int):
    def handler(contract, payload, actor):
        amendment = lc_service.change_deposit(
            contract, new_deposit=payload.get("new_deposit"),
            effective_date=payload.get("effective_date"),
            reason=payload.get("reason"), remarks=payload.get("remarks"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Security deposit updated")
    return _amend(contract_id, handler)


@landlord_contracts_bp.post("/<int:contract_id>/amendments/dates")
@require_permission("property.amend")
def amend_dates(contract_id: int):
    def handler(contract, payload, actor):
        amendment = lc_service.correct_dates(
            contract, new_start_date=payload.get("new_start_date"),
            new_expiry_date=payload.get("new_expiry_date"),
            reason=payload.get("reason"), remarks=payload.get("remarks"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Contract dates corrected")
    return _amend(contract_id, handler)


@landlord_contracts_bp.post("/<int:contract_id>/cancel")
@require_permission("property.cancel")
def cancel_landlord_contract(contract_id: int):
    def handler(contract, payload, actor):
        amendment = lc_service.cancel_contract(
            contract, effective_date=payload.get("effective_date"),
            reason=payload.get("reason"), remarks=payload.get("remarks"), actor=actor)
        return success_response(data=amendment.to_dict(), message="Contract cancelled")
    return _amend(contract_id, handler)
