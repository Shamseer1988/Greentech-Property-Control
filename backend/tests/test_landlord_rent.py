"""Landlord dues ledger: charge generation mirrors test_rent.py on the
client side; payment allocation mirrors test_receipts.py."""


def _property_with_agreement(client, auth_headers, *, rent=20000, start="2026-01-01",
                             expiry="2026-12-31", opening=0, **extra):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "LR Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "LR Tower", "property_type": "full_building",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    payload = {
        "landlord_id": landlord["id"], "start_date": start, "expiry_date": expiry,
        "monthly_rent": rent, "opening_balance": opening,
    }
    payload.update(extra)
    resp = client.post(f"/api/v1/properties/{prop['id']}/agreements",
                       headers=auth_headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    agreement = resp.get_json()["data"]
    return landlord, prop, agreement


def _generate(client, auth_headers, upto="2026-12-01", contract_id=None):
    body = {"upto": upto}
    if contract_id:
        body["contract_id"] = contract_id
    return client.post("/api/v1/expenses/landlord-dues/generate",
                       headers=auth_headers, json=body)


def _charges(client, auth_headers, contract_id):
    rows = client.get(f"/api/v1/expenses/landlord-charges?contract_id={contract_id}",
                      headers=auth_headers).get_json()["data"]
    return {r["period_month"]: r for r in rows}


# ------------------------------------------------------------- basics

def test_generates_one_charge_per_month(client, auth_headers):
    _, _, ag = _property_with_agreement(client, auth_headers, rent=5000)
    resp = _generate(client, auth_headers, contract_id=ag["id"])
    assert resp.status_code == 200, resp.get_data(as_text=True)

    charges = _charges(client, auth_headers, ag["id"])
    assert len(charges) == 12
    assert charges["2026-01-01"]["amount"] == 5000
    assert charges["2026-12-01"]["amount"] == 5000
    assert all(v["status"] == "open" for v in charges.values())


def test_generation_is_idempotent(client, auth_headers):
    _, _, ag = _property_with_agreement(client, auth_headers)
    first = _generate(client, auth_headers, contract_id=ag["id"]).get_json()["data"]
    assert first["created"] == 12

    second = _generate(client, auth_headers, contract_id=ag["id"]).get_json()["data"]
    assert second["created"] == 0
    assert second["unchanged"] == 12


def test_contract_with_no_rent_is_skipped_not_raised(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "No Rent Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "No Rent Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    ag = client.post(f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers, json={
        "landlord_id": landlord["id"], "start_date": "2026-01-01", "expiry_date": "2026-12-31",
    }).get_json()["data"]
    assert ag["monthly_rent"] is None

    resp = _generate(client, auth_headers, contract_id=ag["id"])
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _charges(client, auth_headers, ag["id"]) == {}

    totals = client.post("/api/v1/expenses/landlord-dues/generate", headers=auth_headers,
                         json={"upto": "2026-12-01"}).get_json()["data"]
    assert totals["skipped_no_rent"] >= 1


# ------------------------------------------------------------- amendments

def test_rent_change_applies_from_its_month(client, auth_headers):
    _, _, ag = _property_with_agreement(client, auth_headers, rent=28000)
    client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/rent", headers=auth_headers,
               json={"new_rent": 26000, "effective_date": "2026-04-01"})
    _generate(client, auth_headers, contract_id=ag["id"])

    charges = _charges(client, auth_headers, ag["id"])
    assert charges["2026-03-01"]["amount"] == 28000
    assert charges["2026-04-01"]["amount"] == 26000


def test_free_months_are_zero_and_flagged(client, auth_headers):
    _, _, ag = _property_with_agreement(client, auth_headers, rent=5000)
    client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/free-months",
               headers=auth_headers, json={"months": 2, "from_month": "2026-02-01"})
    _generate(client, auth_headers, contract_id=ag["id"])

    charges = _charges(client, auth_headers, ag["id"])
    assert charges["2026-02-01"]["amount"] == 0
    assert charges["2026-02-01"]["is_free_month"] is True
    assert charges["2026-02-01"]["status"] == "paid"
    assert charges["2026-04-01"]["amount"] == 5000


def test_opening_balance_posts_once(client, auth_headers):
    _, _, ag = _property_with_agreement(client, auth_headers, rent=3600, opening=47100)
    _generate(client, auth_headers, contract_id=ag["id"])
    charges = _charges(client, auth_headers, ag["id"])
    assert charges["2025-12-01"]["amount"] == 47100

    again = _generate(client, auth_headers, contract_id=ag["id"]).get_json()["data"]
    assert again["created"] == 0


def test_paid_month_is_never_repriced(client, auth_headers):
    landlord, prop, ag = _property_with_agreement(client, auth_headers, rent=5000)
    _generate(client, auth_headers, contract_id=ag["id"])
    jan = _charges(client, auth_headers, ag["id"])["2026-01-01"]

    client.post("/api/v1/expenses/landlord-payments", headers=auth_headers, json={
        "landlord_id": landlord["id"], "property_id": prop["id"], "period_month": "2026-01-01",
        "amount": 5000, "mode": "cash",
        "allocations": [{"charge_id": jan["id"], "amount": 5000}],
    })

    client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/rent", headers=auth_headers,
               json={"new_rent": 4000, "effective_date": "2026-01-01"})
    counts = _generate(client, auth_headers, contract_id=ag["id"]).get_json()["data"]
    assert counts["skipped_paid"] >= 1


# --------------------------------------------------------- payment allocation

def test_payment_settles_oldest_charge_first(client, auth_headers):
    landlord, prop, ag = _property_with_agreement(client, auth_headers, rent=5000)
    _generate(client, auth_headers, upto="2026-03-01", contract_id=ag["id"])

    resp = client.post("/api/v1/expenses/landlord-payments", headers=auth_headers, json={
        "landlord_id": landlord["id"], "property_id": prop["id"], "period_month": "2026-01-01",
        "amount": 5000, "mode": "cash",
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)

    charges = _charges(client, auth_headers, ag["id"])
    assert charges["2026-01-01"]["status"] == "paid"
    assert charges["2026-01-01"]["outstanding"] == 0
    assert charges["2026-02-01"]["status"] == "open"


def test_partial_payment_leaves_a_balance(client, auth_headers):
    landlord, prop, ag = _property_with_agreement(client, auth_headers, rent=5000)
    _generate(client, auth_headers, upto="2026-01-01", contract_id=ag["id"])

    client.post("/api/v1/expenses/landlord-payments", headers=auth_headers, json={
        "landlord_id": landlord["id"], "property_id": prop["id"], "period_month": "2026-01-01",
        "amount": 2000, "mode": "cash",
    })
    charges = _charges(client, auth_headers, ag["id"])
    assert charges["2026-01-01"]["status"] == "part_paid"
    assert charges["2026-01-01"]["outstanding"] == 3000


def test_void_reopens_the_charge(client, auth_headers):
    landlord, prop, ag = _property_with_agreement(client, auth_headers, rent=5000)
    _generate(client, auth_headers, upto="2026-01-01", contract_id=ag["id"])

    payment = client.post("/api/v1/expenses/landlord-payments", headers=auth_headers, json={
        "landlord_id": landlord["id"], "property_id": prop["id"], "period_month": "2026-01-01",
        "amount": 5000, "mode": "cash",
    }).get_json()["data"]
    assert _charges(client, auth_headers, ag["id"])["2026-01-01"]["status"] == "paid"

    void = client.post(f"/api/v1/expenses/landlord-payments/{payment['id']}/void",
                       headers=auth_headers, json={"reason": "wrong amount"})
    assert void.status_code == 200, void.get_data(as_text=True)

    charges = _charges(client, auth_headers, ag["id"])
    assert charges["2026-01-01"]["status"] == "open"
    assert charges["2026-01-01"]["outstanding"] == 5000


def test_allocation_never_crosses_properties_for_the_same_landlord(client, auth_headers):
    """A landlord with two buildings: a cheque for Building A must never
    settle Building B's arrear — allocation scope is (landlord_id,
    property_id), not landlord alone."""
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Two Building Owner"}).get_json()["data"]
    prop_a = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Building A", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    prop_b = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Building B", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    ag_a = client.post(f"/api/v1/properties/{prop_a['id']}/agreements", headers=auth_headers, json={
        "landlord_id": landlord["id"], "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 5000,
    }).get_json()["data"]
    ag_b = client.post(f"/api/v1/properties/{prop_b['id']}/agreements", headers=auth_headers, json={
        "landlord_id": landlord["id"], "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 7000,
    }).get_json()["data"]
    _generate(client, auth_headers, upto="2026-01-01", contract_id=ag_a["id"])
    _generate(client, auth_headers, upto="2026-01-01", contract_id=ag_b["id"])

    # Pay only Building A's rent — Building B must stay untouched.
    client.post("/api/v1/expenses/landlord-payments", headers=auth_headers, json={
        "landlord_id": landlord["id"], "property_id": prop_a["id"], "period_month": "2026-01-01",
        "amount": 5000, "mode": "cash",
    })

    charges_a = _charges(client, auth_headers, ag_a["id"])
    charges_b = _charges(client, auth_headers, ag_b["id"])
    assert charges_a["2026-01-01"]["status"] == "paid"
    assert charges_b["2026-01-01"]["status"] == "open"
    assert charges_b["2026-01-01"]["outstanding"] == 7000


def test_landlord_dues_endpoints_require_auth(client):
    assert client.get("/api/v1/expenses/landlord-charges").status_code == 401
    assert client.post("/api/v1/expenses/landlord-dues/generate").status_code == 401
