from datetime import date, datetime

from ..extensions import db
from ..models import (
    Property, Landlord, PropertyAgreement, LandlordRenewal,
)
from ..models.renewal_maintenance import generate_renewal_or_maintenance_number


class RenewalError(ValueError):
    pass


def _parse_date(value, fallback: date | None = None) -> date | None:
    if value is None or value == "":
        return fallback
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value)).date()


def post_renewal(
    *,
    property_id: int,
    landlord_id: int,
    new_start_date,
    new_expiry_date,
    new_monthly_rent=None,
    agreement_number: str | None = None,
    payment_terms: str | None = None,
    notice_period: str | None = None,
    reminder_days_before_expiry: int = 90,
    security_deposit=None,
    kahramaa_account: str | None = None,
    municipality_ref: str | None = None,
    remarks: str | None = None,
    approved_by: int | None = None,
    actor_id: int,
) -> LandlordRenewal:
    """Post a landlord agreement renewal.

    Honours the ``approval.renewal.required`` system setting:
      - If approval is required the renewal row is created with
        ``status="pending_approval"`` and the existing active agreement
        is **not** archived yet. An ``ApprovalRequest`` row is added.
      - Otherwise the old agreement is archived and the new one is created
        immediately (current behaviour).
    """
    from . import approvals as approval_service
    from . import settings as settings_service

    prop = Property.query.get(property_id)
    if prop is None:
        raise RenewalError("Property not found")
    landlord = Landlord.query.get(landlord_id)
    if landlord is None:
        raise RenewalError("Landlord not found")

    start = _parse_date(new_start_date)
    expiry = _parse_date(new_expiry_date)
    if not start or not expiry:
        raise RenewalError("new_start_date and new_expiry_date are required")
    if expiry < start:
        raise RenewalError("new_expiry_date must be on or after new_start_date")

    needs_approval = settings_service.get_bool("approval.renewal.required", False)

    previous = (
        PropertyAgreement.query
        .filter_by(property_id=prop.id, is_active=True)
        .all()
    )
    old_agreement = previous[0] if previous else None

    renewal = LandlordRenewal(
        transaction_number=generate_renewal_or_maintenance_number("LRENEW"),
        property_id=prop.id,
        landlord_id=landlord.id,
        old_agreement_id=old_agreement.id if old_agreement else None,
        new_agreement_id=None,
        renewal_date=date.today(),
        old_expiry_date=old_agreement.expiry_date if old_agreement else None,
        new_start_date=start,
        new_expiry_date=expiry,
        old_monthly_rent=old_agreement.monthly_rent if old_agreement else None,
        new_monthly_rent=new_monthly_rent,
        remarks=remarks,
        approved_by=approved_by,
        status="pending_approval" if needs_approval else "completed",
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.session.add(renewal)
    db.session.flush()

    # Stash unstored fields for later in flight-mode (on a transient attribute)
    renewal._draft_agreement_number = agreement_number
    renewal._draft_payment_terms = payment_terms
    renewal._draft_notice_period = notice_period
    renewal._draft_reminder_days = int(reminder_days_before_expiry or 90)
    renewal._draft_security_deposit = security_deposit
    renewal._draft_kahramaa_account = kahramaa_account
    renewal._draft_municipality_ref = municipality_ref

    if needs_approval:
        # Persist the draft into the renewal.remarks JSON-ish field via a
        # secondary stash so finalize can reconstitute it. Cleanest:
        # encode into remarks separated by markers — but we already have
        # remarks. Use a tiny side table? Overkill. Simply pass-through
        # via session state: we'll persist the fields into the
        # corresponding PropertyAgreement at finalize time using the
        # values stored on the renewal row itself.
        import json
        extras = {
            "agreement_number": agreement_number,
            "payment_terms": payment_terms,
            "notice_period": notice_period,
            "reminder_days_before_expiry": int(reminder_days_before_expiry or 90),
            "security_deposit": float(security_deposit) if security_deposit is not None else None,
            "kahramaa_account": kahramaa_account,
            "municipality_ref": municipality_ref,
        }
        # Encode extras as a comment line in remarks so we can read it back
        marker = "\n[draft]" + json.dumps(extras)
        renewal.remarks = (renewal.remarks or "") + marker
        db.session.flush()
        approval_service.create_request(
            module="renewal", entity=renewal, actor_id=actor_id,
            summary=f"Renew {prop.name} with {landlord.name} until {expiry.isoformat()}",
        )
        return renewal

    new_agreement = _create_new_agreement(
        prop=prop, landlord=landlord, start=start, expiry=expiry,
        agreement_number=agreement_number, monthly_rent=new_monthly_rent,
        security_deposit=security_deposit, payment_terms=payment_terms,
        notice_period=notice_period, reminder_days_before_expiry=reminder_days_before_expiry,
        kahramaa_account=kahramaa_account, municipality_ref=municipality_ref,
        remarks=remarks, actor_id=actor_id,
    )
    for p in previous:
        p.status = "renewed"
        p.renewal_status = "renewed"
        p.updated_by = actor_id
    if previous:
        _carry_units_and_record_renewal(previous[0], new_agreement, actor_id=actor_id)
    renewal.new_agreement_id = new_agreement.id
    db.session.flush()
    return renewal


def _create_new_agreement(*, prop, landlord, start, expiry, agreement_number,
                          monthly_rent, security_deposit, payment_terms, notice_period,
                          reminder_days_before_expiry, kahramaa_account, municipality_ref,
                          remarks, actor_id) -> PropertyAgreement:
    from .landlord_contracts import next_landlord_contract_number

    new_agreement = PropertyAgreement(
        property_id=prop.id,
        landlord_id=landlord.id,
        contract_number=next_landlord_contract_number(),
        agreement_number=agreement_number,
        start_date=start,
        expiry_date=expiry,
        monthly_rent=monthly_rent,
        security_deposit=security_deposit,
        payment_terms=payment_terms,
        notice_period=notice_period,
        renewal_status="pending",
        kahramaa_account=kahramaa_account,
        municipality_ref=municipality_ref,
        reminder_days_before_expiry=int(reminder_days_before_expiry or 90),
        remarks=remarks,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.session.add(new_agreement)
    db.session.flush()
    return new_agreement


def _carry_units_and_record_renewal(old_agreement: PropertyAgreement,
                                    new_agreement: PropertyAgreement, *, actor_id: int) -> None:
    """Move active unit allocations from the old landlord contract to
    the new one, closing the old rows the day before the new term
    starts — mirrors `services.contracts.renew_contract` on the client
    side. Also writes a `renewal` amendment on the OLD contract (the
    new one has no history yet); `renewed_to_id` links the two."""
    from datetime import timedelta
    from ..models import LandlordContractUnit, LandlordContractAmendment
    from .landlord_contracts import next_amendment_number

    old_agreement.renewed_to_id = new_agreement.id

    carried = old_agreement.active_allocations(old_agreement.expiry_date)
    if carried:
        handover = new_agreement.start_date - timedelta(days=1)
        for allocation in carried:
            allocation.to_date = handover
            allocation.updated_by = actor_id
        db.session.flush()

        for allocation in carried:
            db.session.add(LandlordContractUnit(
                contract_id=new_agreement.id, unit_id=allocation.unit_id,
                from_date=new_agreement.start_date, unit_rent=allocation.unit_rent,
                created_by=actor_id, updated_by=actor_id,
            ))

    sequence = len(old_agreement.amendments or []) + 1
    db.session.add(LandlordContractAmendment(
        contract_id=old_agreement.id,
        amendment_number=next_amendment_number(),
        sequence=sequence,
        amendment_type="renewal",
        effective_date=new_agreement.start_date,
        old_rent=old_agreement.monthly_rent,
        new_rent=new_agreement.monthly_rent,
        unit_ids=",".join(str(a.unit_id) for a in carried) if carried else None,
        remarks=f"renewed as {new_agreement.contract_number}",
        created_by=actor_id, updated_by=actor_id,
    ))
    db.session.flush()


def finalize_pending_renewal(renewal: LandlordRenewal, *, actor_id: int) -> LandlordRenewal:
    if renewal.status != "pending_approval":
        raise RenewalError(f"Renewal is {renewal.status}, not pending_approval")

    import json
    extras = {}
    if renewal.remarks:
        marker = "\n[draft]"
        idx = renewal.remarks.find(marker)
        if idx >= 0:
            try:
                extras = json.loads(renewal.remarks[idx + len(marker):])
            except (json.JSONDecodeError, ValueError):
                extras = {}
            renewal.remarks = renewal.remarks[:idx].rstrip() or None

    new_agreement = _create_new_agreement(
        prop=renewal.property,
        landlord=renewal.landlord,
        start=renewal.new_start_date,
        expiry=renewal.new_expiry_date,
        agreement_number=extras.get("agreement_number"),
        monthly_rent=renewal.new_monthly_rent,
        security_deposit=extras.get("security_deposit"),
        payment_terms=extras.get("payment_terms"),
        notice_period=extras.get("notice_period"),
        reminder_days_before_expiry=extras.get("reminder_days_before_expiry", 90),
        kahramaa_account=extras.get("kahramaa_account"),
        municipality_ref=extras.get("municipality_ref"),
        remarks=renewal.remarks,
        actor_id=actor_id,
    )

    # Archive the active agreement(s) now that the renewal is approved
    previous = (
        PropertyAgreement.query
        .filter_by(property_id=renewal.property_id, is_active=True)
        .filter(PropertyAgreement.id != new_agreement.id)
        .all()
    )
    for p in previous:
        p.status = "renewed"
        p.renewal_status = "renewed"
        p.updated_by = actor_id
    if previous:
        _carry_units_and_record_renewal(previous[0], new_agreement, actor_id=actor_id)

    renewal.new_agreement_id = new_agreement.id
    renewal.status = "completed"
    renewal.updated_by = actor_id
    db.session.flush()
    return renewal
