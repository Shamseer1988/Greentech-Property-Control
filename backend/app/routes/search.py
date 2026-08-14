"""Global search endpoint — Cmd-K style typeahead across the main
entities the operator interacts with. Permission-gated per entity type.

Clients and contracts join the result groups in Phases 1-2."""
from flask import Blueprint, request

from ..extensions import db
from ..models import Property, Unit, Landlord, Client, ClientContract, GeneratedAgreement
from ..utils.auth import login_required, current_user
from ..utils.responses import success_response


search_bp = Blueprint("search", __name__)

LIMIT_PER_GROUP = 5


def _can(user, code: str) -> bool:
    return user.is_super_user or user.has_permission(code)


@search_bp.get("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return success_response(data={
            "properties": [], "units": [], "landlords": [], "clients": [],
            "contracts": [], "agreements": [],
        }, meta={"q": q, "min_chars": 2})

    user = current_user()
    like = f"%{q.lower()}%"

    properties: list[dict] = []
    if _can(user, "property.view"):
        rows = (
            Property.query
            .filter(
                db.or_(
                    db.func.lower(Property.code).like(like),
                    db.func.lower(Property.name).like(like),
                    db.func.lower(Property.area).like(like),
                    db.func.lower(Property.city).like(like),
                )
            )
            .order_by(Property.name.asc())
            .limit(LIMIT_PER_GROUP).all()
        )
        properties = [{
            "id": p.id, "code": p.code, "label": p.name,
            "sublabel": " · ".join(
                x for x in [p.code, (p.property_type or "").replace("_", " "),
                            ", ".join(y for y in [p.area, p.city] if y)] if x
            ),
            "href": f"/properties/{p.id}",
        } for p in rows]

    units: list[dict] = []
    if _can(user, "unit.view"):
        rows = (
            db.session.query(Unit).join(Property, Unit.property_id == Property.id)
            .filter(db.func.lower(Unit.unit_number).like(like))
            .order_by(Property.name.asc(), Unit.unit_number.asc())
            .limit(LIMIT_PER_GROUP).all()
        )
        units = [{
            "id": u.id, "code": u.unit_number,
            "label": f"Unit {u.unit_number}",
            "sublabel": f"{u.property.name if u.property else ''} · {(u.unit_type or '').replace('_', ' ')}",
            "href": f"/properties/{u.property_id}",
        } for u in rows]

    landlords: list[dict] = []
    if _can(user, "landlord.view"):
        rows = (
            Landlord.query
            .filter(
                db.or_(
                    db.func.lower(Landlord.code).like(like),
                    db.func.lower(Landlord.name).like(like),
                    db.func.lower(Landlord.qid_cr_number).like(like),
                )
            )
            .order_by(Landlord.name.asc())
            .limit(LIMIT_PER_GROUP).all()
        )
        landlords = [{
            "id": l.id, "code": l.code, "label": l.name,
            "sublabel": " · ".join(x for x in [l.code, l.qid_cr_number, l.mobile] if x),
            "href": "/landlords",  # no detail page; list with row highlight
        } for l in rows]

    clients: list[dict] = []
    if _can(user, "client.view"):
        rows = (
            Client.query
            .filter(
                db.or_(
                    db.func.lower(Client.code).like(like),
                    db.func.lower(Client.name).like(like),
                    Client.name_ar.like(f"%{q}%"),
                    db.func.lower(Client.qid_cr_number).like(like),
                    db.func.lower(Client.mobile).like(like),
                )
            )
            .order_by(Client.name.asc())
            .limit(LIMIT_PER_GROUP).all()
        )
        clients = [{
            "id": c.id, "code": c.code, "label": c.name,
            "sublabel": " · ".join(x for x in [c.code, c.qid_cr_number, c.mobile] if x),
            "href": "/clients",
        } for c in rows]

    # Client and agreement numbers are the two identifiers people actually
    # search by that neither of the two blocks above could find — a
    # contract number or agreement number isn't a name, code or QID/CR.
    contracts: list[dict] = []
    if _can(user, "contract.view"):
        rows = (
            ClientContract.query
            .filter(db.func.lower(ClientContract.contract_number).like(like))
            .order_by(ClientContract.contract_number.desc())
            .limit(LIMIT_PER_GROUP).all()
        )
        contracts = [{
            "id": c.id, "code": c.contract_number, "label": c.contract_number,
            "sublabel": " · ".join(x for x in [
                c.client.name if c.client else None,
                c.property.name if c.property else None] if x),
            "href": f"/contracts/{c.id}",
        } for c in rows]

    agreements: list[dict] = []
    if _can(user, "agreement.view"):
        rows = (
            GeneratedAgreement.query
            .filter(db.func.lower(GeneratedAgreement.agreement_number).like(like))
            .order_by(GeneratedAgreement.agreement_number.desc())
            .limit(LIMIT_PER_GROUP).all()
        )
        agreements = [{
            "id": a.id, "code": a.agreement_number, "label": a.agreement_number,
            "sublabel": (a.landlord.name if a.party_role == "landlord" and a.landlord
                        else a.client.name if a.client else None) or "",
            "href": "/agreements",
        } for a in rows]

    total = sum(len(g) for g in (properties, units, landlords, clients, contracts, agreements))
    return success_response(
        data={
            "properties": properties, "units": units,
            "landlords": landlords, "clients": clients,
            "contracts": contracts, "agreements": agreements,
        },
        meta={"q": q, "total": total, "limit_per_group": LIMIT_PER_GROUP},
    )
