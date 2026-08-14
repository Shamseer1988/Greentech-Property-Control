"""Client (tenant) route schemas."""
from apiflask import Schema
from apiflask.fields import Date, Integer, String
from apiflask.validators import Length, OneOf

from ..models.client import CLIENT_TYPES, CLIENT_STATUSES


class ClientIn(Schema):
    """POST /clients — only name is required."""
    name = String(required=True, validate=Length(min=1, max=160))
    name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    code = String(required=False)
    client_type = String(required=False, validate=OneOf(sorted(CLIENT_TYPES)))
    contact_person = String(required=False, allow_none=True)
    mobile = String(required=False, allow_none=True)
    alt_mobile = String(required=False, allow_none=True)
    email = String(required=False, allow_none=True)
    address = String(required=False, allow_none=True)
    qid_cr_number = String(required=False, allow_none=True)
    qid_cr_expiry_date = Date(required=False, allow_none=True)
    # The named individual who signs on the client's behalf, for
    # bilingual rental-agreement generation — distinct from qid_cr_number,
    # the company's own CR/QID.
    signatory_name = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_id_number = String(required=False, allow_none=True, validate=Length(max=64))
    signatory_title = String(required=False, allow_none=True, validate=Length(max=80))
    signatory_mobile = String(required=False, allow_none=True, validate=Length(max=32))
    status = String(required=False, validate=OneOf(sorted(CLIENT_STATUSES)))
    remarks = String(required=False, allow_none=True)


class ClientUpdateIn(Schema):
    """PUT /clients/<id> — every field optional."""
    name = String(required=False, validate=Length(min=1, max=160))
    name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    client_type = String(required=False, validate=OneOf(sorted(CLIENT_TYPES)))
    contact_person = String(required=False, allow_none=True)
    mobile = String(required=False, allow_none=True)
    alt_mobile = String(required=False, allow_none=True)
    email = String(required=False, allow_none=True)
    address = String(required=False, allow_none=True)
    qid_cr_number = String(required=False, allow_none=True)
    qid_cr_expiry_date = Date(required=False, allow_none=True)
    signatory_name = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_name_ar = String(required=False, allow_none=True, validate=Length(max=160))
    signatory_id_number = String(required=False, allow_none=True, validate=Length(max=64))
    signatory_title = String(required=False, allow_none=True, validate=Length(max=80))
    signatory_mobile = String(required=False, allow_none=True, validate=Length(max=32))
    status = String(required=False, validate=OneOf(sorted(CLIENT_STATUSES)))
    remarks = String(required=False, allow_none=True)


class ClientOut(Schema):
    """Response contract for OpenAPI. Not attached via @output — see the
    convention note in routes/clients.py."""

    id = Integer()
    code = String()
    name = String()
    name_ar = String(allow_none=True)
    client_type = String()
    contact_person = String(allow_none=True)
    mobile = String(allow_none=True)
    alt_mobile = String(allow_none=True)
    email = String(allow_none=True)
    address = String(allow_none=True)
    qid_cr_number = String(allow_none=True)
    qid_cr_expiry_date = Date(allow_none=True)
    signatory_name = String(allow_none=True)
    signatory_name_ar = String(allow_none=True)
    signatory_id_number = String(allow_none=True)
    signatory_title = String(allow_none=True)
    signatory_mobile = String(allow_none=True)
    status = String()
    remarks = String(allow_none=True)
