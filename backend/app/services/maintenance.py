from datetime import date, datetime

from ..extensions import db
from ..models import Property, Unit, MaintenanceRecord
from ..models.renewal_maintenance import (
    MAINTENANCE_ENTITY_TYPES, generate_renewal_or_maintenance_number,
)


class MaintenanceError(ValueError):
    pass


def _parse_date(value, fallback: date | None = None) -> date | None:
    if value is None or value == "":
        return fallback
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value)).date()


def _restorable_status(prior_status: str, entity_type: str) -> str:
    # Only restore to operationally safe states. If the entity was in a
    # transient/derived state previously, fall back to the canonical default.
    safe_defaults = {"property": "active", "unit": "empty"}
    if entity_type == "unit" and prior_status in {"partially_occupied", "full"}:
        return "empty"
    return prior_status or safe_defaults[entity_type]


def start_maintenance(
    *,
    entity_type: str,
    entity_id: int,
    reason: str | None = None,
    start_date=None,
    expected_end_date=None,
    remarks: str | None = None,
    approved_by: int | None = None,
    actor_id: int,
) -> MaintenanceRecord:
    if entity_type not in MAINTENANCE_ENTITY_TYPES:
        raise MaintenanceError(f"entity_type must be one of {sorted(MAINTENANCE_ENTITY_TYPES)}")

    existing = (
        MaintenanceRecord.query
        .filter_by(entity_type=entity_type, entity_id=entity_id, status="in_progress")
        .first()
    )
    if existing is not None:
        raise MaintenanceError(
            f"{entity_type} {entity_id} already has an open maintenance record ({existing.transaction_number})"
        )

    when_start = _parse_date(start_date, date.today())
    when_end = _parse_date(expected_end_date, None) if expected_end_date else None

    property_id: int | None = None
    prior_status: str

    if entity_type == "property":
        prop = Property.query.get(entity_id)
        if prop is None:
            raise MaintenanceError("Property not found")
        prior_status = prop.status
        prop.status = "maintenance"
        prop.updated_by = actor_id
        property_id = prop.id

    else:  # unit
        unit = Unit.query.get(entity_id)
        if unit is None:
            raise MaintenanceError("Unit not found")
        if unit.occupancy_status == "occupied":
            raise MaintenanceError("Unit is occupied; release the contract allocation first.")
        prior_status = unit.occupancy_status
        unit.occupancy_status = "maintenance"
        unit.updated_by = actor_id
        property_id = unit.property_id

    record = MaintenanceRecord(
        transaction_number=generate_renewal_or_maintenance_number("MAINT"),
        entity_type=entity_type,
        entity_id=entity_id,
        property_id=property_id,
        start_date=when_start,
        expected_end_date=when_end,
        reason=reason,
        prior_status=prior_status,
        status="in_progress",
        remarks=remarks,
        approved_by=approved_by,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.session.add(record)
    db.session.flush()
    return record


def complete_maintenance(
    *,
    record_id: int,
    actual_end_date=None,
    remarks: str | None = None,
    actor_id: int,
) -> MaintenanceRecord:
    record = MaintenanceRecord.query.get(record_id)
    if record is None:
        raise MaintenanceError("Maintenance record not found")
    if record.status != "in_progress":
        raise MaintenanceError(f"Maintenance record is already {record.status}")

    when_end = _parse_date(actual_end_date, date.today())
    restored = _restorable_status(record.prior_status, record.entity_type)

    if record.entity_type == "property":
        prop = Property.query.get(record.entity_id)
        if prop is not None:
            prop.status = restored
            prop.updated_by = actor_id

    else:  # unit
        unit = Unit.query.get(record.entity_id)
        if unit is not None:
            unit.occupancy_status = restored
            unit.updated_by = actor_id

    record.status = "completed"
    record.actual_end_date = when_end
    if remarks:
        record.remarks = (record.remarks + "\n" + remarks) if record.remarks else remarks
    record.updated_by = actor_id
    db.session.flush()
    return record


def cancel_maintenance(*, record_id: int, actor_id: int) -> MaintenanceRecord:
    """Cancel a maintenance record without restoring the entity (rare; for
    correcting mistakes). Most users should `complete` instead."""
    record = MaintenanceRecord.query.get(record_id)
    if record is None:
        raise MaintenanceError("Maintenance record not found")
    if record.status != "in_progress":
        raise MaintenanceError(f"Maintenance record is already {record.status}")
    record.status = "cancelled"
    record.actual_end_date = date.today()
    record.updated_by = actor_id
    db.session.flush()
    return record
