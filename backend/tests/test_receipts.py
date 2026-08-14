"""Receipts, allocation, voiding, ageing and statements of account."""
from datetime import date


def _ledger(client, auth_headers, *, rent=1000, months_upto="2026-04-01", mode="cash"):
    """A contract with Jan-Apr charges raised."""
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Coll LL"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Coll Tower", "property_type": "full_building",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Coll Client"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": rent, "payment_mode": mode,
    }).get_json()["data"]
    client.post("/api/v1/rent/generate", headers=auth_headers,
                json={"contract_id": contract["id"], "upto": months_upto})
    return prop, tenant, contract


def _charges(client, auth_headers, contract_id):
    rows = client.get(f"/api/v1/rent/charges?contract_id={contract_id}",
                      headers=auth_headers).get_json()["data"]
    return sorted(rows, key=lambda r: r["period_month"])


# ---------------------------------------------------------- allocation

def test_receipt_settles_oldest_charge_first(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=1000)   # Jan-Apr, 4000 due

    resp = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 2500,
        "receipt_date": "2026-04-05", "mode": "cash"})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    receipt = resp.get_json()["data"]
    assert receipt["receipt_number"].startswith("RV-")
    assert receipt["allocated"] == 2500
    assert receipt["unallocated"] == 0

    charges = _charges(client, auth_headers, c["id"])
    assert charges[0]["status"] == "paid"        # Jan
    assert charges[1]["status"] == "paid"        # Feb
    assert charges[2]["status"] == "part_paid"   # Mar, 500 of 1000
    assert charges[2]["outstanding"] == 500
    assert charges[3]["status"] == "open"        # Apr untouched


def test_overpayment_is_held_as_an_advance(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=1000)   # 4000 due
    resp = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 5000,
        "receipt_date": "2026-04-05", "mode": "cash"})
    receipt = resp.get_json()["data"]
    assert receipt["allocated"] == 4000
    assert receipt["unallocated"] == 1000, "money on account, not lost"

    charges = _charges(client, auth_headers, c["id"])
    assert all(x["status"] == "paid" for x in charges)


def test_manual_allocation_targets_a_named_month(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=1000)
    charges = _charges(client, auth_headers, c["id"])
    april = charges[3]

    resp = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 1000, "receipt_date": "2026-04-05",
        "mode": "online", "allocations": [{"charge_id": april["id"], "amount": 1000}]})
    assert resp.status_code == 201
    detail = resp.get_json()["data"]
    assert detail["allocations"][0]["is_manual"] is True

    after = _charges(client, auth_headers, c["id"])
    assert after[3]["status"] == "paid", "April settled as instructed"
    assert after[0]["status"] == "open", "January deliberately left open"


def test_receipt_cannot_pay_another_clients_charge(client, auth_headers):
    _, tenant_a, c_a = _ledger(client, auth_headers)
    _, tenant_b, _ = _ledger(client, auth_headers)
    charge_a = _charges(client, auth_headers, c_a["id"])[0]

    resp = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant_b["id"], "amount": 500, "receipt_date": "2026-02-01",
        "mode": "cash", "allocations": [{"charge_id": charge_a["id"], "amount": 500}]})
    assert resp.status_code == 400
    assert "another client" in resp.get_json()["message"]


def test_receipt_validation(client, auth_headers):
    _, tenant, _ = _ledger(client, auth_headers)
    bad_mode = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 100, "receipt_date": "2026-02-01",
        "mode": "barter"})
    assert bad_mode.status_code == 400

    zero = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 0, "receipt_date": "2026-02-01",
        "mode": "cash"})
    assert zero.status_code == 400


# --------------------------------------------------------------- void

def test_void_reopens_the_dues_and_keeps_the_receipt(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=1000)
    posted = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 2000, "receipt_date": "2026-03-01",
        "mode": "cash"}).get_json()["data"]

    assert _charges(client, auth_headers, c["id"])[0]["status"] == "paid"

    resp = client.post(f"/api/v1/rent/receipts/{posted['id']}/void", headers=auth_headers,
                       json={"reason": "entered against the wrong client"})
    assert resp.status_code == 200
    voided = resp.get_json()["data"]
    assert voided["status"] == "voided"
    assert voided["void_reason"] == "entered against the wrong client"

    charges = _charges(client, auth_headers, c["id"])
    assert charges[0]["status"] == "open", "the due reopened"
    assert charges[0]["outstanding"] == 1000

    # The receipt itself is still on the ledger with its number.
    listed = client.get(f"/api/v1/rent/receipts?client_id={tenant['id']}",
                        headers=auth_headers).get_json()["data"]
    assert any(r["receipt_number"] == posted["receipt_number"] for r in listed)


def test_void_requires_a_reason_and_cannot_repeat(client, auth_headers):
    _, tenant, _ = _ledger(client, auth_headers)
    posted = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 500, "receipt_date": "2026-03-01",
        "mode": "cash"}).get_json()["data"]

    assert client.post(f"/api/v1/rent/receipts/{posted['id']}/void", headers=auth_headers,
                       json={}).status_code == 400

    client.post(f"/api/v1/rent/receipts/{posted['id']}/void", headers=auth_headers,
                json={"reason": "duplicate"})
    again = client.post(f"/api/v1/rent/receipts/{posted['id']}/void", headers=auth_headers,
                        json={"reason": "again"})
    assert again.status_code == 400
    assert "already voided" in again.get_json()["message"]


def test_receipt_numbers_are_sequential_and_survive_voiding(client, auth_headers):
    _, tenant, _ = _ledger(client, auth_headers)
    first = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 100, "receipt_date": "2026-02-01",
        "mode": "cash"}).get_json()["data"]
    client.post(f"/api/v1/rent/receipts/{first['id']}/void", headers=auth_headers,
                json={"reason": "mistake"})
    second = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 100, "receipt_date": "2026-02-02",
        "mode": "cash"}).get_json()["data"]

    assert first["receipt_number"] != second["receipt_number"]
    assert int(second["receipt_number"].rsplit("-", 1)[1]) == \
           int(first["receipt_number"].rsplit("-", 1)[1]) + 1, "no gaps, no reuse"


# ------------------------------------------------- cheque -> receipt

def test_depositing_a_cheque_posts_a_receipt_for_its_month(client, auth_headers):
    """Deposit is the revenue-recognition point — the SOA reflects the
    money as soon as the bank has the cheque, not once it clears."""
    _, tenant, c = _ledger(client, auth_headers, rent=6000, mode="cheque")
    client.post(f"/api/v1/contracts/{c['id']}/cheques", headers=auth_headers, json={
        "cheques": [{"cheque_number": "CH-1", "cheque_date": "2026-01-01",
                     "for_month": "2026-01-01", "amount": 6000}]})
    cheque = client.get(f"/api/v1/contracts/{c['id']}/cheques",
                        headers=auth_headers).get_json()["data"][0]

    dep = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit",
                      headers=auth_headers, json={"when": "2026-01-03"})
    assert dep.status_code == 200

    receipts = client.get(f"/api/v1/rent/receipts?client_id={tenant['id']}",
                          headers=auth_headers).get_json()["data"]
    assert len(receipts) == 1
    assert receipts[0]["mode"] == "cheque"
    assert receipts[0]["amount"] == 6000
    assert "CH-1" in receipts[0]["reference"]

    charges = _charges(client, auth_headers, c["id"])
    assert charges[0]["status"] == "paid", "January settled once the cheque was deposited"

    # Clearing afterwards is confirmation only — no second receipt.
    resp = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/clear",
                       headers=auth_headers, json={"when": "2026-01-05"})
    assert resp.status_code == 200
    still_one = client.get(f"/api/v1/rent/receipts?client_id={tenant['id']}",
                           headers=auth_headers).get_json()["data"]
    assert len(still_one) == 1


def test_depositing_the_security_cheque_posts_nothing(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=6000, mode="cheque")
    client.post(f"/api/v1/contracts/{c['id']}/cheques", headers=auth_headers, json={
        "cheques": [],
        "security": {"cheque_number": "SEC-9", "cheque_date": "2026-01-01", "amount": 6000}})
    security = client.get(f"/api/v1/contracts/{c['id']}/cheques",
                          headers=auth_headers).get_json()["data"][0]
    client.post(f"/api/v1/contracts/cheques/{security['id']}/deposit",
                headers=auth_headers, json={})
    client.post(f"/api/v1/contracts/cheques/{security['id']}/clear",
                headers=auth_headers, json={})

    receipts = client.get(f"/api/v1/rent/receipts?client_id={tenant['id']}",
                          headers=auth_headers).get_json()["data"]
    assert receipts == [], "a security cheque is not rent"


def test_bounce_voids_the_receipt_deposit_posted(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=6000, mode="cheque")
    client.post(f"/api/v1/contracts/{c['id']}/cheques", headers=auth_headers, json={
        "cheques": [{"cheque_number": "CH-2", "cheque_date": "2026-01-01",
                     "for_month": "2026-01-01", "amount": 6000}]})
    cheque = client.get(f"/api/v1/contracts/{c['id']}/cheques",
                        headers=auth_headers).get_json()["data"][0]

    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit",
                headers=auth_headers, json={"when": "2026-01-03"})
    charges = _charges(client, auth_headers, c["id"])
    assert charges[0]["status"] == "paid"

    bounced = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/bounce",
                          headers=auth_headers, json={"reason": "insufficient funds"})
    assert bounced.status_code == 200

    receipts = client.get(f"/api/v1/rent/receipts?client_id={tenant['id']}",
                          headers=auth_headers).get_json()["data"]
    assert len(receipts) == 1
    assert receipts[0]["status"] == "voided", "the receipt the bounced deposit posted is reversed"

    charges = _charges(client, auth_headers, c["id"])
    assert charges[0]["status"] == "open", "January reopens once the cheque bounces"


# -------------------------------------------------------------- ageing

def test_ageing_buckets_by_month(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=1000)   # Jan-Apr open
    client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 1500, "receipt_date": "2026-04-05",
        "mode": "cash"})

    resp = client.get("/api/v1/rent/ageing?upto=2026-04-01", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    row = next(r for r in data["rows"] if r["client_id"] == tenant["id"])
    assert row["total"] == 2500, "4000 charged less 1500 paid"
    assert row["months"]["2026-02-01"] == 500, "Feb part-paid"
    assert row["months"]["2026-03-01"] == 1000
    assert "2026-01-01" not in row["months"], "January fully settled"
    assert data["grand_total"] == 2500


def test_outstanding_by_client_lists_who_owes(client, auth_headers):
    _, tenant, _ = _ledger(client, auth_headers, rent=1000)
    resp = client.get("/api/v1/rent/outstanding?upto=2026-04-01", headers=auth_headers)
    rows = resp.get_json()["data"]
    row = next(r for r in rows if r["client_id"] == tenant["id"])
    assert row["outstanding"] == 4000
    assert row["open_months"] == 4
    assert row["oldest_month"] == "2026-01-01"


# ------------------------------------------------------------ statement

def test_statement_of_account_runs_a_balance(client, auth_headers):
    _, tenant, c = _ledger(client, auth_headers, rent=1000)
    client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 2500, "receipt_date": "2026-03-10",
        "mode": "cash"})

    resp = client.get(f"/api/v1/rent/statement/{tenant['id']}", headers=auth_headers)
    assert resp.status_code == 200
    soa = resp.get_json()["data"]
    assert soa["client"]["id"] == tenant["id"]
    assert soa["totals"]["debit"] == 4000
    assert soa["totals"]["credit"] == 2500
    assert soa["totals"]["balance"] == 1500
    assert soa["lines"][-1]["balance"] == 1500

    # Charges precede the receipt that settles them on the same date.
    kinds = [l["type"] for l in soa["lines"]]
    assert kinds.count("charge") == 4
    assert kinds.count("receipt") == 1


def test_voided_receipt_is_absent_from_the_statement(client, auth_headers):
    _, tenant, _ = _ledger(client, auth_headers, rent=1000)
    posted = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 1000, "receipt_date": "2026-02-10",
        "mode": "cash"}).get_json()["data"]
    client.post(f"/api/v1/rent/receipts/{posted['id']}/void", headers=auth_headers,
                json={"reason": "wrong client"})

    soa = client.get(f"/api/v1/rent/statement/{tenant['id']}",
                     headers=auth_headers).get_json()["data"]
    assert soa["totals"]["credit"] == 0
    assert soa["totals"]["balance"] == 4000


def test_collections_summary(client, auth_headers):
    _, tenant, _ = _ledger(client, auth_headers, rent=1000)
    client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 1000, "receipt_date": "2026-01-15",
        "mode": "cash"})

    data = client.get("/api/v1/rent/summary?month=2026-01-01",
                      headers=auth_headers).get_json()["data"]
    assert data["charged"] == 1000
    assert data["collected"] == 1000
    assert data["outstanding"] == 0
    assert data["collection_percent"] == 100.0


def test_receipt_endpoints_require_auth(client):
    assert client.get("/api/v1/rent/receipts").status_code == 401
    assert client.get("/api/v1/rent/ageing").status_code == 401
