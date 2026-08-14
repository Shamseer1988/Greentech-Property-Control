import os
from datetime import datetime
from urllib.parse import quote
from flask import Blueprint, request, send_file, abort

from ..extensions import db
from ..models import Attachment, AttachmentLink, Property, PropertyAgreement, ClientContract
from ..models.attachment import ATTACHMENT_CATEGORIES
from ..services import audit, attachments as att_service
from ..services.attachments import DOWNLOAD_CONTENT_TYPE
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

attachments_bp = Blueprint("attachments", __name__)

ALLOWED_ENTITIES = {
    "property", "property_agreement", "landlord", "client",
    "unit", "client_contract", "cheque", "transaction", "renewal",
}

# Entity types a document can be *also tagged to* on upload, beyond its
# one real owner — a client's doc showing up on the client's contract
# too, or (once Phase 3 lands) a landlord's doc on the landlord contract.
# Keep this to types we can both verify existence for and describe by
# name in `also_on` below; anything else stays owner-only.
LINKABLE_ENTITIES = {"property", "client_contract"}


def _entity_exists(entity_type: str, entity_id: str) -> bool:
    try:
        eid = int(entity_id)
    except (TypeError, ValueError):
        return False
    if entity_type == "property":
        return Property.query.get(eid) is not None
    if entity_type == "client_contract":
        return ClientContract.query.get(eid) is not None
    return False


def _describe_entities(entity_type: str, ids: list[str]) -> dict[str, dict]:
    """Best-effort code/name lookup for a batch of same-type entity ids,
    for the `also_on` display — e.g. {"5": {"code": "PROP-0005", "name": "ST-10"}}."""
    int_ids = []
    for i in ids:
        try:
            int_ids.append(int(i))
        except (TypeError, ValueError):
            continue
    if not int_ids:
        return {}
    if entity_type == "property":
        rows = Property.query.filter(Property.id.in_(int_ids)).all()
        return {str(r.id): {"code": r.code, "name": r.name} for r in rows}
    if entity_type == "client_contract":
        rows = ClientContract.query.filter(ClientContract.id.in_(int_ids)).all()
        return {
            str(r.id): {"code": r.contract_number, "name": r.client.name if r.client else None}
            for r in rows
        }
    if entity_type == "property_agreement":
        rows = PropertyAgreement.query.filter(PropertyAgreement.id.in_(int_ids)).all()
        return {
            str(r.id): {"code": r.agreement_number or f"AG-{r.id}",
                       "name": r.property.name if r.property else None}
            for r in rows
        }
    return {}


def _parse_date(value: str | None, field: str):
    """Empty string and missing both mean "not set"."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD")


@attachments_bp.post("")
@require_permission("attachment.upload")
def upload():
    entity_type = (request.form.get("entity_type") or "").strip()
    entity_id = (request.form.get("entity_id") or "").strip()
    category = request.form.get("category") or None
    remarks = request.form.get("remarks") or None
    doc_number = request.form.get("doc_number") or None
    link_entity_type = (request.form.get("link_entity_type") or "").strip()
    link_entity_id = (request.form.get("link_entity_id") or "").strip()

    if entity_type not in ALLOWED_ENTITIES:
        return error_response(f"Unsupported entity_type. Allowed: {sorted(ALLOWED_ENTITIES)}", 400)
    if not entity_id:
        return error_response("entity_id is required", 400)
    if link_entity_type:
        if link_entity_type not in LINKABLE_ENTITIES:
            return error_response(
                f"Cannot also-tag to '{link_entity_type}'. Allowed: {sorted(LINKABLE_ENTITIES)}", 400)
        if not link_entity_id or not _entity_exists(link_entity_type, link_entity_id):
            return error_response(f"{link_entity_type} link target does not exist", 400)
    if category is not None and category not in ATTACHMENT_CATEGORIES:
        return error_response(
            f"Unsupported category. Allowed: {sorted(ATTACHMENT_CATEGORIES)}", 400)
    if "file" not in request.files:
        return error_response("file is required", 400)
    try:
        issue_date = _parse_date(request.form.get("issue_date"), "issue_date")
        expiry_date = _parse_date(request.form.get("expiry_date"), "expiry_date")
    except ValueError as exc:
        return error_response(str(exc), 400)
    if issue_date and expiry_date and expiry_date < issue_date:
        return error_response("expiry_date must be on or after issue_date", 400)

    actor = current_user()
    try:
        att = att_service.store_file(
            file=request.files["file"],
            entity_type=entity_type,
            entity_id=entity_id,
            category=category,
            actor_id=actor.id,
            remarks=remarks,
            doc_number=doc_number,
            issue_date=issue_date,
            expiry_date=expiry_date,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)

    if link_entity_type and link_entity_id:
        db.session.add(AttachmentLink(
            attachment_id=att.id, entity_type=link_entity_type, entity_id=link_entity_id,
            created_by=actor.id, updated_by=actor.id,
        ))

    audit.record(user=actor, action="upload", module="attachment",
                 entity_type=entity_type, entity_id=entity_id, new_value=att.to_dict(),
                 remarks=category)
    db.session.commit()
    return success_response(data=att.to_dict(), message="Uploaded", status=201)


@attachments_bp.get("")
@require_permission("attachment.view")
def list_attachments():
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id")
    if not entity_type or not entity_id:
        return error_response("entity_type and entity_id are required", 400)

    owned = Attachment.query.filter_by(entity_type=entity_type, entity_id=str(entity_id))
    linked_ids = (
        db.session.query(AttachmentLink.attachment_id)
        .filter_by(entity_type=entity_type, entity_id=str(entity_id))
    )
    linked = Attachment.query.filter(Attachment.id.in_(linked_ids))

    rows = owned.union(linked).order_by(Attachment.id.desc()).all()

    # Tell the UI which of an attachment's OTHER homes it's also tagged
    # to, so a landlord-uploaded doc shown here can say "also on PROP-0002".
    all_links = (
        AttachmentLink.query
        .filter(AttachmentLink.attachment_id.in_([r.id for r in rows]))
        .all()
    ) if rows else []
    # Drop the link back to the entity we're currently viewing — that's
    # "here", not an "also on".
    all_links = [
        l for l in all_links
        if not (l.entity_type == entity_type and l.entity_id == str(entity_id))
    ]

    ids_by_type: dict[str, list[str]] = {}
    for link in all_links:
        ids_by_type.setdefault(link.entity_type, []).append(link.entity_id)
    described_by_type = {
        etype: _describe_entities(etype, ids) for etype, ids in ids_by_type.items()
    }

    links_by_attachment: dict[int, list[dict]] = {}
    for link in all_links:
        info = described_by_type.get(link.entity_type, {}).get(link.entity_id)
        if info is None:
            continue
        links_by_attachment.setdefault(link.attachment_id, []).append(
            {"entity_type": link.entity_type, **info})

    data = []
    for r in rows:
        d = r.to_dict()
        d["also_on"] = links_by_attachment.get(r.id, [])
        data.append(d)
    return success_response(data=data, meta={"count": len(rows)})


@attachments_bp.get("/<int:att_id>/download")
@require_permission("attachment.view")
def download(att_id: int):
    att = Attachment.query.get_or_404(att_id)
    path = att_service.absolute_path(att)
    if not os.path.exists(path):
        abort(404)
    # Force application/octet-stream and an explicit attachment
    # disposition so a stored text/html / SVG legacy row can never
    # render inline. X-Content-Type-Options: nosniff is already
    # applied globally by the Phase 2 after_request hook.
    resp = send_file(
        path,
        mimetype=DOWNLOAD_CONTENT_TYPE,
        as_attachment=True,
        download_name=att.original_name,
    )
    safe_name = quote(att.original_name)
    resp.headers["Content-Type"] = DOWNLOAD_CONTENT_TYPE
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=\"{safe_name}\"; filename*=UTF-8''{safe_name}"
    )
    return resp


@attachments_bp.delete("/<int:att_id>")
@require_permission("attachment.upload")
def delete(att_id: int):
    att = Attachment.query.get_or_404(att_id)
    actor = current_user()
    audit.record(user=actor, action="delete", module="attachment",
                 entity_type=att.entity_type, entity_id=att.entity_id,
                 old_value=att.to_dict())
    att_service.delete_file(att)
    db.session.commit()
    return success_response(message="Deleted")
