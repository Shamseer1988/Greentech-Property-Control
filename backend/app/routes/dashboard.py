from datetime import datetime

from flask import Blueprint, request

from ..services import dashboard, cashflow as cashflow_service
from ..utils.auth import require_permission
from ..utils.responses import success_response, error_response

dashboard_bp = Blueprint("dashboard", __name__)


def _month_arg():
    """?month=YYYY-MM-DD (or YYYY-MM) — defaults to the current month."""
    raw = request.args.get("month")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw if len(raw) > 7 else f"{raw}-01").date()
    except ValueError:
        raise ValueError("month must be YYYY-MM or YYYY-MM-DD")


@dashboard_bp.get("/summary")
@require_permission("dashboard.view")
def summary():
    try:
        month = _month_arg()
    except ValueError as exc:
        return error_response(str(exc), 400)
    return success_response(data=dashboard.summary(month=month))


@dashboard_bp.get("/activity")
@require_permission("dashboard.view")
def activity():
    limit = min(request.args.get("limit", default=15, type=int), 100)
    return success_response(data=dashboard.recent_activity(limit=limit))


@dashboard_bp.get("/alerts")
@require_permission("dashboard.view")
def alerts():
    return success_response(data=dashboard.alerts())


@dashboard_bp.get("/charts/occupancy-by-property")
@require_permission("dashboard.view")
def occupancy_by_property():
    limit = min(request.args.get("limit", default=20, type=int), 100)
    return success_response(data=dashboard.occupancy_by_property(limit=limit))


@dashboard_bp.get("/cashflow-forecast")
@require_permission("dashboard.view")
def cashflow_forecast():
    return success_response(data=cashflow_service.forecast())


@dashboard_bp.get("/renewals-at-risk")
@require_permission("dashboard.view")
def renewals_at_risk():
    within_days = min(request.args.get("within_days", default=60, type=int), 365)
    return success_response(data=dashboard.renewals_at_risk(within_days=within_days))


@dashboard_bp.get("/cheque-ageing")
@require_permission("dashboard.view")
def cheque_ageing():
    return success_response(data=dashboard.cheque_ageing())


def _entity_dashboard(builder, entity_id: int):
    try:
        month = _month_arg()
    except ValueError as exc:
        return error_response(str(exc), 400)
    try:
        return success_response(data=builder(entity_id, month=month))
    except ValueError as exc:
        return error_response(str(exc), 404)


@dashboard_bp.get("/property/<int:property_id>")
@require_permission("dashboard.view")
def property_dashboard(property_id: int):
    return _entity_dashboard(dashboard.property_dashboard, property_id)


@dashboard_bp.get("/client/<int:client_id>")
@require_permission("dashboard.view")
def client_dashboard(client_id: int):
    return _entity_dashboard(dashboard.client_dashboard, client_id)


@dashboard_bp.get("/landlord/<int:landlord_id>")
@require_permission("dashboard.view")
def landlord_dashboard(landlord_id: int):
    return _entity_dashboard(dashboard.landlord_dashboard, landlord_id)
