"""Generated rental-agreement routes — template listing, preview,
generate, list/detail, void and regenerate. Registered with an empty
prefix (mounted straight under `/api/v1`) since it serves two resource
roots: `/agreement-templates` and `/agreements`.
"""
from flask import Blueprint, request

from ..extensions import db
from ..models import Client, GeneratedAgreement, Landlord
from ..services import agreement_templates, agreements as agreements_service
from ..utils.auth import require_permission, current_user
from ..utils.pagination import paginate
from ..utils.responses import success_response, error_response

agreements_bp = Blueprint("agreements", __name__)


def _term_kwargs(payload: dict) -> dict:
    return {
        "landlord": Landlord.query.get(payload.get("landlord_id")) if payload.get("landlord_id") else None,
        "client": Client.query.get(payload.get("client_id")) if payload.get("client_id") else None,
        "party_role": payload.get("party_role"),
        "rooms_description": payload.get("rooms_description"),
        "contract_period_months": payload.get("contract_period_months"),
        "start_date": _to_date(payload.get("start_date")),
        "end_date": _to_date(payload.get("end_date")),
        "electricity_included": bool(payload.get("electricity_included")),
        "water_included": bool(payload.get("water_included")),
        "free_months_count": payload.get("free_months_count"),
        "free_months_mode": payload.get("free_months_mode"),
        "free_months_specific": payload.get("free_months_specific"),
        "deposit_cheque_required": bool(payload.get("deposit_cheque_required")),
        "cancellation_mode": payload.get("cancellation_mode") or "no_cancellation",
        "cancellation_notice_months": payload.get("cancellation_notice_months"),
        "rent_amount": payload.get("rent_amount"),
        "rent_payment_frequency_months": payload.get("rent_payment_frequency_months"),
        "currency": payload.get("currency"),
    }


def _to_date(value):
    from datetime import date, datetime
    if not value:
        raise agreements_service.AgreementError("start_date and end_date are required")
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        raise agreements_service.AgreementError(f"Invalid date: {value}")


@agreements_bp.get("/agreement-templates")
@require_permission("agreement.view")
def list_agreement_templates():
    party_role = request.args.get("party_role")
    return success_response(data=agreement_templates.list_templates(party_role))


@agreements_bp.post("/agreements/preview")
@require_permission("agreement.view")
def preview_agreement():
    payload = request.get_json(silent=True) or {}
    template_slug = payload.get("template_slug")
    if not template_slug:
        return error_response("template_slug is required", 400)
    try:
        kwargs = _term_kwargs(payload)
        clauses = agreements_service.preview(template_slug=template_slug, **kwargs)
    except (agreements_service.AgreementError, KeyError) as exc:
        return error_response(str(exc), 400)
    return success_response(data={"clauses": clauses})


@agreements_bp.post("/agreements")
@require_permission("agreement.create")
def create_agreement():
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    template_slug = payload.get("template_slug")
    if not template_slug:
        return error_response("template_slug is required", 400)

    landlord_id = payload.get("landlord_id")
    client_id = payload.get("client_id")
    party_role = payload.get("party_role")
    try:
        agreement = agreements_service.generate(
            template_slug=template_slug, party_role=party_role,
            landlord_id=landlord_id, client_id=client_id,
            landlord_contract_id=payload.get("landlord_contract_id"),
            client_contract_id=payload.get("client_contract_id"),
            property_id=payload.get("property_id"),
            unit_ids=payload.get("unit_ids"),
            rooms_count=payload.get("rooms_count"),
            rooms_description=payload.get("rooms_description"),
            start_date=payload.get("start_date"), end_date=payload.get("end_date"),
            contract_period_months=payload.get("contract_period_months"),
            electricity_included=bool(payload.get("electricity_included")),
            water_included=bool(payload.get("water_included")),
            free_months_count=payload.get("free_months_count"),
            free_months_mode=payload.get("free_months_mode"),
            free_months_specific=payload.get("free_months_specific"),
            deposit_cheque_required=bool(payload.get("deposit_cheque_required")),
            cancellation_mode=payload.get("cancellation_mode") or "no_cancellation",
            cancellation_notice_months=payload.get("cancellation_notice_months"),
            rent_amount=payload.get("rent_amount"),
            rent_payment_frequency_months=payload.get("rent_payment_frequency_months"),
            currency=payload.get("currency"),
            remarks=payload.get("remarks"),
            actor=actor,
        )
    except (agreements_service.AgreementError, KeyError) as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(
        data=agreement.to_dict(), status=201,
        message=f"Agreement {agreement.agreement_number} generated",
    )


@agreements_bp.get("/agreements")
@require_permission("agreement.view")
def list_agreements():
    query = GeneratedAgreement.query
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id", type=int)
    if entity_type == "landlord" and entity_id:
        query = query.filter_by(landlord_id=entity_id)
    elif entity_type == "client" and entity_id:
        query = query.filter_by(client_id=entity_id)
    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)

    rows, meta = paginate(query.order_by(GeneratedAgreement.created_at.desc()))
    meta["count"] = len(rows)
    return success_response(data=[r.to_dict() for r in rows], meta=meta)


@agreements_bp.get("/agreements/<int:agreement_id>")
@require_permission("agreement.view")
def get_agreement(agreement_id: int):
    agreement = GeneratedAgreement.query.get_or_404(agreement_id)
    data = agreement.to_dict()
    try:
        info = agreement_templates.AGREEMENT_TEMPLATE_REGISTRY[agreement.template_slug]
        context = {
            **(agreement.snapshot_json or {}),
            "rooms_description": agreement.rooms_description,
            "contract_period_months": agreement.contract_period_months,
            "start_date_str": agreement.start_date.strftime("%d/%m/%Y"),
            "end_date_str": agreement.end_date.strftime("%d/%m/%Y"),
            "electricity_included": agreement.electricity_included,
            "water_included": agreement.water_included,
            "free_months_count": agreement.free_months_count or 0,
            "free_months_mode": agreement.free_months_mode,
            "free_months_specific_str": agreement.free_months_specific or "",
            "deposit_cheque_required": agreement.deposit_cheque_required,
            "cancellation_mode": agreement.cancellation_mode,
            "cancellation_notice_months": agreement.cancellation_notice_months,
            "rent_amount": float(agreement.rent_amount or 0),
            "rent_payment_frequency_months": agreement.rent_payment_frequency_months or 1,
            "currency": agreement.currency,
        }
        data["clauses"] = agreement_templates.build_clauses(agreement.template_slug, context)
        data["template_title"] = info["title"]
    except (KeyError, AttributeError):
        data["clauses"] = []
    return success_response(data=data)


@agreements_bp.post("/agreements/<int:agreement_id>/void")
@require_permission("agreement.void")
def void_agreement(agreement_id: int):
    agreement = GeneratedAgreement.query.get_or_404(agreement_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        agreements_service.void(agreement, reason=payload.get("reason") or "", actor=actor)
    except agreements_service.AgreementError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(data=agreement.to_dict(),
                            message=f"Agreement {agreement.agreement_number} voided")


@agreements_bp.post("/agreements/bulk-renew")
@require_permission("agreement.create")
def bulk_renew_agreements():
    payload = request.get_json(silent=True) or {}
    within_days = payload.get("within_days") or 60
    actor = current_user()
    result = agreements_service.bulk_renew(within_days=int(within_days), actor=actor)
    db.session.commit()
    return success_response(
        data=result,
        message=f"{result['renewed_count']} agreement(s) renewed" +
                (f", {result['failed_count']} failed" if result["failed_count"] else ""),
    )


@agreements_bp.post("/agreements/<int:agreement_id>/regenerate")
@require_permission("agreement.create")
def regenerate_agreement(agreement_id: int):
    agreement = GeneratedAgreement.query.get_or_404(agreement_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    overrides = {k: v for k, v in payload.items() if v is not None}
    try:
        new_agreement = agreements_service.regenerate(agreement, actor=actor, **overrides)
    except (agreements_service.AgreementError, KeyError) as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    db.session.commit()
    return success_response(
        data=new_agreement.to_dict(), status=201,
        message=f"Agreement {new_agreement.agreement_number} generated (supersedes "
               f"{agreement.agreement_number})",
    )
