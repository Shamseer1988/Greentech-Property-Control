from datetime import date, timedelta

from apiflask import APIBlueprint
from flask import request

from ..extensions import db
from ..models import Landlord
from ..schemas.common import envelope
from ..schemas.landlord import LandlordIn, LandlordUpdateIn, LandlordOut
from ..services import audit, codes
from ..utils.auth import require_permission, current_user
from ..utils.pagination import paginate
from ..utils.responses import success_response, error_response

landlords_bp = APIBlueprint("landlords", __name__)

EDITABLE_FIELDS = {
    "name", "name_ar", "qid_cr_number", "qid_cr_expiry_date",
    "mobile", "email", "address", "contact_person",
    # Agreement-on-landlord fields (Phase 15)
    "agreement_start_date", "agreement_expiry_date", "monthly_rent",
    "reminder_days_before_expiry",
    # Legacy / hidden in UI but still settable via API for migration use
    "bank_name", "iban",
    # The named individual who signs on the landlord's behalf, used by
    # bilingual rental-agreement generation.
    "signatory_name", "signatory_name_ar", "signatory_id_number",
    "signatory_title", "signatory_mobile",
    "status", "remarks",
}





@landlords_bp.get("")
@require_permission("landlord.view")
def list_landlords():
    q = (request.args.get("q") or "").strip().lower()
    status = request.args.get("status")
    expires_within = request.args.get("expires_within", type=int)

    query = Landlord.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                db.func.lower(Landlord.code).like(like),
                db.func.lower(Landlord.name).like(like),
                Landlord.name_ar.like(f"%{q}%"),
                db.func.lower(Landlord.qid_cr_number).like(like),
                db.func.lower(Landlord.mobile).like(like),
            )
        )
    if status:
        query = query.filter(Landlord.status == status)
    if expires_within is not None:
        today = date.today()
        if expires_within < 0:
            # "Expired" — any agreement expiry already in the past.
            query = query.filter(Landlord.agreement_expiry_date < today)
        else:
            query = query.filter(
                Landlord.agreement_expiry_date.isnot(None),
                Landlord.agreement_expiry_date >= today,
                Landlord.agreement_expiry_date <= today + timedelta(days=expires_within),
            )

    rows, meta = paginate(query.order_by(Landlord.name.asc()))
    meta["count"] = len(rows)
    return success_response(data=[r.to_dict() for r in rows], meta=meta)


@landlords_bp.get("/<int:landlord_id>")
@require_permission("landlord.view")
def get_landlord(landlord_id: int):
    return success_response(data=Landlord.query.get_or_404(landlord_id).to_dict())


@landlords_bp.post("")
@require_permission("landlord.create")
@landlords_bp.input(LandlordIn)
def create_landlord(json_data):
    name = json_data["name"].strip()
    actor = current_user()
    code = (json_data.get("code") or "").strip() or codes.next_code(
        Landlord, codes.prefix_for("landlord"),
    )
    if Landlord.query.filter(db.func.lower(Landlord.code) == code.lower()).first():
        return error_response("Code already exists", 409)
    ll = Landlord(code=code, name=name, created_by=actor.id, updated_by=actor.id)
    for k in EDITABLE_FIELDS:
        if k in json_data and k != "name":
            setattr(ll, k, json_data[k])
    db.session.add(ll)
    db.session.flush()
    audit.record(user=actor, action="create", module="landlord",
                 entity_type="landlord", entity_id=ll.id, new_value=ll.to_dict())
    db.session.commit()
    return success_response(data=ll.to_dict(), message="Landlord created", status=201)


@landlords_bp.put("/<int:landlord_id>")
@require_permission("landlord.edit")
@landlords_bp.input(LandlordUpdateIn)
def update_landlord(landlord_id: int, json_data):
    ll = Landlord.query.get_or_404(landlord_id)
    actor = current_user()
    old = ll.to_dict()
    for k in EDITABLE_FIELDS:
        if k in json_data:
            setattr(ll, k, json_data[k])
    ll.updated_by = actor.id
    audit.record(user=actor, action="update", module="landlord",
                 entity_type="landlord", entity_id=ll.id, old_value=old, new_value=ll.to_dict())
    db.session.commit()
    return success_response(data=ll.to_dict(), message="Landlord updated")
