"""Bulk entry: one receipt per client / one voucher per (landlord,
property), posted in a single batch request — Phase 5's main feature."""


def _client_contract(client, auth_headers, name, *, rent=1000, mode="cash"):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": f"{name} LL"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": f"{name} Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": name}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": rent, "payment_mode": mode,
    }).get_json()["data"]
    client.post("/api/v1/rent/generate", headers=auth_headers,
               json={"contract_id": contract["id"], "upto": "2026-04-01"})
    return landlord, prop, tenant, contract


# ------------------------------------------------------------ receipts

def test_bulk_preview_groups_charges_by_client(client, auth_headers):
    landlord, prop, tenant1, c1 = _client_contract(client, auth_headers, "Bulk Client A", rent=1000)
    landlord2, prop2, tenant2, c2 = _client_contract(client, auth_headers, "Bulk Client B", rent=2000)

    resp = client.get("/api/v1/rent/bulk-preview?from_month=2026-01-01&to_month=2026-04-01",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    by_id = {e["client"]["id"]: e for e in data}
    assert tenant1["id"] in by_id and tenant2["id"] in by_id
    assert len(by_id[tenant1["id"]]["charges"]) == 4
    assert by_id[tenant1["id"]]["total_outstanding"] == 4000
    assert by_id[tenant2["id"]]["total_outstanding"] == 8000


def test_bulk_post_creates_one_receipt_per_client_with_partial_amounts(client, auth_headers):
    landlord, prop, tenant1, c1 = _client_contract(client, auth_headers, "Bulk Post A", rent=1000)
    landlord2, prop2, tenant2, c2 = _client_contract(client, auth_headers, "Bulk Post B", rent=2000)

    preview = client.get("/api/v1/rent/bulk-preview?from_month=2026-01-01&to_month=2026-04-01",
                         headers=auth_headers).get_json()["data"]
    by_id = {e["client"]["id"]: e for e in preview}

    # Client A: pay January in full, February half — a genuine partial.
    jan_a = by_id[tenant1["id"]]["charges"][0]
    feb_a = by_id[tenant1["id"]]["charges"][1]
    # Client B: pay everything outstanding.
    entries = [
        {"client_id": tenant1["id"], "allocations": [
            {"charge_id": jan_a["id"], "amount": jan_a["outstanding"]},
            {"charge_id": feb_a["id"], "amount": 500},
        ]},
        {"client_id": tenant2["id"], "allocations": [
            {"charge_id": c["id"], "amount": c["outstanding"]}
            for c in by_id[tenant2["id"]]["charges"]
        ]},
    ]
    resp = client.post("/api/v1/rent/bulk-post", headers=auth_headers, json={
        "receipt_date": "2026-01-15", "mode": "cash", "entries": entries,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    result = resp.get_json()["data"]
    assert len(result["posted"]) == 2
    assert result["failed"] == []
    numbers = [p["receipt_number"] for p in result["posted"]]
    assert len(set(numbers)) == 2, "one receipt per client, distinct numbers"

    charges = {c["period_month"]: c for c in client.get(
        f"/api/v1/rent/charges?contract_id={c1['id']}", headers=auth_headers).get_json()["data"]}
    assert charges["2026-01-01"]["status"] == "paid"
    assert charges["2026-02-01"]["status"] == "part_paid"
    assert charges["2026-02-01"]["outstanding"] == 500

    charges_b = {c["period_month"]: c for c in client.get(
        f"/api/v1/rent/charges?contract_id={c2['id']}", headers=auth_headers).get_json()["data"]}
    assert all(c["status"] == "paid" for c in charges_b.values())


def test_bulk_post_isolates_a_bad_entry_from_the_rest(client, auth_headers):
    landlord, prop, tenant1, c1 = _client_contract(client, auth_headers, "Bulk Fail A", rent=1000)
    landlord2, prop2, tenant2, c2 = _client_contract(client, auth_headers, "Bulk Fail B", rent=2000)

    preview = client.get("/api/v1/rent/bulk-preview?from_month=2026-01-01&to_month=2026-04-01",
                         headers=auth_headers).get_json()["data"]
    by_id = {e["client"]["id"]: e for e in preview}
    good_charge = by_id[tenant2["id"]]["charges"][0]

    entries = [
        # A charge_id that belongs to a different client than named — post_receipt rejects this.
        {"client_id": tenant1["id"], "allocations": [
            {"charge_id": good_charge["id"], "amount": 100},
        ]},
        {"client_id": tenant2["id"], "allocations": [
            {"charge_id": good_charge["id"], "amount": good_charge["outstanding"]},
        ]},
    ]
    resp = client.post("/api/v1/rent/bulk-post", headers=auth_headers, json={
        "receipt_date": "2026-01-15", "mode": "cash", "entries": entries,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    result = resp.get_json()["data"]
    assert len(result["posted"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["client_id"] == tenant1["id"]

    # The good entry must still have gone through despite the bad one.
    charges_b = client.get(f"/api/v1/rent/charges?contract_id={c2['id']}",
                           headers=auth_headers).get_json()["data"]
    settled = next(c for c in charges_b if c["id"] == good_charge["id"])
    assert settled["status"] == "paid"


# ------------------------------------------------------- landlord payments

def test_landlord_bulk_preview_groups_by_landlord_and_property(client, auth_headers):
    landlord, prop, _, _ = _client_contract(client, auth_headers, "LB Client A")
    ag = client.post(f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers, json={
        "landlord_id": landlord["id"], "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 5000,
    }).get_json()["data"]
    client.post("/api/v1/expenses/landlord-dues/generate", headers=auth_headers,
               json={"contract_id": ag["id"], "upto": "2026-04-01"})

    resp = client.get(
        "/api/v1/expenses/landlord-dues/bulk-preview?from_month=2026-01-01&to_month=2026-04-01",
        headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    row = next(e for e in data if e["landlord"]["id"] == landlord["id"])
    assert len(row["charges"]) == 4
    assert row["total_outstanding"] == 20000


def test_landlord_bulk_post_creates_one_voucher_per_pair(client, auth_headers):
    landlord, prop, _, _ = _client_contract(client, auth_headers, "LB Post A")
    ag = client.post(f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers, json={
        "landlord_id": landlord["id"], "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 5000,
    }).get_json()["data"]
    client.post("/api/v1/expenses/landlord-dues/generate", headers=auth_headers,
               json={"contract_id": ag["id"], "upto": "2026-02-01"})

    preview = client.get(
        "/api/v1/expenses/landlord-dues/bulk-preview?from_month=2026-01-01&to_month=2026-02-01",
        headers=auth_headers).get_json()["data"]
    row = next(e for e in preview if e["landlord"]["id"] == landlord["id"])

    entries = [{
        "landlord_id": landlord["id"], "property_id": prop["id"], "contract_id": ag["id"],
        "allocations": [{"charge_id": c["id"], "amount": c["outstanding"]} for c in row["charges"]],
    }]
    resp = client.post("/api/v1/expenses/landlord-dues/bulk-post", headers=auth_headers, json={
        "payment_date": "2026-01-15", "mode": "cash", "entries": entries,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    result = resp.get_json()["data"]
    assert len(result["posted"]) == 1
    assert result["posted"][0]["amount"] == 10000

    charges = client.get(f"/api/v1/expenses/landlord-charges?contract_id={ag['id']}",
                         headers=auth_headers).get_json()["data"]
    assert all(c["status"] == "paid" for c in charges)


def test_bulk_endpoints_require_auth(client):
    assert client.get("/api/v1/rent/bulk-preview").status_code == 401
    assert client.post("/api/v1/rent/bulk-post").status_code == 401
    assert client.get("/api/v1/expenses/landlord-dues/bulk-preview").status_code == 401
    assert client.post("/api/v1/expenses/landlord-dues/bulk-post").status_code == 401
