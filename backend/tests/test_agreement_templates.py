"""Agreement clause templates: conditional clause text switches
correctly with the term inputs that drive it."""
from app.services.agreement_templates import build_clauses, list_templates


def _ctx(**overrides):
    base = {
        "lessor": {"role_label_en": "Lessor", "role_label_ar": "المؤجر",
                  "role_label_ar_lam": "للمؤجر", "name": "Owner Co", "name_ar": "شركة المالك"},
        "tenant": {"role_label_en": "Tenant", "role_label_ar": "المستأجر",
                  "role_label_ar_lam": "للمستأجر", "name": "Renter Co", "name_ar": "شركة المستأجر"},
        "rooms_description": "10 rooms", "rooms_description_ar": None,
        "contract_period_months": 12,
        "start_date_str": "01/01/2026", "end_date_str": "31/12/2026",
        "electricity_included": False, "water_included": False,
        "rent_amount": 12000, "rent_payment_frequency_months": 3, "currency": "QAR",
        "deposit_cheque_required": False,
        "free_months_count": 0, "free_months_mode": None, "free_months_specific_str": "",
        "cancellation_mode": "no_cancellation", "cancellation_notice_months": None,
    }
    base.update(overrides)
    return base


def _bodies(clauses, heading_en):
    return next((c for c in clauses if c["heading_en"] and heading_en in c["heading_en"]), None)


def test_lists_the_labour_camp_template():
    templates = list_templates()
    assert any(t["slug"] == "labour-camp-room-rental" for t in templates)
    for_landlord = list_templates(party_role="landlord")
    assert any(t["slug"] == "labour-camp-room-rental" for t in for_landlord)


def test_utilities_clause_reflects_electricity_and_water_flags():
    both = build_clauses("labour-camp-room-rental", _ctx(electricity_included=True, water_included=True))
    rental_both = _bodies(both, "Rental Value")
    assert "electricity, water and sewage consumption" in rental_both["body_en"]

    electricity_only = build_clauses("labour-camp-room-rental",
                                     _ctx(electricity_included=True, water_included=False))
    rental_elec = _bodies(electricity_only, "Rental Value")
    assert "bears the cost of electricity consumption" in rental_elec["body_en"]
    assert "electricity, water and sewage" not in rental_elec["body_en"]

    neither = build_clauses("labour-camp-room-rental", _ctx())
    rental_neither = _bodies(neither, "Rental Value")
    assert "bears the cost of" not in rental_neither["body_en"]


def test_cancellation_clause_switches_between_modes():
    blocked = build_clauses("labour-camp-room-rental", _ctx(cancellation_mode="no_cancellation"))
    c = _bodies(blocked, "Early Termination")
    assert "not permitted before the end" in c["body_en"]
    assert "لا يجوز" in c["body_ar"]

    notice = build_clauses("labour-camp-room-rental",
                           _ctx(cancellation_mode="notice_months", cancellation_notice_months=3))
    c2 = _bodies(notice, "Early Termination")
    assert "at least 3 month(s)" in c2["body_en"]
    assert "3 شهر" in c2["body_ar"]


def test_free_months_clause_absent_when_zero_and_present_when_set():
    zero = build_clauses("labour-camp-room-rental", _ctx(free_months_count=0))
    assert _bodies(zero, "Rent-Free Period") is None

    start = build_clauses("labour-camp-room-rental",
                          _ctx(free_months_count=2, free_months_mode="start"))
    c = _bodies(start, "Rent-Free Period")
    assert "first 2 month(s)" in c["body_en"]

    end = build_clauses("labour-camp-room-rental",
                        _ctx(free_months_count=1, free_months_mode="end"))
    c2 = _bodies(end, "Rent-Free Period")
    assert "last 1 month(s)" in c2["body_en"]

    specific = build_clauses("labour-camp-room-rental", _ctx(
        free_months_count=2, free_months_mode="specific",
        free_months_specific_str="March 2026, April 2026"))
    c3 = _bodies(specific, "Rent-Free Period")
    assert "March 2026, April 2026" in c3["body_en"]


def test_deposit_cheque_clause_only_when_required():
    required = build_clauses("labour-camp-room-rental", _ctx(deposit_cheque_required=True))
    with_cheque = _bodies(required, "Rental Value")
    assert "security cheque" in with_cheque["body_en"]

    not_required = build_clauses("labour-camp-room-rental", _ctx(deposit_cheque_required=False))
    without_cheque = _bodies(not_required, "Rental Value")
    assert "security cheque" not in without_cheque["body_en"]


def test_clauses_are_numbered_sequentially_with_no_gaps():
    clauses = build_clauses("labour-camp-room-rental",
                            _ctx(free_months_count=1, free_months_mode="start"))
    numbered = [c for c in clauses if c["heading_en"] and c["heading_en"][0].isdigit()]
    numbers = [int(c["heading_en"].split(".")[0]) for c in numbered]
    assert numbers == list(range(1, len(numbers) + 1))


def test_role_labels_swap_between_lessor_and_tenant_in_both_languages():
    clauses = build_clauses("labour-camp-room-rental", _ctx())
    lease_term = _bodies(clauses, "Lease Term")
    assert "Owner Co" not in lease_term["body_en"]  # names aren't in this clause, but role labels are
    early_vacate = next(c for c in clauses if c["heading_en"] and "Early Vacate" in c["heading_en"])
    assert "Lessor" in early_vacate["body_en"]
    assert "المؤجر" in early_vacate["body_ar"]
