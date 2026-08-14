from flask import Blueprint, request

from ..extensions import db
from ..models import ApprovalRequest
from ..services import audit, approvals as approval_service
from ..services.renewals import RenewalError
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

approvals_bp = Blueprint("approvals", __name__)


@approvals_bp.get("")
@require_permission("approval.approve")
def list_approvals():
    status = request.args.get("status", "pending")
    module = request.args.get("module")
    rows = approval_service.list_requests(status=status or None, module=module)
    return success_response(
        data=[r.to_dict() for r in rows],
        meta={"count": len(rows), "pending_counts": approval_service.pending_counts()},
    )


@approvals_bp.get("/counts")
@require_permission("approval.approve")
def pending_counts():
    return success_response(data=approval_service.pending_counts())


@approvals_bp.get("/<int:req_id>")
@require_permission("approval.approve")
def get_approval(req_id: int):
    return success_response(data=ApprovalRequest.query.get_or_404(req_id).to_dict())


@approvals_bp.post("/<int:req_id>/approve")
@require_permission("approval.approve")
def approve(req_id: int):
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        req = approval_service.approve(
            request_id=req_id, actor_id=actor.id, remarks=payload.get("remarks"),
        )
    except (approval_service.ApprovalError, RenewalError) as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    audit.record(user=actor, action="approve", module="approval",
                 entity_type="approval_request", entity_id=req.id,
                 new_value=req.to_dict(), remarks=req.transaction_number)
    db.session.commit()
    return success_response(data=req.to_dict(), message="Approved")


@approvals_bp.post("/<int:req_id>/reject")
@require_permission("approval.reject")
def reject(req_id: int):
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    try:
        req = approval_service.reject(
            request_id=req_id, actor_id=actor.id, remarks=payload.get("remarks"),
        )
    except approval_service.ApprovalError as exc:
        db.session.rollback()
        return error_response(str(exc), 400)
    audit.record(user=actor, action="reject", module="approval",
                 entity_type="approval_request", entity_id=req.id,
                 new_value=req.to_dict(), remarks=req.transaction_number)
    db.session.commit()
    return success_response(data=req.to_dict(), message="Rejected")
