from flask import Blueprint, request

from ..extensions import db
from ..models import Unit, Floor, Property
from ..models.unit import UNIT_TYPES, UNIT_STATUSES
from ..services import audit
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

units_bp = Blueprint("units", __name__)


def _publish_occupancy(event: dict) -> None:
    """Best-effort SSE publish for live floor-map updates."""
    try:
        from ..services import events as event_service
        event_service.publish("occupancy", event)
    except Exception:
        pass


EDITABLE = {
    "unit_number", "unit_name", "unit_type", "size", "is_shared_facility",
    "has_bathroom", "has_ac", "monthly_rent", "remarks",
}


def _validate(payload: dict) -> str | None:
    if "unit_type" in payload and payload["unit_type"] not in UNIT_TYPES:
        return f"unit_type must be one of {sorted(UNIT_TYPES)}"
    return None


@units_bp.get("/floors/<int:floor_id>/units")
@require_permission("unit.view")
def list_units_for_floor(floor_id: int):
    Floor.query.get_or_404(floor_id)
    rows = (
        Unit.query.filter_by(floor_id=floor_id)
        .order_by(Unit.unit_number.asc())
        .all()
    )
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@units_bp.get("/properties/<int:prop_id>/units")
@require_permission("unit.view")
def list_units_for_property(prop_id: int):
    Property.query.get_or_404(prop_id)
    rows = (
        Unit.query.filter_by(property_id=prop_id)
        .order_by(Unit.floor_id.asc(), Unit.unit_number.asc())
        .all()
    )
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@units_bp.get("/units/<int:unit_id>")
@require_permission("unit.view")
def get_unit(unit_id: int):
    return success_response(data=Unit.query.get_or_404(unit_id).to_dict())


@units_bp.post("/floors/<int:floor_id>/units")
@require_permission("unit.manage")
def create_unit(floor_id: int):
    floor = Floor.query.get_or_404(floor_id)
    payload = request.get_json(silent=True) or {}
    err = _validate(payload)
    if err:
        return error_response(err, 400)
    unit_number = (payload.get("unit_number") or "").strip()
    if not unit_number:
        return error_response("unit_number is required", 400)
    if Unit.query.filter_by(property_id=floor.property_id, floor_id=floor.id, unit_number=unit_number).first():
        return error_response("Unit number already exists on this floor", 409)

    actor = current_user()
    unit = Unit(
        property_id=floor.property_id,
        floor_id=floor.id,
        unit_number=unit_number,
        created_by=actor.id,
        updated_by=actor.id,
    )
    for k in EDITABLE:
        if k in payload and k != "unit_number":
            setattr(unit, k, payload[k])
    db.session.add(unit)
    db.session.flush()
    audit.record(user=actor, action="create", module="unit",
                 entity_type="unit", entity_id=unit.id, new_value=unit.to_dict())
    db.session.commit()
    return success_response(data=unit.to_dict(), message="Unit created", status=201)


@units_bp.put("/units/<int:unit_id>")
@require_permission("unit.manage")
def update_unit(unit_id: int):
    unit = Unit.query.get_or_404(unit_id)
    payload = request.get_json(silent=True) or {}
    err = _validate(payload)
    if err:
        return error_response(err, 400)

    actor = current_user()
    old = unit.to_dict()
    if "unit_number" in payload:
        new_no = (payload["unit_number"] or "").strip()
        if new_no != unit.unit_number:
            if Unit.query.filter_by(property_id=unit.property_id, floor_id=unit.floor_id, unit_number=new_no).first():
                return error_response("Unit number already exists on this floor", 409)
            unit.unit_number = new_no
    for k in EDITABLE:
        if k in payload and k != "unit_number":
            setattr(unit, k, payload[k])
    unit.updated_by = actor.id
    audit.record(user=actor, action="update", module="unit",
                 entity_type="unit", entity_id=unit.id, old_value=old, new_value=unit.to_dict())
    db.session.commit()
    return success_response(data=unit.to_dict(), message="Unit updated")


@units_bp.post("/units/<int:unit_id>/status")
@require_permission("unit.manage")
def set_unit_status(unit_id: int):
    unit = Unit.query.get_or_404(unit_id)
    payload = request.get_json(silent=True) or {}
    status = (payload.get("status") or "").strip()
    if status not in UNIT_STATUSES:
        return error_response(f"status must be one of {sorted(UNIT_STATUSES)}", 400)
    # From Phase 2, "occupied" derives from active contract allocations;
    # manual status is for maintenance / blocked and corrections.
    unit.occupancy_status = status
    actor = current_user()
    unit.updated_by = actor.id
    audit.record(user=actor, action="update_status", module="unit",
                 entity_type="unit", entity_id=unit.id, new_value={"status": unit.occupancy_status})
    db.session.commit()
    _publish_occupancy({
        "type": "unit.status_changed",
        "property_id": unit.property_id, "unit_id": unit.id,
        "status": unit.occupancy_status,
    })
    return success_response(data=unit.to_dict(), message="Unit status updated")


@units_bp.delete("/units/<int:unit_id>")
@require_permission("unit.manage")
def delete_unit(unit_id: int):
    unit = Unit.query.get_or_404(unit_id)
    if unit.occupancy_status == "occupied":
        return error_response("Cannot delete an occupied unit; release the contract first", 409)
    unit_id_snap, prop_id_snap = unit.id, unit.property_id
    actor = current_user()
    audit.record(user=actor, action="delete", module="unit",
                 entity_type="unit", entity_id=unit.id, old_value=unit.to_dict())
    db.session.delete(unit)
    db.session.commit()
    _publish_occupancy({
        "type": "unit.deleted",
        "property_id": prop_id_snap, "unit_id": unit_id_snap,
    })
    return success_response(message="Unit deleted")
