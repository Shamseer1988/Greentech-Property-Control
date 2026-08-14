from flask import Blueprint, request

from ..extensions import db
from ..models import Floor, Property
from ..services import audit
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

floors_bp = Blueprint("floors", __name__)

EDITABLE = {"floor_number", "floor_name", "floor_type", "status", "remarks"}


@floors_bp.get("/properties/<int:prop_id>/floors")
@require_permission("property.view")
def list_floors(prop_id: int):
    Property.query.get_or_404(prop_id)
    rows = (
        Floor.query.filter_by(property_id=prop_id)
        .order_by(Floor.floor_number.asc())
        .all()
    )
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@floors_bp.post("/properties/<int:prop_id>/floors")
@require_permission("floor.manage")
def create_floor(prop_id: int):
    Property.query.get_or_404(prop_id)
    payload = request.get_json(silent=True) or {}
    floor_number = (payload.get("floor_number") or "").strip()
    if not floor_number:
        return error_response("floor_number is required", 400)
    if Floor.query.filter_by(property_id=prop_id, floor_number=floor_number).first():
        return error_response("Floor number already exists for this property", 409)

    actor = current_user()
    floor = Floor(property_id=prop_id, floor_number=floor_number,
                  created_by=actor.id, updated_by=actor.id)
    for k in EDITABLE:
        if k in payload and k != "floor_number":
            setattr(floor, k, payload[k])
    db.session.add(floor)
    db.session.flush()
    audit.record(user=actor, action="create", module="floor",
                 entity_type="floor", entity_id=floor.id, new_value=floor.to_dict())
    db.session.commit()
    return success_response(data=floor.to_dict(), message="Floor created", status=201)


@floors_bp.put("/floors/<int:floor_id>")
@require_permission("floor.manage")
def update_floor(floor_id: int):
    floor = Floor.query.get_or_404(floor_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    old = floor.to_dict()
    if "floor_number" in payload:
        new_no = (payload["floor_number"] or "").strip()
        if new_no != floor.floor_number:
            if Floor.query.filter_by(property_id=floor.property_id, floor_number=new_no).first():
                return error_response("Floor number already exists", 409)
            floor.floor_number = new_no
    for k in EDITABLE:
        if k in payload and k != "floor_number":
            setattr(floor, k, payload[k])
    floor.updated_by = actor.id
    audit.record(user=actor, action="update", module="floor",
                 entity_type="floor", entity_id=floor.id, old_value=old, new_value=floor.to_dict())
    db.session.commit()
    return success_response(data=floor.to_dict(), message="Floor updated")


@floors_bp.delete("/floors/<int:floor_id>")
@require_permission("floor.manage")
def delete_floor(floor_id: int):
    floor = Floor.query.get_or_404(floor_id)
    if floor.units:
        return error_response("Cannot delete a floor that has units", 409)
    actor = current_user()
    audit.record(user=actor, action="delete", module="floor",
                 entity_type="floor", entity_id=floor.id, old_value=floor.to_dict())
    db.session.delete(floor)
    db.session.commit()
    return success_response(message="Floor deleted")
