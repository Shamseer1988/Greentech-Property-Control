"""The one-time migration off the workbook.

Three steps, deliberately separate: **parse** reads the file and writes
nothing; **plan** turns the parse into the exact set of writes with the
operator's corrections applied, still writing nothing; **commit** does
it, once, in a single transaction.

Everything sits behind `settings.manage` — this rewrites the whole
database, so it belongs with the operator who owns the install.
"""
import os
import tempfile
from datetime import datetime

from flask import Blueprint, request

from ..extensions import db
from ..services import audit, migration as migration_service
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

migration_bp = Blueprint("migration", __name__)

ALLOWED_SUFFIXES = (".xlsm", ".xlsx")


def _saved_upload():
    """Persist the uploaded workbook to a temp file openpyxl can read.

    Returns (path, error). The caller must remove the file.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return None, "Attach the master workbook (.xlsm)"
    if not upload.filename.lower().endswith(ALLOWED_SUFFIXES):
        return None, f"Only {' / '.join(ALLOWED_SUFFIXES)} files can be read"
    handle, path = tempfile.mkstemp(suffix=os.path.splitext(upload.filename)[1])
    os.close(handle)
    upload.save(path)
    return path, None


@migration_bp.post("/parse")
@require_permission("settings.manage")
def parse():
    """Read the workbook and report what is in it. Writes nothing."""
    path, error = _saved_upload()
    if error:
        return error_response(error, 400)
    try:
        parsed = migration_service.parse_workbook(path)
    except Exception as exc:                      # noqa: BLE001 — shown to operator
        return error_response(f"Could not read that workbook: {exc}", 400)
    finally:
        os.unlink(path)
    return success_response(data=parsed, meta=parsed["summary"])


@migration_bp.post("/plan")
@require_permission("settings.manage")
def plan():
    """Apply the operator's corrections and show exactly what would be
    written. Still writes nothing."""
    path, error = _saved_upload()
    if error:
        return error_response(error, 400)
    raw = request.form.get("overrides")
    overrides = {}
    if raw:
        import json
        try:
            overrides = json.loads(raw)
        except ValueError:
            os.unlink(path)
            return error_response("overrides must be JSON", 400)
    try:
        parsed = migration_service.parse_workbook(path)
        built = migration_service.build_commit_plan(parsed, overrides=overrides)
    except Exception as exc:                      # noqa: BLE001
        return error_response(f"Could not plan the migration: {exc}", 400)
    finally:
        os.unlink(path)
    return success_response(data=built, meta=built["summary"])


@migration_bp.post("/commit")
@require_permission("settings.manage")
def commit():
    """Write the plan. One transaction: it all lands or none of it does.

    Refuses to run against a database that already holds contracts
    unless `confirm_existing` is sent, because the usual reason for that
    state is someone running the migration twice by accident.
    """
    from ..models import ClientContract

    path, error = _saved_upload()
    if error:
        return error_response(error, 400)

    payload_raw = request.form.get("overrides")
    overrides = {}
    if payload_raw:
        import json
        try:
            overrides = json.loads(payload_raw)
        except ValueError:
            os.unlink(path)
            return error_response("overrides must be JSON", 400)

    confirm = str(request.form.get("confirm_existing", "")).lower() in ("1", "true", "yes")
    existing = db.session.query(db.func.count(ClientContract.id)).scalar() or 0
    if existing and not confirm:
        os.unlink(path)
        return error_response(
            f"This database already holds {existing} contract(s). Re-running the "
            "migration reuses what matches and adds what doesn't, but if this "
            "wasn't intended, restore a backup first. Send confirm_existing=true "
            "to go ahead.", 409)

    actor = current_user()
    try:
        parsed = migration_service.parse_workbook(path)
        built = migration_service.build_commit_plan(parsed, overrides=overrides)
        result = migration_service.commit_plan(built, actor=actor)
        audit.record(user=actor, action="migrate", module="migration",
                     entity_type="workbook", entity_id=None,
                     new_value={"created": result["created"],
                                "reused": result["reused"]},
                     remarks="One-time migration from the master workbook")
        db.session.commit()
    except Exception as exc:                      # noqa: BLE001
        db.session.rollback()
        return error_response(f"Migration failed and nothing was written: {exc}", 400)
    finally:
        os.unlink(path)

    return success_response(
        data=result,
        message=(f"Migrated {result['created']['properties']} propert(ies), "
                 f"{result['created']['contracts']} tenanc(ies)"),
    )


@migration_bp.post("/reconcile")
@require_permission("report.view")
def reconcile():
    """The parallel run: the app's month against the workbook's own."""
    path, error = _saved_upload()
    if error:
        return error_response(error, 400)
    raw_month = request.form.get("month")
    month = None
    if raw_month:
        try:
            month = datetime.fromisoformat(
                raw_month if len(raw_month) > 7 else f"{raw_month}-01").date()
        except ValueError:
            os.unlink(path)
            return error_response("month must be YYYY-MM", 400)
    try:
        parsed = migration_service.parse_workbook(path)
        result = migration_service.reconcile(parsed, month=month)
    except Exception as exc:                      # noqa: BLE001
        return error_response(f"Could not reconcile: {exc}", 400)
    finally:
        os.unlink(path)
    return success_response(data=result, meta=result["summary"])
