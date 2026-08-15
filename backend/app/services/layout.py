"""Property structure generator.

Turns one create-property request into floors and units in a
single transaction so the caller can roll everything back (the new
property included) if anything in the layout is invalid.

The generator reuses the same patterns as the per-entity create routes:
  * `audit.record(...)` for every created entity plus one summary record,
  * the existing Floor/Unit columns — no schema change.
"""

from ..extensions import db
from ..models import Property, Floor, Unit, UnitType
from . import audit


MAX_FLOORS = 50
MAX_UNITS_PER_FLOOR = 100
MAX_BUILDINGS = 20
MAX_STORES_PER_BUILDING = 50


class LayoutError(ValueError):
    """Raised for any caller-visible validation failure inside the generator."""


def _unit_type_or_raise(code: str, *, where: str) -> UnitType:
    """A unit type is only offerable while active — same non-destructive
    precedent as PropertyType/`_valid_property_type()`."""
    utype = UnitType.query.filter_by(code=code, is_active=True).first()
    if utype is None:
        raise LayoutError(f"{where}: unknown or inactive unit_type {code!r}")
    return utype


def _floor_specs(floors: int, floor_prefix: str, ground_floor: bool) -> list[tuple[str, str]]:
    """Return [(stored_floor_number, floor_seq_used_for_unit_numbering), ...].

    `floor_seq` strips the prefix so unit numbers stay short ("F1" -> "1",
    ground -> "G"). It is used purely to build unit_number; the floor row
    is stored with the user-chosen prefix.
    """
    out: list[tuple[str, str]] = []
    if ground_floor:
        out.append((f"{floor_prefix}G", "G"))
        for i in range(1, floors):
            out.append((f"{floor_prefix}{i}", str(i)))
    else:
        for i in range(1, floors + 1):
            out.append((f"{floor_prefix}{i}", str(i)))
    return out


def generate_structure(
    property: Property,
    *,
    floors: int,
    units_per_floor: int,
    floor_prefix: str = "",
    unit_prefix: str = "",
    ground_floor: bool = False,
    default_unit_type: str = "room",
    actor,
) -> dict:
    """Create floors -> units for `property`.

    Caller owns the transaction: we flush so PKs are assigned and audit
    rows reference the right ids, but we do NOT commit. The caller's
    final `db.session.commit()` ships the new property AND its layout
    in one shot.

    Refuses with `LayoutError` if the property already has any floor —
    so the same property can't be double-built.
    """
    if not (1 <= floors <= MAX_FLOORS):
        raise LayoutError(f"floors must be between 1 and {MAX_FLOORS}")
    if not (1 <= units_per_floor <= MAX_UNITS_PER_FLOOR):
        raise LayoutError(f"units_per_floor must be between 1 and {MAX_UNITS_PER_FLOOR}")
    _unit_type_or_raise(default_unit_type, where="Structure")

    existing = (
        db.session.query(db.func.count(Floor.id))
        .filter(Floor.property_id == property.id)
        .scalar() or 0
    )
    if existing:
        raise LayoutError("Property already has floors; refusing to generate")

    unit_pad = max(2, len(str(units_per_floor)))
    floor_specs = _floor_specs(floors, floor_prefix, ground_floor)

    counts = {"floors": 0, "units": 0}

    for stored_floor_no, floor_seq in floor_specs:
        floor = Floor(
            property_id=property.id,
            floor_number=stored_floor_no,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.session.add(floor)
        db.session.flush()
        counts["floors"] += 1
        audit.record(
            user=actor, action="create", module="floor",
            entity_type="floor", entity_id=floor.id, new_value=floor.to_dict(),
        )

        for uidx in range(1, units_per_floor + 1):
            unit_number = f"{unit_prefix}{floor_seq}{uidx:0{unit_pad}d}"
            unit = Unit(
                property_id=property.id,
                floor_id=floor.id,
                unit_number=unit_number,
                unit_type=default_unit_type,
                created_by=actor.id,
                updated_by=actor.id,
            )
            db.session.add(unit)
            db.session.flush()
            counts["units"] += 1
            audit.record(
                user=actor, action="create", module="unit",
                entity_type="unit", entity_id=unit.id, new_value=unit.to_dict(),
            )

    audit.record(
        user=actor, action="bulk_create", module="property",
        entity_type="property", entity_id=property.id,
        new_value={
            "summary": counts,
            "spec": {
                "floors": floors,
                "units_per_floor": units_per_floor,
                "floor_prefix": floor_prefix,
                "unit_prefix": unit_prefix,
                "ground_floor": ground_floor,
                "default_unit_type": default_unit_type,
            },
        },
        remarks=f"Auto-generated structure for {property.code}",
    )

    return counts


# ----------------------------------------------------------------------
# Compounds: one property standing in for several buildings
# ----------------------------------------------------------------------
#
# A compound gets no new table. A `Floor` and `Unit` are still exactly
# what they were — the building a floor belongs to is carried entirely
# in `floor_number` / `unit_number` ("A-1", "A-101"), the same two
# free-text columns a single building already used. That is enough for
# every screen that lists or groups by floor to keep working unchanged,
# and it means this is additive: `generate_structure` above, and every
# caller of it (including the Phase-8 workbook importer), is untouched.

def _building_code(index: int, requested: str) -> str:
    requested = (requested or "").strip().upper()
    if requested:
        return requested
    # A, B, … Z, A2, B2, … — plain enough to read off a floor plan.
    letter = chr(ord("A") + (index % 26))
    cycle = index // 26 + 1
    return letter if cycle == 1 else f"{letter}{cycle}"


def generate_compound_structure(
    property: Property,
    *,
    buildings: list[dict],
    actor,
) -> dict:
    """Create several buildings' worth of floors and units under one
    property in a single transaction.

    Each entry in `buildings` is one of two shapes, chosen by the
    building's `unit_type` and that type's `bulk_mode` (see `UnitType`):

    floors mode — {"code": "A", "unit_type": "room", "floors": 4,
                   "units_per_floor": 6, "ground_floor": True}
        Walks floors x rooms-per-floor, same as `generate_structure`.

    count mode — {"code": "S1", "unit_type": "store", "unit_count": 4,
                  "with_mezzanine": False, "room_with_store": False}
        No floor/rooms-per-floor breakdown — just `unit_count` units on
        one dedicated floor (labelled "<code>-S"), optionally with one
        extra mezzanine unit for the building and/or one linked `room`
        unit per count-unit. A building never mixes the two shapes: the
        selected unit type alone decides which fields apply, so a
        store-type building has no floors field to leave stray, and a
        room-type building has no separate store count bolted on.

    `code` is optional — buildings are lettered A, B, C… when left
    blank.

    Same transaction contract as `generate_structure`: the caller
    commits. Refuses if the property already has any floor, for the
    same reason — so a compound can't be double-built by resubmitting.
    """
    if not buildings:
        raise LayoutError("At least one building is required")
    if len(buildings) > MAX_BUILDINGS:
        raise LayoutError(f"A compound can hold at most {MAX_BUILDINGS} buildings")

    existing = (
        db.session.query(db.func.count(Floor.id))
        .filter(Floor.property_id == property.id)
        .scalar() or 0
    )
    if existing:
        raise LayoutError("Property already has floors; refusing to generate")

    counts = {"buildings": 0, "floors": 0, "units": 0, "rooms": 0, "stores": 0}
    used_codes: set[str] = set()
    per_building: list[dict] = []

    for index, spec in enumerate(buildings):
        unit_type = str(spec.get("unit_type") or spec.get("default_unit_type") or "room")
        utype = _unit_type_or_raise(unit_type, where=f"Building {index + 1}")

        code = _building_code(index, str(spec.get("code") or ""))
        if code in used_codes:
            raise LayoutError(f"Building code {code!r} is used more than once")
        used_codes.add(code)

        rooms_built = 0
        stores_built = 0

        if utype.bulk_mode == "floors":
            floors = int(spec.get("floors", 0) or 0)
            units_per_floor = int(spec.get("units_per_floor", 0) or 0)
            ground_floor = bool(spec.get("ground_floor", False))

            if not (1 <= floors <= MAX_FLOORS):
                raise LayoutError(
                    f"Building {index + 1}: floors must be between 1 and {MAX_FLOORS}")
            if not (1 <= units_per_floor <= MAX_UNITS_PER_FLOOR):
                raise LayoutError(
                    f"Building {index + 1}: units per floor must be between "
                    f"1 and {MAX_UNITS_PER_FLOOR}")

            floor_specs = _floor_specs(floors, "", ground_floor)
            total_units = floors * units_per_floor
            unit_pad = max(2, len(str(total_units)))
            unit_counter = 1
            for stored_floor_no, _floor_seq in floor_specs:
                floor = Floor(
                    property_id=property.id,
                    floor_number=f"{code}-{stored_floor_no}",
                    floor_name=str(spec.get("label") or f"Building {code}"),
                    created_by=actor.id, updated_by=actor.id,
                )
                db.session.add(floor)
                db.session.flush()
                counts["floors"] += 1
                audit.record(user=actor, action="create", module="floor",
                             entity_type="floor", entity_id=floor.id,
                             new_value=floor.to_dict())

                for _ in range(units_per_floor):
                    unit = Unit(
                        property_id=property.id, floor_id=floor.id,
                        unit_number=f"{code}-{unit_counter:0{unit_pad}d}",
                        unit_type=unit_type,
                        created_by=actor.id, updated_by=actor.id,
                    )
                    db.session.add(unit)
                    db.session.flush()
                    counts["units"] += 1
                    rooms_built += 1
                    unit_counter += 1
                    audit.record(user=actor, action="create", module="unit",
                                 entity_type="unit", entity_id=unit.id,
                                 new_value=unit.to_dict())

        else:  # bulk_mode == "count"
            unit_count = int(spec.get("unit_count", spec.get("store_count", 0)) or 0)
            with_mezzanine = bool(spec.get("with_mezzanine", False))
            room_with_store = bool(spec.get("room_with_store", False))

            if not (0 <= unit_count <= MAX_STORES_PER_BUILDING):
                raise LayoutError(
                    f"Building {index + 1}: unit count must be between "
                    f"0 and {MAX_STORES_PER_BUILDING}")

            if unit_count or with_mezzanine:
                count_floor = Floor(
                    property_id=property.id, floor_number=f"{code}-S",
                    floor_name=str(spec.get("label") or f"Building {code} — {utype.name}"),
                    created_by=actor.id, updated_by=actor.id,
                )
                db.session.add(count_floor)
                db.session.flush()
                counts["floors"] += 1
                audit.record(user=actor, action="create", module="floor",
                             entity_type="floor", entity_id=count_floor.id,
                             new_value=count_floor.to_dict())

                pad = max(2, len(str(unit_count)))
                for uidx in range(1, unit_count + 1):
                    unit_number = f"{code}-S{uidx:0{pad}d}"
                    store = Unit(
                        property_id=property.id, floor_id=count_floor.id,
                        unit_number=unit_number,
                        unit_type=unit_type, occupancy_status="empty",
                        created_by=actor.id, updated_by=actor.id,
                    )
                    db.session.add(store)
                    db.session.flush()
                    counts["units"] += 1
                    stores_built += 1
                    audit.record(user=actor, action="create", module="unit",
                                 entity_type="unit", entity_id=store.id,
                                 new_value=store.to_dict())

                    if room_with_store:
                        room_unit = Unit(
                            property_id=property.id, floor_id=count_floor.id,
                            unit_number=f"{unit_number}-R",
                            unit_type="room", unit_name=f"Room for {unit_number}",
                            occupancy_status="empty",
                            created_by=actor.id, updated_by=actor.id,
                        )
                        db.session.add(room_unit)
                        db.session.flush()
                        counts["units"] += 1
                        rooms_built += 1
                        audit.record(user=actor, action="create", module="unit",
                                     entity_type="unit", entity_id=room_unit.id,
                                     new_value=room_unit.to_dict())

                if with_mezzanine:
                    mezzanine = Unit(
                        property_id=property.id, floor_id=count_floor.id,
                        unit_number=f"{code}-M", unit_type=unit_type,
                        unit_name="Mezzanine", occupancy_status="empty",
                        created_by=actor.id, updated_by=actor.id,
                    )
                    db.session.add(mezzanine)
                    db.session.flush()
                    counts["units"] += 1
                    audit.record(user=actor, action="create", module="unit",
                                 entity_type="unit", entity_id=mezzanine.id,
                                 new_value=mezzanine.to_dict())

        counts["buildings"] += 1
        counts["rooms"] += rooms_built
        counts["stores"] += stores_built
        per_building.append({"code": code, "unit_type": unit_type,
                             "rooms": rooms_built, "stores": stores_built})

    audit.record(
        user=actor, action="bulk_create", module="property",
        entity_type="property", entity_id=property.id,
        new_value={"summary": counts, "buildings": per_building},
        remarks=f"Auto-generated compound structure for {property.code}",
    )

    counts["by_building"] = per_building
    return counts
