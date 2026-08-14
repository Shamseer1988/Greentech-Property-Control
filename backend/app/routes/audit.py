from datetime import datetime, timedelta

from flask import Blueprint, request
from sqlalchemy import func

from ..extensions import db
from ..models import AuditLog
from ..utils.auth import require_permission
from ..utils.pagination import paginate
from ..utils.responses import success_response

audit_bp = Blueprint("audit", __name__)


# Fields stored on every entity that aren't part of the user's mental
# model of the row — hide them from the diff to reduce noise.
_DIFF_IGNORE = {"id", "created_at", "updated_at", "created_by", "updated_by"}


def _compute_diff(old, new) -> list[dict] | None:
    """Build a [{field, before, after}, ...] list of fields that actually
    changed. Returns None when there's nothing to compare (e.g. a
    create or delete row carrying only one side)."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return None
    diff: list[dict] = []
    keys = (set(old.keys()) | set(new.keys())) - _DIFF_IGNORE
    for k in sorted(keys):
        before = old.get(k)
        after = new.get(k)
        if before == after:
            continue
        diff.append({"field": k, "before": before, "after": after})
    return diff


def _parse_day(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


@audit_bp.get("")
@require_permission("audit.view")
def list_audit():
    module = request.args.get("module")
    action = request.args.get("action")
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id")
    user_id = request.args.get("user_id", type=int)
    date_from = _parse_day(request.args.get("date_from"))
    date_to = _parse_day(request.args.get("date_to"))

    query = AuditLog.query
    if module:
        query = query.filter_by(module=module)
    if action:
        query = query.filter_by(action=action)
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    if entity_id:
        query = query.filter_by(entity_id=str(entity_id))
    if user_id:
        query = query.filter_by(user_id=user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.combine(
            date_from, datetime.min.time()))
    if date_to:
        # Inclusive of the whole end day — an operator picking "3 Aug"
        # means everything that happened on the 3rd, not up to midnight.
        query = query.filter(AuditLog.created_at < datetime.combine(
            date_to + timedelta(days=1), datetime.min.time()))

    rows, meta = paginate(query.order_by(AuditLog.id.desc()),
                          default_per_page=100, max_per_page=500)
    out: list[dict] = []
    for r in rows:
        d = r.to_dict()
        # Compute changed-fields server-side so every client renders the
        # same set without diffing JSON in JS. Any action that recorded
        # both sides gets a diff — not just "update", because the
        # interesting ones are named for what they did (amend, cancel,
        # void, approve).
        d["diff"] = _compute_diff(r.old_value, r.new_value)
        out.append(d)
    meta["count"] = len(out)
    return success_response(data=out, meta=meta)


@audit_bp.get("/facets")
@require_permission("audit.view")
def facets():
    """The distinct values actually present in the log, so the viewer's
    filters offer what exists rather than a hardcoded list that drifts
    as modules are added."""
    def distinct(column):
        return sorted(
            v for (v,) in db.session.query(column).distinct().all() if v
        )

    users = (
        db.session.query(AuditLog.user_id, AuditLog.username,
                         func.count(AuditLog.id))
        .group_by(AuditLog.user_id, AuditLog.username)
        .all()
    )
    return success_response(data={
        "modules": distinct(AuditLog.module),
        "actions": distinct(AuditLog.action),
        "users": [
            {"user_id": uid, "username": name, "count": int(n)}
            for uid, name, n in sorted(users, key=lambda r: (r[1] or ""))
            if name
        ],
    })
