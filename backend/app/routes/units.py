from flask import Blueprint, request

from ..extensions import db
from ..models import Unit, UnitType, Floor, Property
from ..models.unit import UNIT_STATUSES, BULK_MODES
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


def _valid_unit_type(code: str) -> bool:
    """A unit type is only offerable while active — a deactivated type
    stays valid on units that already carry it (the column is free
    text, never enforced by an FK), just not selectable for new or
    edited ones."""
    return db.session.query(UnitType.id).filter_by(code=code, is_active=True).first() is not None


def _validate(payload: dict, *, current_type: str | None = None) -> str | None:
    # A deactivated type stays legal to resave unchanged — same
    # non-destructive precedent as `update_property`'s `property_type`
    # check — it only becomes an error when actually switching to
    # something invalid or inactive.
    if "unit_type" in payload and payload["unit_type"] != current_type \
            and not _valid_unit_type(payload["unit_type"]):
        return "Unknown or inactive unit_type"
    return None


# ------------------------------------------------------------ unit types

@units_bp.get("/units/types")
@require_permission("unit.view")
def list_unit_types():
    query = UnitType.query
    if request.args.get("active_only") in ("1", "true", "yes"):
        query = query.filter_by(is_active=True)
    rows = query.order_by(UnitType.name.asc()).all()
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@units_bp.post("/units/types")
@require_permission("settings.manage")
def create_unit_type():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip() or name.upper().replace(" ", "_")[:32]
    if not name:
        return error_response("name is required", 400)
    bulk_mode = (payload.get("bulk_mode") or "floors").strip()
    if bulk_mode not in BULK_MODES:
        return error_response(f"bulk_mode must be one of {sorted(BULK_MODES)}", 400)
    if UnitType.query.filter(db.func.lower(UnitType.code) == code.lower()).first():
        return error_response("A unit type with that code already exists", 409)

    actor = current_user()
    utype = UnitType(code=code, name=name, remarks=payload.get("remarks"),
                     is_facility=bool(payload.get("is_facility", False)),
                     bulk_mode=bulk_mode,
                     created_by=actor.id, updated_by=actor.id)
    db.session.add(utype)
    db.session.commit()
    return success_response(data=utype.to_dict(), message="Unit type created", status=201)


@units_bp.patch("/units/types/<int:type_id>")
@require_permission("settings.manage")
def update_unit_type(type_id: int):
    utype = UnitType.query.get_or_404(type_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return error_response("name cannot be empty", 400)
        utype.name = name
    if "bulk_mode" in payload:
        bulk_mode = (payload.get("bulk_mode") or "").strip()
        if bulk_mode not in BULK_MODES:
            return error_response(f"bulk_mode must be one of {sorted(BULK_MODES)}", 400)
        utype.bulk_mode = bulk_mode
    if "is_facility" in payload:
        utype.is_facility = bool(payload["is_facility"])
    if "remarks" in payload:
        utype.remarks = payload.get("remarks")
    if "is_active" in payload:
        utype.is_active = bool(payload["is_active"])
    utype.updated_by = actor.id
    db.session.commit()
    return success_response(data=utype.to_dict(), message="Unit type updated")


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
    err = _validate(payload, current_type=unit.unit_type)
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
