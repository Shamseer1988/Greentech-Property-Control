"""Generated rental-agreement lifecycle — validates the chosen party has
a signatory on file, assembles the bilingual render context, and turns
a template's clause list into a saved `.docx` attached to that
landlord's or client's record.

Mirrors `services/landlord_contracts.py`'s shape: a caller-visible
`AgreementError`, a gapless numbering helper, and plain functions that
`flush()` but never `commit()` — the route layer commits.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import io

from werkzeug.datastructures import FileStorage

from ..extensions import db
from ..models import Client, GeneratedAgreement, Landlord
from ..models.agreement import AGREEMENT_PARTY_ROLES, CANCELLATION_MODES, FREE_MONTHS_MODES
from . import audit, attachments as attachments_service, numbering, settings as settings_service
from .agreement_documents import build_docx
from .agreement_templates import AGREEMENT_TEMPLATE_REGISTRY, ARABIC_WEEKDAYS, build_clauses


class AgreementError(ValueError):
    """Caller-visible validation failure."""


def _parse_date(value, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        raise AgreementError(f"{field} must be YYYY-MM-DD")


def next_agreement_number() -> str:
    month_key = datetime.utcnow().strftime("%Y%m")
    return numbering.next_number("AGR", month_key, legacy_seed=lambda: 0)


# ----------------------------------------------------------------------
# Party assembly
# ----------------------------------------------------------------------

def _company_party(*, role_label_en: str, role_label_ar: str) -> dict:
    return {
        "name": settings_service.get("company.name") or "",
        "name_ar": settings_service.get("company.name_ar") or "",
        "cr_number": settings_service.get("company.cr_number") or "",
        "signatory_name": settings_service.get("company.signatory_name") or "",
        "signatory_name_ar": settings_service.get("company.signatory_name_ar") or "",
        "signatory_id_number": settings_service.get("company.signatory_id_number") or "",
        "signatory_title": settings_service.get("company.signatory_title") or "",
        "signatory_mobile": settings_service.get("company.contact_phone") or "",
        "mobile": settings_service.get("company.contact_phone") or "",
        "role_label_en": role_label_en, "role_label_ar": role_label_ar,
        "role_label_ar_lam": _lam(role_label_ar),
    }


def _master_party(entity, *, role_label_en: str, role_label_ar: str) -> dict:
    return {
        "name": entity.name or "",
        "name_ar": entity.name_ar or "",
        "cr_number": entity.qid_cr_number or "",
        "signatory_name": entity.signatory_name or "",
        "signatory_name_ar": entity.signatory_name_ar or "",
        "signatory_id_number": entity.signatory_id_number or "",
        "signatory_title": entity.signatory_title or "",
        "signatory_mobile": entity.signatory_mobile or "",
        "mobile": getattr(entity, "mobile", None) or "",
        "role_label_en": role_label_en, "role_label_ar": role_label_ar,
        "role_label_ar_lam": _lam(role_label_ar),
    }


def _lam(role_label_ar: str) -> str:
    """`لـ` + `الX` correctly merges to `للX`, not `لـالX` — a real
    Arabic orthography detail, not cosmetic. Falls back to a plain
    prefix for any label that doesn't start with the definite article."""
    if role_label_ar.startswith("ال"):
        return "لل" + role_label_ar[2:]
    return "لـ" + role_label_ar


def _validate_signatory(entity, label: str) -> None:
    missing = [
        field for field, value in (
            ("signatory name", entity.signatory_name),
            ("signatory Arabic name", entity.signatory_name_ar),
            ("signatory ID number", entity.signatory_id_number),
        ) if not value
    ]
    if missing:
        raise AgreementError(
            f"{label} is missing: {', '.join(missing)}. Fill these in on the "
            f"{label} record before generating an agreement."
        )


def validate_party(*, party_role: str, landlord: Landlord | None, client: Client | None) -> None:
    if party_role not in AGREEMENT_PARTY_ROLES:
        raise AgreementError(f"party_role must be one of {sorted(AGREEMENT_PARTY_ROLES)}")
    if party_role == "landlord":
        if landlord is None:
            raise AgreementError("landlord_id is required for a landlord agreement")
        _validate_signatory(landlord, f"Landlord {landlord.name}")
    else:
        if client is None:
            raise AgreementError("client_id is required for a client agreement")
        _validate_signatory(client, f"Client {client.name}")

    missing_company = [
        field for field, value in (
            ("company signatory name", settings_service.get("company.signatory_name")),
            ("company signatory Arabic name", settings_service.get("company.signatory_name_ar")),
            ("company signatory ID number", settings_service.get("company.signatory_id_number")),
        ) if not value
    ]
    if missing_company:
        raise AgreementError(
            "Company signatory details are missing: " + ", ".join(missing_company) +
            ". Fill these in under Settings → Company before generating an agreement."
        )


# ----------------------------------------------------------------------
# Render context
# ----------------------------------------------------------------------

def build_context(*, party_role: str, landlord: Landlord | None, client: Client | None,
                  rooms_description: str | None, contract_period_months: int | None,
                  start_date: date, end_date: date,
                  electricity_included: bool, water_included: bool,
                  free_months_count: int | None, free_months_mode: str | None,
                  free_months_specific: list[str] | None,
                  deposit_cheque_required: bool,
                  cancellation_mode: str, cancellation_notice_months: int | None,
                  rent_amount, rent_payment_frequency_months: int | None,
                  currency: str | None) -> dict:
    if cancellation_mode not in CANCELLATION_MODES:
        raise AgreementError(f"cancellation_mode must be one of {sorted(CANCELLATION_MODES)}")
    if free_months_mode is not None and free_months_mode not in FREE_MONTHS_MODES:
        raise AgreementError(f"free_months_mode must be one of {sorted(FREE_MONTHS_MODES)}")
    if end_date < start_date:
        raise AgreementError("end_date must be on or after start_date")

    if party_role == "landlord":
        lessor = _master_party(landlord, role_label_en="Lessor", role_label_ar="المؤجر")
        tenant = _company_party(role_label_en="Tenant", role_label_ar="المستأجر")
    else:
        lessor = _company_party(role_label_en="Lessor", role_label_ar="المؤجر")
        tenant = _master_party(client, role_label_en="Tenant", role_label_ar="المستأجر")

    today = date.today()
    return {
        "lessor": lessor, "tenant": tenant,
        "rooms_description": rooms_description or "",
        "contract_period_months": contract_period_months or _months_between(start_date, end_date),
        "start_date_str": start_date.strftime("%d/%m/%Y"),
        "end_date_str": end_date.strftime("%d/%m/%Y"),
        "today_str": today.strftime("%d/%m/%Y"),
        "weekday_ar": ARABIC_WEEKDAYS[today.weekday()],
        "weekday_en": today.strftime("%A"),
        "electricity_included": bool(electricity_included),
        "water_included": bool(water_included),
        "free_months_count": free_months_count or 0,
        "free_months_mode": free_months_mode,
        "free_months_specific_str": ", ".join(free_months_specific or []),
        "deposit_cheque_required": bool(deposit_cheque_required),
        "cancellation_mode": cancellation_mode,
        "cancellation_notice_months": cancellation_notice_months,
        "rent_amount": float(rent_amount) if rent_amount not in (None, "") else 0.0,
        "rent_payment_frequency_months": rent_payment_frequency_months or 1,
        "currency": currency or settings_service.get("company.currency") or "QAR",
    }


def _months_between(start: date, end: date) -> int:
    return max((end.year - start.year) * 12 + (end.month - start.month) + 1, 1)


# ----------------------------------------------------------------------
# Preview / generate / void / regenerate
# ----------------------------------------------------------------------

def preview(*, template_slug: str, **term_kwargs) -> list[dict]:
    """Same code path `generate()` uses for the clause list — a preview
    can never show text the downloaded file doesn't also have."""
    context = build_context(**term_kwargs)
    return build_clauses(template_slug, context)


def generate(*, template_slug: str, party_role: str,
            landlord_id: int | None, client_id: int | None,
            landlord_contract_id: int | None = None, client_contract_id: int | None = None,
            property_id: int | None = None, unit_ids: list[int] | None = None,
            rooms_count: int | None = None, rooms_description: str | None = None,
            start_date, end_date, contract_period_months: int | None = None,
            electricity_included: bool = False, water_included: bool = False,
            free_months_count: int | None = None, free_months_mode: str | None = None,
            free_months_specific: list[str] | None = None,
            deposit_cheque_required: bool = False,
            cancellation_mode: str = "no_cancellation", cancellation_notice_months: int | None = None,
            rent_amount=None, rent_payment_frequency_months: int | None = None,
            currency: str | None = None, remarks: str | None = None,
            actor) -> GeneratedAgreement:
    landlord = Landlord.query.get(landlord_id) if landlord_id else None
    client = Client.query.get(client_id) if client_id else None
    validate_party(party_role=party_role, landlord=landlord, client=client)

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    context = build_context(
        party_role=party_role, landlord=landlord, client=client,
        rooms_description=rooms_description, contract_period_months=contract_period_months,
        start_date=start, end_date=end,
        electricity_included=electricity_included, water_included=water_included,
        free_months_count=free_months_count, free_months_mode=free_months_mode,
        free_months_specific=free_months_specific,
        deposit_cheque_required=deposit_cheque_required,
        cancellation_mode=cancellation_mode, cancellation_notice_months=cancellation_notice_months,
        rent_amount=rent_amount, rent_payment_frequency_months=rent_payment_frequency_months,
        currency=currency,
    )
    clauses = build_clauses(template_slug, context)
    info = AGREEMENT_TEMPLATE_REGISTRY[template_slug]

    agreement = GeneratedAgreement(
        agreement_number=next_agreement_number(),
        template_slug=template_slug, party_role=party_role,
        landlord_id=landlord.id if landlord else None,
        client_id=client.id if client else None,
        landlord_contract_id=landlord_contract_id, client_contract_id=client_contract_id,
        property_id=property_id,
        unit_ids=",".join(str(u) for u in unit_ids) if unit_ids else None,
        rooms_count=rooms_count, rooms_description=rooms_description,
        start_date=start, end_date=end,
        contract_period_months=context["contract_period_months"],
        electricity_included=context["electricity_included"],
        water_included=context["water_included"],
        free_months_count=context["free_months_count"] or None,
        free_months_mode=free_months_mode,
        free_months_specific=",".join(free_months_specific) if free_months_specific else None,
        deposit_cheque_required=context["deposit_cheque_required"],
        cancellation_mode=cancellation_mode,
        cancellation_notice_months=cancellation_notice_months,
        rent_amount=context["rent_amount"] or None,
        rent_payment_frequency_months=context["rent_payment_frequency_months"],
        currency=context["currency"],
        snapshot_json={"lessor": context["lessor"], "tenant": context["tenant"]},
        status="generated",
        remarks=remarks,
        created_by=actor.id, updated_by=actor.id,
    )
    db.session.add(agreement)
    db.session.flush()

    docx_bytes = build_docx(
        title_en=info["title"], title_ar=info["title_ar"],
        agreement_number=agreement.agreement_number,
        context=context, clauses=clauses,
    )
    file_storage = FileStorage(
        stream=io.BytesIO(docx_bytes), filename=f"{agreement.agreement_number}.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    entity_type = "landlord" if party_role == "landlord" else "client"
    entity_id = landlord.id if landlord else client.id
    att = attachments_service.store_file(
        file=file_storage, entity_type=entity_type, entity_id=entity_id,
        category="agreement", actor_id=actor.id, doc_number=agreement.agreement_number,
        trusted_source=True,
    )
    agreement.attachment_id = att.id
    db.session.flush()

    audit.record(user=actor, action="generate", module="agreement",
                 entity_type="generated_agreement", entity_id=agreement.id,
                 new_value=agreement.to_dict(),
                 remarks=f"{agreement.agreement_number} ({template_slug})")
    return agreement


def void(agreement: GeneratedAgreement, *, reason: str, actor) -> GeneratedAgreement:
    if agreement.status == "voided":
        raise AgreementError(f"Agreement {agreement.agreement_number} is already voided")
    if not (reason or "").strip():
        raise AgreementError("reason is required to void an agreement")
    agreement.status = "voided"
    agreement.remarks = f"{agreement.remarks}\nVoided: {reason}" if agreement.remarks else f"Voided: {reason}"
    agreement.updated_by = actor.id
    db.session.flush()
    audit.record(user=actor, action="void", module="agreement",
                 entity_type="generated_agreement", entity_id=agreement.id,
                 old_value={"status": "generated"}, new_value={"status": "voided", "reason": reason})
    return agreement


def regenerate(agreement: GeneratedAgreement, *, actor, **overrides) -> GeneratedAgreement:
    """A fresh agreement carrying this one's terms (any overridden),
    linked back via `superseded_by_id` — the old row is left as-is
    (still a real document that existed), not voided automatically."""
    kwargs = dict(
        template_slug=agreement.template_slug, party_role=agreement.party_role,
        landlord_id=agreement.landlord_id, client_id=agreement.client_id,
        landlord_contract_id=agreement.landlord_contract_id,
        client_contract_id=agreement.client_contract_id,
        property_id=agreement.property_id,
        unit_ids=[int(x) for x in agreement.unit_ids.split(",")] if agreement.unit_ids else None,
        rooms_count=agreement.rooms_count, rooms_description=agreement.rooms_description,
        start_date=agreement.start_date, end_date=agreement.end_date,
        contract_period_months=agreement.contract_period_months,
        electricity_included=agreement.electricity_included, water_included=agreement.water_included,
        free_months_count=agreement.free_months_count, free_months_mode=agreement.free_months_mode,
        free_months_specific=agreement.free_months_specific.split(",") if agreement.free_months_specific else None,
        deposit_cheque_required=agreement.deposit_cheque_required,
        cancellation_mode=agreement.cancellation_mode,
        cancellation_notice_months=agreement.cancellation_notice_months,
        rent_amount=agreement.rent_amount, rent_payment_frequency_months=agreement.rent_payment_frequency_months,
        currency=agreement.currency, remarks=agreement.remarks,
    )
    kwargs.update(overrides)
    new_agreement = generate(actor=actor, **kwargs)
    agreement.superseded_by_id = new_agreement.id
    agreement.updated_by = actor.id
    db.session.flush()
    return new_agreement


def expiring_generated_agreements(*, within_days: int = 60, today: date | None = None) -> list[GeneratedAgreement]:
    """Live agreements (not voided, not already superseded) ending within
    `within_days` — the set bulk_renew() acts on, and what the
    renewals-at-risk dashboard widget displays. Both read from this one
    function so the count shown and the count acted on can never
    disagree."""
    today = today or date.today()
    cutoff = today + timedelta(days=within_days)
    return (
        GeneratedAgreement.query
        .filter(GeneratedAgreement.status == "generated")
        .filter(GeneratedAgreement.superseded_by_id.is_(None))
        .filter(GeneratedAgreement.end_date <= cutoff)
        .order_by(GeneratedAgreement.end_date.asc())
        .all()
    )


def bulk_renew(*, within_days: int = 60, actor) -> dict:
    """Regenerate every expiring, not-yet-superseded agreement with the
    same terms (start/end shift by the same span the original covered),
    following the loop + per-row try/except + one audit entry at the end
    convention already used by services/rent.py::generate_all() and
    services/landlord_rent.py::generate_all()."""
    today = date.today()
    candidates = expiring_generated_agreements(within_days=within_days, today=today)

    renewed, failed = [], []
    for agreement in candidates:
        # A day past the previous end date, running the same length the
        # original term covered — the operator can still hand-edit dates
        # afterward via a single regenerate() call if the renewed term
        # should differ.
        span_days = (agreement.end_date - agreement.start_date).days
        new_start = agreement.end_date + timedelta(days=1)
        new_end = new_start + timedelta(days=span_days)
        try:
            new_agreement = regenerate(
                agreement, actor=actor, start_date=new_start, end_date=new_end)
            renewed.append({
                "old_agreement_id": agreement.id, "old_agreement_number": agreement.agreement_number,
                "new_agreement_id": new_agreement.id, "new_agreement_number": new_agreement.agreement_number,
            })
        except (AgreementError, KeyError) as exc:
            db.session.rollback()
            failed.append({
                "agreement_id": agreement.id, "agreement_number": agreement.agreement_number,
                "error": str(exc),
            })

    if renewed:
        audit.record(user=actor, action="bulk_renew", module="agreement",
                     entity_type="generated_agreement", entity_id=0,
                     new_value={"renewed": len(renewed), "failed": len(failed)},
                     remarks=f"bulk renewal, within {within_days} days")

    return {"renewed": renewed, "failed": failed,
            "renewed_count": len(renewed), "failed_count": len(failed)}
