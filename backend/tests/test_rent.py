"""Rent schedule generation: the rent actually in force, month by month."""
from datetime import date


def _setup(client, auth_headers, *, rent=5000, start="2026-01-01", expiry="2026-12-31",
           mode="cash", opening=0, units=1):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Rent LL"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Rent Tower", "property_type": "full_building",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 6},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Rent Client"}).get_json()["data"]
    all_units = client.get(f"/api/v1/properties/{prop['id']}/units",
                           headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [u["id"] for u in all_units[:units]],
        "start_date": start, "expiry_date": expiry,
        "monthly_rent": rent, "payment_mode": mode, "opening_balance": opening,
    }).get_json()["data"]
    return prop, tenant, contract


def _generate(client, auth_headers, upto="2026-12-01", contract_id=None):
    body = {"upto": upto}
    if contract_id:
        body["contract_id"] = contract_id
    return client.post("/api/v1/rent/generate", headers=auth_headers, json=body)


def _charges(client, auth_headers, contract_id):
    rows = client.get(f"/api/v1/rent/charges?contract_id={contract_id}",
                      headers=auth_headers).get_json()["data"]
    return {r["period_month"]: r for r in rows}


# ------------------------------------------------------------- basics

def test_generates_one_charge_per_month(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=5000)
    resp = _generate(client, auth_headers, contract_id=c["id"])
    assert resp.status_code == 200, resp.get_data(as_text=True)

    charges = _charges(client, auth_headers, c["id"])
    assert len(charges) == 12
    assert charges["2026-01-01"]["amount"] == 5000
    assert charges["2026-12-01"]["amount"] == 5000
    assert all(v["status"] == "open" for v in charges.values())


def test_generation_is_idempotent(client, auth_headers):
    _, _, c = _setup(client, auth_headers)
    first = _generate(client, auth_headers, contract_id=c["id"]).get_json()["data"]
    assert first["created"] == 12

    second = _generate(client, auth_headers, contract_id=c["id"]).get_json()["data"]
    assert second["created"] == 0
    assert second["unchanged"] == 12
    assert len(_charges(client, auth_headers, c["id"])) == 12


def test_only_generates_up_to_the_requested_month(client, auth_headers):
    _, _, c = _setup(client, auth_headers)
    _generate(client, auth_headers, upto="2026-03-01", contract_id=c["id"])
    charges = _charges(client, auth_headers, c["id"])
    assert sorted(charges) == ["2026-01-01", "2026-02-01", "2026-03-01"]


# ------------------------------------------------------- rent changes

def test_rent_change_applies_from_its_month(client, auth_headers):
    """28,000 until March, 26,000 from April — the master-file case."""
    _, _, c = _setup(client, auth_headers, rent=28000)
    client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                json={"new_rent": 26000, "effective_date": "2026-04-01"})
    _generate(client, auth_headers, contract_id=c["id"])

    charges = _charges(client, auth_headers, c["id"])
    assert charges["2026-01-01"]["amount"] == 28000
    assert charges["2026-03-01"]["amount"] == 28000
    assert charges["2026-04-01"]["amount"] == 26000
    assert charges["2026-12-01"]["amount"] == 26000


def test_mid_month_rent_change_applies_to_that_whole_month(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=10000)
    client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                json={"new_rent": 9000, "effective_date": "2026-04-15"})
    _generate(client, auth_headers, contract_id=c["id"])
    charges = _charges(client, auth_headers, c["id"])
    assert charges["2026-03-01"]["amount"] == 10000
    assert charges["2026-04-01"]["amount"] == 9000


def test_two_rent_changes_apply_in_order(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=5000)
    client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                json={"new_rent": 5500, "effective_date": "2026-04-01"})
    client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                json={"new_rent": 6000, "effective_date": "2026-09-01"})
    _generate(client, auth_headers, contract_id=c["id"])

    charges = _charges(client, auth_headers, c["id"])
    assert charges["2026-02-01"]["amount"] == 5000
    assert charges["2026-05-01"]["amount"] == 5500
    assert charges["2026-10-01"]["amount"] == 6000


def test_regeneration_after_a_rent_change_updates_unpaid_months(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=5000)
    _generate(client, auth_headers, contract_id=c["id"])
    client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                json={"new_rent": 4000, "effective_date": "2026-06-01"})
    again = _generate(client, auth_headers, contract_id=c["id"]).get_json()["data"]
    assert again["updated"] == 7, "Jun-Dec re-priced"

    charges = _charges(client, auth_headers, c["id"])
    assert charges["2026-05-01"]["amount"] == 5000
    assert charges["2026-06-01"]["amount"] == 4000


# -------------------------------------------------------- free months

def test_free_months_are_zero_and_flagged(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=5000)
    client.post(f"/api/v1/contracts/{c['id']}/amendments/free-months", headers=auth_headers,
                json={"months": 2, "from_month": "2026-02-01"})
    _generate(client, auth_headers, contract_id=c["id"])

    charges = _charges(client, auth_headers, c["id"])
    assert charges["2026-01-01"]["amount"] == 5000
    assert charges["2026-02-01"]["amount"] == 0
    assert charges["2026-02-01"]["is_free_month"] is True
    assert charges["2026-02-01"]["status"] == "paid", "nothing to collect"
    assert charges["2026-03-01"]["amount"] == 0
    assert charges["2026-04-01"]["amount"] == 5000


# ------------------------------------------------------------ pro-rata

def test_mid_month_start_is_prorated(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=3100, start="2026-01-21",
                     expiry="2026-12-31")
    _generate(client, auth_headers, contract_id=c["id"])
    charges = _charges(client, auth_headers, c["id"])
    # 11 of 31 days.
    assert charges["2026-01-01"]["amount"] == 1100.0
    assert "11/31 days" in charges["2026-01-01"]["proration_note"]
    assert charges["2026-02-01"]["amount"] == 3100


def test_cancellation_prorates_the_final_month_and_stops(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=3000)
    client.post(f"/api/v1/contracts/{c['id']}/cancel", headers=auth_headers,
                json={"effective_date": "2026-05-10", "reason": "vacated"})
    _generate(client, auth_headers, contract_id=c["id"])

    charges = _charges(client, auth_headers, c["id"])
    assert sorted(charges)[-1] == "2026-05-01", "no charges after cancellation"
    assert charges["2026-04-01"]["amount"] == 3000
    # 10 of 31 days of May.
    assert charges["2026-05-01"]["amount"] == round(3000 * 10 / 31, 2)


# ------------------------------------------------------ opening balance

def test_opening_balance_posts_once_before_the_first_month(client, auth_headers):
    _, _, c = _setup(client, auth_headers, rent=3600, opening=47100)
    _generate(client, auth_headers, contract_id=c["id"])

    charges = _charges(client, auth_headers, c["id"])
    assert "2025-12-01" in charges, "dated the month before the contract starts"
    opening = charges["2025-12-01"]
    assert opening["amount"] == 47100
    assert opening["is_opening_balance"] is True

    again = _generate(client, auth_headers, contract_id=c["id"]).get_json()["data"]
    assert again["created"] == 0, "opening balance is not posted twice"


# --------------------------------------------------------- protections

def test_paid_month_is_never_repriced(client, auth_headers):
    _, tenant, c = _setup(client, auth_headers, rent=5000)
    _generate(client, auth_headers, contract_id=c["id"])
    charges = _charges(client, auth_headers, c["id"])
    jan = charges["2026-01-01"]

    client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 5000, "receipt_date": "2026-01-05",
        "mode": "cash", "allocations": [{"charge_id": jan["id"], "amount": 5000}]})

    client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                json={"new_rent": 4000, "effective_date": "2026-01-01"})
    counts = _generate(client, auth_headers, contract_id=c["id"]).get_json()["data"]
    assert counts["skipped_paid"] >= 1

    after = _charges(client, auth_headers, c["id"])
    assert after["2026-01-01"]["amount"] == 5000, "a settled month keeps its figure"


def test_generate_all_covers_every_contract(client, auth_headers):
    _setup(client, auth_headers, rent=1000)
    _setup(client, auth_headers, rent=2000)
    counts = client.post("/api/v1/rent/generate", headers=auth_headers,
                         json={"upto": "2026-06-01"}).get_json()["data"]
    assert counts["contracts"] == 2
    assert counts["created"] == 12


def test_rent_endpoints_require_auth(client):
    assert client.get("/api/v1/rent/charges").status_code == 401
    assert client.post("/api/v1/rent/generate").status_code == 401
