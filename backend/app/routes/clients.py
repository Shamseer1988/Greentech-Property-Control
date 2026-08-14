"""Client master — the tenants GreenTech lets units to.

Client contracts (unit allocation, rent, mode, PDC cheques) land in
Phase 2 and reference these rows.

Convention note: apiflask's ``@output`` would serialize the return value
and replace the ``{success, message, data, meta}`` envelope the frontend
expects, so — as in ``routes/landlords.py`` — we validate the request
with ``@input`` and build the response with ``success_response()``.
"""
from apiflask import APIBlueprint
from flask import request

from ..extensions import db
from ..models import Client
from ..schemas.client import ClientIn, ClientUpdateIn
from ..services import audit, codes
from ..utils.auth import require_permission, current_user
from ..utils.pagination import paginate
from ..utils.responses import success_response, error_response

clients_bp = APIBlueprint("clients", __name__)

EDITABLE_FIELDS = {
    "name", "name_ar", "client_type", "contact_person", "mobile", "alt_mobile",
    "email", "address", "qid_cr_number", "qid_cr_expiry_date",
    # The named individual who signs on the client's behalf, used by
    # bilingual rental-agreement generation.
    "signatory_name", "signatory_name_ar", "signatory_id_number",
    "signatory_title", "signatory_mobile",
    "status", "remarks",
}


@clients_bp.get("")
@require_permission("client.view")
def list_clients():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status")
    query = Client.query
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(Client.code).like(like),
                db.func.lower(Client.name).like(like),
                Client.name_ar.like(f"%{q}%"),  # Arabic has no case folding
                db.func.lower(Client.qid_cr_number).like(like),
                db.func.lower(Client.mobile).like(like),
                db.func.lower(Client.contact_person).like(like),
            )
        )
    if status:
        query = query.filter_by(status=status)
    rows, meta = paginate(query.order_by(Client.name.asc()))
    meta["count"] = len(rows)
    return success_response(data=[r.to_dict() for r in rows], meta=meta)


@clients_bp.get("/<int:client_id>")
@require_permission("client.view")
def get_client(client_id: int):
    return success_response(data=Client.query.get_or_404(client_id).to_dict())


@clients_bp.post("")
@require_permission("client.create")
@clients_bp.input(ClientIn)
def create_client(json_data):
    name = json_data["name"].strip()
    actor = current_user()
    code = (json_data.get("code") or "").strip() or codes.next_code(
        Client, codes.prefix_for("client"),
    )
    if Client.query.filter(db.func.lower(Client.code) == code.lower()).first():
        return error_response("Code already exists", 409)

    client = Client(code=code, name=name, created_by=actor.id, updated_by=actor.id)
    for k in EDITABLE_FIELDS:
        if k in json_data and k != "name":
            setattr(client, k, json_data[k])
    db.session.add(client)
    db.session.flush()
    audit.record(user=actor, action="create", module="client",
                 entity_type="client", entity_id=client.id, new_value=client.to_dict())
    db.session.commit()
    return success_response(data=client.to_dict(), message="Client created", status=201)


@clients_bp.put("/<int:client_id>")
@require_permission("client.edit")
@clients_bp.input(ClientUpdateIn)
def update_client(client_id: int, json_data):
    client = Client.query.get_or_404(client_id)
    actor = current_user()
    old = client.to_dict()
    for k in EDITABLE_FIELDS:
        if k in json_data:
            setattr(client, k, json_data[k])
    client.updated_by = actor.id
    audit.record(user=actor, action="update", module="client",
                 entity_type="client", entity_id=client.id,
                 old_value=old, new_value=client.to_dict())
    db.session.commit()
    return success_response(data=client.to_dict(), message="Client updated")
