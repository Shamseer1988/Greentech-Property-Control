"""Landlord route schemas (Phase 4)."""
from apiflask import Schema
from apiflask.fields import Date, Float, Integer, String
from apiflask.validators import Length, OneOf

from ..models.landlord import LANDLORD_STATUSES


class LandlordIn(Schema):
    """POST /landlords — only name is required."""
    name = String(required=True, validate=Length(min=1, max=120))
    name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    code = String(required=False)
    qid_cr_number = String(required=False)
    qid_cr_expiry_date = Date(required=False, allow_none=True)
    mobile = String(required=False)
    email = String(required=False)
    address = String(required=False)
    contact_person = String(required=False)
    agreement_start_date = Date(required=False, allow_none=True)
    agreement_expiry_date = Date(required=False, allow_none=True)
    monthly_rent = Float(required=False, allow_none=True)
    reminder_days_before_expiry = Integer(required=False, load_default=90)
    bank_name = String(required=False)
    iban = String(required=False)
    # The named individual who signs on the landlord's behalf, for
    # bilingual rental-agreement generation — distinct from qid_cr_number,
    # the company's own CR/QID.
    signatory_name = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_id_number = String(required=False, allow_none=True, validate=Length(max=64))
    signatory_title = String(required=False, allow_none=True, validate=Length(max=80))
    signatory_mobile = String(required=False, allow_none=True, validate=Length(max=32))
    status = String(required=False, validate=OneOf(sorted(LANDLORD_STATUSES)))
    remarks = String(required=False)


class LandlordUpdateIn(Schema):
    """PUT /landlords/<id> — all fields optional."""
    name = String(required=False, validate=Length(min=1, max=120))
    name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    qid_cr_number = String(required=False, allow_none=True)
    qid_cr_expiry_date = Date(required=False, allow_none=True)
    mobile = String(required=False, allow_none=True)
    email = String(required=False, allow_none=True)
    address = String(required=False, allow_none=True)
    contact_person = String(required=False, allow_none=True)
    agreement_start_date = Date(required=False, allow_none=True)
    agreement_expiry_date = Date(required=False, allow_none=True)
    monthly_rent = Float(required=False, allow_none=True)
    reminder_days_before_expiry = Integer(required=False)
    bank_name = String(required=False, allow_none=True)
    iban = String(required=False, allow_none=True)
    signatory_name = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_id_number = String(required=False, allow_none=True, validate=Length(max=64))
    signatory_title = String(required=False, allow_none=True, validate=Length(max=80))
    signatory_mobile = String(required=False, allow_none=True, validate=Length(max=32))
    status = String(required=False, validate=OneOf(sorted(LANDLORD_STATUSES)))
    remarks = String(required=False, allow_none=True)


class LandlordOut(Schema):
    id = Integer()
    code = String()
    name = String()
    name_ar = String(allow_none=True)
    qid_cr_number = String(allow_none=True)
    qid_cr_expiry_date = Date(allow_none=True)
    mobile = String(allow_none=True)
    email = String(allow_none=True)
    address = String(allow_none=True)
    contact_person = String(allow_none=True)
    agreement_start_date = Date(allow_none=True)
    agreement_expiry_date = Date(allow_none=True)
    monthly_rent = Float(allow_none=True)
    reminder_days_before_expiry = Integer(allow_none=True)
    signatory_name = String(allow_none=True)
    signatory_name_ar = String(allow_none=True)
    signatory_id_number = String(allow_none=True)
    signatory_title = String(allow_none=True)
    signatory_mobile = String(allow_none=True)
    status = String(allow_none=True)
