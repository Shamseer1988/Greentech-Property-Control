from datetime import date, datetime
from flask import Blueprint, request

from ..extensions import db
from ..models import Property, PropertyAgreement, PropertyType, Landlord, Floor, Unit
from ..services import audit, codes, reminders, layout as layout_service
from ..services import contracts as contract_service
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

properties_bp = Blueprint("properties", __name__)

# Seed values for the property_types master table (cli.py seed()) — the
# set itself is no longer the source of truth for validation, only the
# starting data. See PropertyType in models/property.py.
DEFAULT_PROPERTY_TYPES = [
    ("full_building", "Full building"),
    ("building_with_store", "Building with store"),
    ("flat_building", "Flat building"),
    ("villa", "Villa"),
    ("labour_camp", "Labour camp"),
    ("store", "Store"),
    ("mixed_use", "Mixed use"),
    ("compound", "Compound"),
]
OWNERSHIP_TYPES = {"rented", "company_owned", "temporary"}
STATUSES = {"active", "inactive", "maintenance", "on_hold", "vacated"}
USER_FACING_STATUSES = {"active", "inactive", "maintenance", "on_hold"}

EDITABLE_FIELDS = {
    "name", "property_type", "building_number", "zone", "street", "area", "city",
    "map_link", "gps_lat", "gps_lng", "ownership_type", "managed_by",
    "landlord_id", "remarks",
}
# `status` is intentionally NOT here — it must go through /status so the
# occupancy guard cannot be bypassed.


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value).date()


def _valid_property_type(code: str) -> bool:
    """A property type is only offerable while active — a deactivated
    type stays valid on properties that already carry it (the column is
    free text, never enforced by an FK), just not selectable for new or
    edited ones."""
    return db.session.query(PropertyType.id).filter_by(code=code, is_active=True).first() is not None


def _counts_for(prop_id: int) -> dict:
    """Live counts of floors and units for a property."""
    return {
        "floors_count": db.session.query(db.func.count(Floor.id))
            .filter(Floor.property_id == prop_id).scalar() or 0,
        "units_count": db.session.query(db.func.count(Unit.id))
            .filter(Unit.property_id == prop_id).scalar() or 0,
    }


def _counts_for_many(prop_ids: list[int]) -> dict[int, dict]:
    """One-shot count aggregator for the list endpoint to avoid N+1."""
    if not prop_ids:
        return {}
    floor_rows = (
        db.session.query(Floor.property_id, db.func.count(Floor.id))
        .filter(Floor.property_id.in_(prop_ids))
        .group_by(Floor.property_id).all()
    )
    unit_rows = (
        db.session.query(Unit.property_id, db.func.count(Unit.id))
        .filter(Unit.property_id.in_(prop_ids))
        .group_by(Unit.property_id).all()
    )
    out: dict[int, dict] = {pid: {"floors_count": 0, "units_count": 0} for pid in prop_ids}
    for pid, n in floor_rows:
        out[pid]["floors_count"] = n
    for pid, n in unit_rows:
        out[pid]["units_count"] = n
    return out


@properties_bp.get("")
@require_permission("property.view")
def list_properties():
    q = (request.args.get("q") or "").strip().lower()
    status = request.args.get("status")
    exclude_status = request.args.get("exclude_status")
    ptype = request.args.get("type")
    city = request.args.get("city")
    landlord_id = request.args.get("landlord_id", type=int)

    query = Property.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                db.func.lower(Property.code).like(like),
                db.func.lower(Property.name).like(like),
                db.func.lower(Property.area).like(like),
                db.func.lower(Property.city).like(like),
            )
        )
    if status:
        query = query.filter_by(status=status)
    elif exclude_status:
        # "Show deactivated" unchecked: hide inactive without also hiding
        # maintenance/on_hold, which aren't a deactivation state.
        query = query.filter(Property.status != exclude_status)
    if ptype:
        query = query.filter_by(property_type=ptype)
    if city:
        query = query.filter(db.func.lower(Property.city) == city.lower())
    if landlord_id:
        query = query.filter_by(landlord_id=landlord_id)

    rows = query.order_by(Property.name.asc()).all()
    counts = _counts_for_many([r.id for r in rows])
    data = []
    for r in rows:
        d = r.to_dict()
        d.update(counts.get(r.id, {"floors_count": 0, "units_count": 0}))
        data.append(d)
    return success_response(data=data, meta={"count": len(rows)})


# ------------------------------------------------------------ prop types

@properties_bp.get("/types")
@require_permission("property.view")
def list_property_types():
    query = PropertyType.query
    if request.args.get("active_only") in ("1", "true", "yes"):
        query = query.filter_by(is_active=True)
    rows = query.order_by(PropertyType.name.asc()).all()
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@properties_bp.post("/types")
@require_permission("settings.manage")
def create_property_type():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip() or name.upper().replace(" ", "_")[:32]
    if not name:
        return error_response("name is required", 400)
    if PropertyType.query.filter(db.func.lower(PropertyType.code) == code.lower()).first():
        return error_response("A property type with that code already exists", 409)

    actor = current_user()
    ptype = PropertyType(code=code, name=name, remarks=payload.get("remarks"),
                         created_by=actor.id, updated_by=actor.id)
    db.session.add(ptype)
    db.session.commit()
    return success_response(data=ptype.to_dict(), message="Property type created", status=201)


@properties_bp.patch("/types/<int:type_id>")
@require_permission("settings.manage")
def update_property_type(type_id: int):
    ptype = PropertyType.query.get_or_404(type_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return error_response("name cannot be empty", 400)
        ptype.name = name
    if "remarks" in payload:
        ptype.remarks = payload.get("remarks")
    if "is_active" in payload:
        ptype.is_active = bool(payload["is_active"])
    ptype.updated_by = actor.id
    db.session.commit()
    return success_response(data=ptype.to_dict(), message="Property type updated")


@properties_bp.get("/<int:prop_id>")
@require_permission("property.view")
def get_property(prop_id: int):
    prop = Property.query.get_or_404(prop_id)
    data = prop.to_dict()
    data.update(_counts_for(prop_id))
    return success_response(data=data)


@properties_bp.post("")
@require_permission("property.create")
def create_property():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    ptype = (payload.get("property_type") or "").strip()
    if not name or not ptype:
        return error_response("name and property_type are required", 400)
    if not _valid_property_type(ptype):
        return error_response(f"Unknown or inactive property_type '{ptype}'", 400)

    actor = current_user()
    code = (payload.get("code") or "").strip() or codes.next_code(Property, codes.prefix_for("property"))
    if Property.query.filter(db.func.lower(Property.code) == code.lower()).first():
        return error_response("Code already exists", 409)

    if payload.get("landlord_id"):
        if not Landlord.query.get(payload["landlord_id"]):
            return error_response("landlord_id not found", 400)
    if payload.get("ownership_type") and payload["ownership_type"] not in OWNERSHIP_TYPES:
        return error_response("Invalid ownership_type", 400)
    if payload.get("status") and payload["status"] not in STATUSES:
        return error_response("Invalid status", 400)

    prop = Property(code=code, name=name, property_type=ptype,
                    created_by=actor.id, updated_by=actor.id)
    for k in EDITABLE_FIELDS:
        if k in payload and k not in {"name", "property_type"}:
            setattr(prop, k, payload[k])
    db.session.add(prop)
    db.session.flush()
    audit.record(user=actor, action="create", module="property",
                 entity_type="property", entity_id=prop.id, new_value=prop.to_dict())

    layout_counts = None
    layout = payload.get("layout")
    if layout:
        if not isinstance(layout, dict):
            db.session.rollback()
            return error_response("layout must be an object", 400)
        buildings = layout.get("buildings")
        try:
            if buildings:
                # Compound mode: one property standing in for several
                # buildings, each with its own floors, rooms and stores.
                if not isinstance(buildings, list):
                    raise TypeError("layout.buildings must be a list")
                layout_counts = layout_service.generate_compound_structure(
                    prop, buildings=buildings, actor=actor,
                )
            else:
                layout_counts = layout_service.generate_structure(
                    prop,
                    floors=int(layout.get("floors", 0) or 0),
                    units_per_floor=int(layout.get("units_per_floor", 0) or 0),
                    floor_prefix=str(layout.get("floor_prefix") or "").strip(),
                    unit_prefix=str(layout.get("unit_prefix") or "").strip(),
                    ground_floor=bool(layout.get("ground_floor", False)),
                    default_unit_type=str(layout.get("default_unit_type") or "room"),
                    actor=actor,
                )
        except layout_service.LayoutError as e:
            db.session.rollback()
            return error_response(str(e), 400)
        except (TypeError, ValueError) as e:
            db.session.rollback()
            return error_response(f"Invalid layout payload: {e}", 400)

    db.session.commit()
    data = prop.to_dict()
    if layout_counts is not None:
        data["layout_generated"] = layout_counts
    return success_response(data=data, message="Property created", status=201)


@properties_bp.put("/<int:prop_id>")
@require_permission("property.edit")
def update_property(prop_id: int):
    prop = Property.query.get_or_404(prop_id)
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    old = prop.to_dict()

    if "status" in payload:
        return error_response(
            "Status changes go through POST /properties/{id}/status — see the property control modal.",
            400,
        )
    if "property_type" in payload and payload["property_type"] != prop.property_type \
            and not _valid_property_type(payload["property_type"]):
        # A deactivated type stays legal to resave unchanged (an edit form
        # that always round-trips every field shouldn't be blocked from
        # saving other changes just because this property's type has since
        # been retired) — it only becomes an error when actually switching
        # to something invalid or inactive.
        return error_response("Invalid or inactive property_type", 400)
    if "ownership_type" in payload and payload["ownership_type"] not in OWNERSHIP_TYPES:
        return error_response("Invalid ownership_type", 400)
    if "landlord_id" in payload and payload["landlord_id"]:
        if not Landlord.query.get(payload["landlord_id"]):
            return error_response("landlord_id not found", 400)

    for k in EDITABLE_FIELDS:
        if k in payload:
            setattr(prop, k, payload[k])
    prop.updated_by = actor.id
    audit.record(user=actor, action="update", module="property",
                 entity_type="property", entity_id=prop.id, old_value=old, new_value=prop.to_dict())
    db.session.commit()
    return success_response(data=prop.to_dict(), message="Property updated")


def _occupancy_snapshot(prop_id: int) -> dict:
    """Counts of units still held — used to explain blocked status changes.

    From Phase 2 the occupied count derives from active client-contract
    unit assignments; today it reads the unit status field."""
    occupied = (
        db.session.query(db.func.count(Unit.id))
        .filter(Unit.property_id == prop_id, Unit.occupancy_status == "occupied")
        .scalar() or 0
    )
    sample: list[dict] = []
    if occupied:
        units = (
            Unit.query
            .filter(Unit.property_id == prop_id, Unit.occupancy_status == "occupied")
            .limit(10).all()
        )
        sample = [{
            "unit_id": u.id, "unit_number": u.unit_number, "unit_type": u.unit_type,
        } for u in units]
    return {"occupied": occupied, "sample": sample}


@properties_bp.post("/<int:prop_id>/status")
@require_permission("property.deactivate")
def change_property_status(prop_id: int):
    prop = Property.query.get_or_404(prop_id)
    payload = request.get_json(silent=True) or {}
    new_status = (payload.get("status") or "").strip()
    reason = (payload.get("reason") or "").strip()
    remarks = (payload.get("remarks") or "").strip() or None

    if new_status not in USER_FACING_STATUSES:
        return error_response(
            f"status must be one of {sorted(USER_FACING_STATUSES)}", 400,
        )
    if new_status == prop.status:
        return error_response(f"Property is already {new_status}", 400)
    if new_status != "active" and not reason:
        return error_response("reason is required when moving away from active", 400)

    # Guard: refuse to move out of active while units are held.
    if new_status != "active":
        snap = _occupancy_snapshot(prop.id)
        if snap["occupied"]:
            return error_response(
                (
                    f"Cannot set {prop.name} to {new_status} — "
                    f"{snap['occupied']} unit(s) occupied. "
                    "Release or cancel those contracts first."
                ),
                status=409,
                details={
                    "blocked": True,
                    "occupied": snap["occupied"],
                    "sample_units": snap["sample"],
                },
            )

    actor = current_user()
    old_status = prop.status
    prop.status = new_status
    prop.updated_by = actor.id
    audit.record(
        user=actor, action="status_change", module="property",
        entity_type="property", entity_id=prop.id,
        old_value={"status": old_status},
        new_value={"status": new_status, "reason": reason, "remarks": remarks},
        remarks=reason or remarks,
    )
    db.session.commit()
    return success_response(
        data=prop.to_dict(),
        message=f"Property {prop.code} set to {new_status}",
    )


@properties_bp.get("/<int:prop_id>/occupancy-snapshot")
@require_permission("property.view")
def property_occupancy_snapshot(prop_id: int):
    Property.query.get_or_404(prop_id)
    return success_response(data=_occupancy_snapshot(prop_id))


@properties_bp.delete("/<int:prop_id>")
@require_permission("property.deactivate")
def deactivate_property(prop_id: int):
    """Legacy endpoint — routed through the same guard."""
    prop = Property.query.get_or_404(prop_id)
    if prop.status == "inactive":
        return error_response("Property is already inactive", 400)
    snap = _occupancy_snapshot(prop.id)
    if snap["occupied"]:
        return error_response(
            (
                f"Cannot deactivate {prop.name} — "
                f"{snap['occupied']} unit(s) occupied. "
                "Release or cancel those contracts first."
            ),
            status=409,
            details={
                "blocked": True,
                "occupied": snap["occupied"],
                "sample_units": snap["sample"],
            },
        )
    actor = current_user()
    prop.status = "inactive"
    prop.updated_by = actor.id
    audit.record(
        user=actor, action="status_change", module="property",
        entity_type="property", entity_id=prop.id,
        old_value={"status": "active"}, new_value={"status": "inactive"},
        remarks="deactivated via DELETE",
    )
    db.session.commit()
    return success_response(message="Property deactivated")


# ---------- Agreements ----------

@properties_bp.get("/<int:prop_id>/agreements")
@require_permission("property.view")
def list_agreements(prop_id: int):
    Property.query.get_or_404(prop_id)
    rows = (
        PropertyAgreement.query
        .filter_by(property_id=prop_id)
        .order_by(PropertyAgreement.is_active.desc(), PropertyAgreement.expiry_date.desc())
        .all()
    )
    return success_response(data=[r.to_dict() for r in rows], meta={"count": len(rows)})


@properties_bp.post("/<int:prop_id>/agreements")
@require_permission("property.edit")
def create_agreement(prop_id: int):
    prop = Property.query.get_or_404(prop_id)
    payload = request.get_json(silent=True) or {}

    landlord_id = payload.get("landlord_id")
    if not landlord_id or not Landlord.query.get(landlord_id):
        return error_response("Valid landlord_id is required", 400)
    try:
        start = _parse_date(payload.get("start_date"))
        expiry = _parse_date(payload.get("expiry_date"))
    except ValueError:
        return error_response("Invalid date format (use YYYY-MM-DD)", 400)
    if not start or not expiry:
        return error_response("start_date and expiry_date are required", 400)
    if expiry < start:
        return error_response("expiry_date must be on or after start_date", 400)

    actor = current_user()

    # Archive previous active agreement
    previous = (
        PropertyAgreement.query.filter_by(property_id=prop_id, is_active=True).all()
    )
    for p in previous:
        p.status = "renewed"
        p.renewal_status = "renewed"
        p.updated_by = actor.id

    from ..services import landlord_contracts as lc_service

    ag = PropertyAgreement(
        property_id=prop.id,
        landlord_id=landlord_id,
        contract_number=lc_service.next_landlord_contract_number(),
        agreement_number=payload.get("agreement_number"),
        start_date=start,
        expiry_date=expiry,
        monthly_rent=payload.get("monthly_rent"),
        security_deposit=payload.get("security_deposit"),
        payment_terms=payload.get("payment_terms"),
        notice_period=payload.get("notice_period"),
        renewal_status=payload.get("renewal_status") or "pending",
        kahramaa_account=payload.get("kahramaa_account"),
        municipality_ref=payload.get("municipality_ref"),
        reminder_days_before_expiry=int(payload.get("reminder_days_before_expiry") or 90),
        payment_mode=payload.get("payment_mode") or "cheque",
        opening_balance=payload.get("opening_balance") or 0,
        remarks=payload.get("remarks"),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.session.add(ag)
    db.session.flush()
    audit.record(user=actor, action="create", module="agreement",
                 entity_type="property_agreement", entity_id=ag.id, new_value=ag.to_dict(),
                 remarks=f"property {prop.code}")
    db.session.commit()
    return success_response(data=ag.to_dict(), message="Agreement created", status=201)


@properties_bp.put("/<int:prop_id>/agreements/<int:ag_id>")
@require_permission("property.edit")
def update_agreement(prop_id: int, ag_id: int):
    ag = PropertyAgreement.query.filter_by(id=ag_id, property_id=prop_id).first_or_404()
    payload = request.get_json(silent=True) or {}
    actor = current_user()
    old = ag.to_dict()
    if "start_date" in payload:
        ag.start_date = _parse_date(payload["start_date"])
    if "expiry_date" in payload:
        ag.expiry_date = _parse_date(payload["expiry_date"])
    for k in (
        "agreement_number", "monthly_rent", "security_deposit", "payment_terms",
        "notice_period", "renewal_status", "kahramaa_account", "municipality_ref",
        "reminder_days_before_expiry", "remarks", "payment_mode", "opening_balance",
    ):
        if k in payload:
            setattr(ag, k, payload[k])
    if "landlord_id" in payload and payload["landlord_id"]:
        if not Landlord.query.get(payload["landlord_id"]):
            return error_response("landlord_id not found", 400)
        ag.landlord_id = payload["landlord_id"]
    ag.updated_by = actor.id
    audit.record(user=actor, action="update", module="agreement",
                 entity_type="property_agreement", entity_id=ag.id,
                 old_value=old, new_value=ag.to_dict())
    db.session.commit()
    return success_response(data=ag.to_dict(), message="Agreement updated")


# ---------- Structure ----------

@properties_bp.get("/<int:prop_id>/structure")
@require_permission("property.view")
def property_structure(prop_id: int):
    Property.query.get_or_404(prop_id)
    floors = (
        Floor.query.filter_by(property_id=prop_id)
        .order_by(Floor.floor_number.asc())
        .all()
    )
    all_units = (
        Unit.query.filter_by(property_id=prop_id)
        .order_by(Unit.unit_number.asc())
        .all()
    )
    by_floor: dict[int, list[Unit]] = {}
    for u in all_units:
        by_floor.setdefault(u.floor_id, []).append(u)

    # One query for every occupied unit on the property, keyed by unit_id —
    # the floor plan's hover popup needs to know who's in each unit today.
    holders = contract_service.units_held_on([u.id for u in all_units], date.today())

    out = []
    for f in floors:
        f_dict = f.to_dict()
        unit_dicts = []
        for u in by_floor.get(f.id, []):
            d = u.to_dict()
            contract = holders.get(u.id)
            if contract is not None:
                d["occupant"] = {
                    "client_id": contract.client_id,
                    "client_name": contract.client.name if contract.client else None,
                    "contract_id": contract.id,
                    "contract_number": contract.contract_number,
                    "monthly_rent": float(contract.monthly_rent) if contract.monthly_rent is not None else None,
                    "start_date": contract.start_date.isoformat() if contract.start_date else None,
                    "expiry_date": contract.expiry_date.isoformat() if contract.expiry_date else None,
                }
            else:
                d["occupant"] = None
            unit_dicts.append(d)
        f_dict["units"] = unit_dicts
        out.append(f_dict)
    return success_response(data=out, meta={"count": len(out)})


@properties_bp.post("/<int:prop_id>/floors/<int:floor_id>/renumber-units")
@require_permission("unit.manage")
def renumber_units(prop_id: int, floor_id: int):
    """Bulk-rename units on a floor using a new prefix.

    Body: ``{"unit_prefix": str, "force": bool=false}``.

    The new unit number for unit index i (1..N within the floor) is
    ``{unit_prefix}{floor_seq}{nn}`` where ``floor_seq`` strips a single
    optional letter prefix from the stored floor_number (so "F1" -> "1",
    "G" -> "G").

    Refuses with 409 if any unit on the floor is occupied unless
    ``force=true`` is supplied — caller takes responsibility. The rename
    is two-phase: every row touched is first set to a guaranteed-unique
    temp name, then to its final name, so the UNIQUE constraint never
    fires on an intermediate state.
    """
    prop = Property.query.get_or_404(prop_id)
    floor = Floor.query.filter_by(id=floor_id, property_id=prop.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    new_prefix = str(payload.get("unit_prefix") or "").strip()
    force = bool(payload.get("force", False))

    units = (
        Unit.query.filter_by(floor_id=floor.id)
        .order_by(Unit.unit_number.asc())
        .all()
    )
    if not units:
        return success_response(
            data={"renamed": 0, "units": []},
            message="No units on this floor",
        )

    # Detect occupied units across the floor before touching anything.
    if not force:
        occupied = (
            db.session.query(db.func.count(Unit.id))
            .filter(Unit.floor_id == floor.id, Unit.occupancy_status == "occupied")
            .scalar() or 0
        )
        if occupied:
            return error_response(
                f"Floor has {occupied} occupied unit(s). "
                "Release the contracts first or re-send with force=true.",
                status=409,
                details={"occupied": occupied, "force_required": True},
            )

    # Determine floor_seq for unit numbers (same rule as layout generator).
    raw = floor.floor_number
    floor_seq = raw if raw == "G" or raw.startswith("G") and len(raw) > 1 and raw[1:].isalpha() else (
        "".join(ch for ch in raw if ch.isdigit()) or raw
    )
    if not floor_seq:
        floor_seq = raw  # final fallback

    unit_pad = max(2, len(str(len(units))))
    actor = current_user()

    # Build rename map: (unit, old_number, new_number).
    renames: list[tuple[Unit, str, str]] = []
    for idx, unit in enumerate(units, start=1):
        new_no = f"{new_prefix}{floor_seq}{idx:0{unit_pad}d}"
        renames.append((unit, unit.unit_number, new_no))

    # No-op if nothing changes.
    if all(old == new for _, old, new in renames):
        return success_response(
            data={"renamed": 0, "units": [u.to_dict() for u, _, _ in renames]},
            message="Unit numbers already match the requested prefix",
        )

    # Phase A: park every affected unit_number at a unique temp value so
    # the rename can't collide on the UNIQUE constraint.
    for unit, _, _ in renames:
        unit.unit_number = f"__TMP_UNIT_{unit.id}__"
    db.session.flush()

    # Phase B: assign final unit numbers.
    old_to_new: list[dict] = []
    for unit, old_number, new_no in renames:
        unit.unit_number = new_no
        unit.updated_by = actor.id
        old_to_new.append({
            "unit_id": unit.id,
            "old_unit_number": old_number,
            "new_unit_number": new_no,
        })
        audit.record(
            user=actor, action="renumber", module="unit",
            entity_type="unit", entity_id=unit.id,
            new_value={"unit_number": new_no},
            remarks=f"floor {floor.floor_number} prefix='{new_prefix}'",
        )
    db.session.flush()

    audit.record(
        user=actor, action="bulk_renumber", module="floor",
        entity_type="floor", entity_id=floor.id,
        new_value={
            "renamed": len(renames),
            "unit_prefix": new_prefix,
            "force": force,
        },
        remarks=f"Renumbered {len(renames)} units on floor {floor.floor_number}",
    )
    db.session.commit()
    return success_response(
        data={
            "renamed": len(renames),
            "units": [u.to_dict() for u, _, _ in renames],
            "diff": old_to_new,
        },
        message=f"Renumbered {len(renames)} unit(s) on floor {floor.floor_number}",
    )


# ---------- Reminders ----------

@properties_bp.get("/agreements/expiring")
@require_permission("property.view")
def expiring():
    days = request.args.get("days", default=90, type=int)
    rows = reminders.expiring_agreements(within_days=days)
    today = date.today()
    out = []
    for a in rows:
        d = a.to_dict()
        d["bucket"] = reminders.agreement_bucket(a.expiry_date, today)
        d["days_left"] = (a.expiry_date - today).days
        d["property"] = {"id": a.property.id, "code": a.property.code, "name": a.property.name}
        out.append(d)
    return success_response(data=out, meta={"count": len(out), "summary": reminders.reminder_summary(today)})
