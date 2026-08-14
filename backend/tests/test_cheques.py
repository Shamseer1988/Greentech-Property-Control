"""PDC register: 12 rent cheques + security, and the cheque lifecycle."""
from datetime import date, timedelta


def _cheque_contract(client, auth_headers, *, rent=6000):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "PDC Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "PDC Tower", "property_type": "full_building",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 3},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "AL MIHRAB SHOP"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": rent, "payment_mode": "cheque",
    }).get_json()["data"]
    return contract


def _book(count=12, amount=6000, start_month=1):
    return [
        {"cheque_number": f"100{i:04d}", "bank_name": "QNB",
         "cheque_date": f"2026-{start_month + i:02d}-01", "amount": amount}
        for i in range(count)
    ]


def test_preview_builds_twelve_dated_rows(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    resp = client.get(f"/api/v1/contracts/{c['id']}/cheques/preview", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.get_json()["data"]
    assert len(rows) == 12
    assert rows[0]["cheque_date"] == "2026-01-01"
    assert rows[11]["cheque_date"] == "2026-12-01"
    assert all(r["amount"] == 6000 for r in rows)


def test_preview_clamps_month_end(client, auth_headers):
    """31 Jan + 1 month must land on 28 Feb, not overflow."""
    c = _cheque_contract(client, auth_headers)
    resp = client.get(
        f"/api/v1/contracts/{c['id']}/cheques/preview?count=2&start_date=2026-01-31",
        headers=auth_headers)
    rows = resp.get_json()["data"]
    assert rows[0]["cheque_date"] == "2026-01-31"
    assert rows[1]["cheque_date"] == "2026-02-28"


def test_register_twelve_plus_security(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    resp = client.post(f"/api/v1/contracts/{c['id']}/cheques", headers=auth_headers, json={
        "cheques": _book(),
        "security": {"cheque_number": "SEC-9001", "bank_name": "QNB",
                     "cheque_date": "2026-01-01", "amount": 6000},
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    created = resp.get_json()["data"]
    assert len(created) == 13

    listed = client.get(f"/api/v1/contracts/{c['id']}/cheques",
                        headers=auth_headers).get_json()
    assert listed["meta"]["count"] == 13
    security = [x for x in listed["data"] if x["is_security"]]
    assert len(security) == 1
    assert security[0]["cheque_number"] == "SEC-9001"
    rent_cheques = [x for x in listed["data"] if not x["is_security"]]
    assert all(x["status"] == "received" for x in rent_cheques)
    assert rent_cheques[0]["for_month"] == "2026-01-01"


def test_cheques_rejected_on_cash_contract(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Cash Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Cash Camp", "property_type": "labour_camp",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 2},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Cash Co"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    c = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": 1400,
        "payment_mode": "cash", "security_deposit": 1400,
    }).get_json()["data"]

    resp = client.post(f"/api/v1/contracts/{c['id']}/cheques", headers=auth_headers,
                       json={"cheques": _book(1)})
    assert resp.status_code == 400
    assert "cash contract" in resp.get_json()["message"]


def test_duplicate_cheque_number_rejected_and_rolls_back(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    book = _book(3)
    book[2]["cheque_number"] = book[0]["cheque_number"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/cheques", headers=auth_headers,
                       json={"cheques": book})
    assert resp.status_code == 400
    assert "already registered" in resp.get_json()["message"]

    listed = client.get(f"/api/v1/contracts/{c['id']}/cheques",
                        headers=auth_headers).get_json()
    assert listed["meta"]["count"] == 0, "a bad row must not leave a half-entered book"


# ------------------------------------------------------------ lifecycle

def _first_cheque(client, auth_headers, contract_id):
    client.post(f"/api/v1/contracts/{contract_id}/cheques", headers=auth_headers,
                json={"cheques": _book(2)})
    return client.get(f"/api/v1/contracts/{contract_id}/cheques",
                      headers=auth_headers).get_json()["data"][0]


def test_happy_path_deposit_then_clear(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])

    dep = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit",
                      headers=auth_headers, json={"when": "2026-01-02"})
    assert dep.status_code == 200
    assert dep.get_json()["data"]["status"] == "deposited"

    cleared = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/clear",
                          headers=auth_headers, json={"when": "2026-01-04",
                                                      "bank_reference": "TXN-77"})
    assert cleared.status_code == 200
    assert cleared.get_json()["data"]["status"] == "cleared"

    detail = client.get(f"/api/v1/contracts/cheques/{cheque['id']}",
                        headers=auth_headers).get_json()["data"]
    assert [e["event_type"] for e in detail["events"]] == ["received", "deposited", "cleared"]
    assert detail["events"][2]["bank_reference"] == "TXN-77"


def test_illegal_transitions_are_refused(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])

    # Can't clear a cheque that was never deposited.
    early = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/clear",
                        headers=auth_headers, json={})
    assert early.status_code == 400
    assert "cannot move to 'cleared'" in early.get_json()["message"]

    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit", headers=auth_headers, json={})
    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/clear", headers=auth_headers, json={})

    # Cleared is terminal.
    again = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/bounce",
                        headers=auth_headers, json={"reason": "nope"})
    assert again.status_code == 400
    assert "terminal" in again.get_json()["message"]


def test_bounce_requires_reason(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])
    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit", headers=auth_headers, json={})
    resp = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/bounce",
                       headers=auth_headers, json={})
    assert resp.status_code == 400


def test_bounce_then_replace_links_the_chain(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])
    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit", headers=auth_headers, json={})
    bounced = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/bounce",
                          headers=auth_headers,
                          json={"reason": "insufficient funds", "when": "2026-01-05"})
    assert bounced.status_code == 200
    assert bounced.get_json()["data"]["status"] == "bounced"

    resp = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/replace",
                       headers=auth_headers,
                       json={"cheque_number": "REP-5001", "cheque_date": "2026-02-10"})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    replacement = resp.get_json()["data"]
    assert replacement["replaces_cheque_id"] == cheque["id"]
    assert replacement["status"] == "received"
    assert replacement["amount"] == cheque["amount"], "amount carried over"
    assert replacement["for_month"] == cheque["for_month"], "still covers the same month"

    original = client.get(f"/api/v1/contracts/cheques/{cheque['id']}",
                          headers=auth_headers).get_json()["data"]
    assert original["status"] == "replaced"
    kinds = [e["event_type"] for e in original["events"]]
    assert kinds == ["received", "deposited", "bounced", "replaced"]
    assert original["events"][2]["reason"] == "insufficient funds"


def test_only_bounced_cheques_can_be_replaced(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])
    resp = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/replace",
                       headers=auth_headers,
                       json={"cheque_number": "REP-1", "cheque_date": "2026-02-10"})
    assert resp.status_code == 400
    assert "bounced" in resp.get_json()["message"]


def test_security_cheque_is_returned_not_deposited(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    client.post(f"/api/v1/contracts/{c['id']}/cheques", headers=auth_headers, json={
        "cheques": _book(1),
        "security": {"cheque_number": "SEC-1", "cheque_date": "2026-01-01", "amount": 6000},
    })
    security = [x for x in client.get(f"/api/v1/contracts/{c['id']}/cheques",
                                      headers=auth_headers).get_json()["data"]
                if x["is_security"]][0]

    resp = client.post(f"/api/v1/contracts/cheques/{security['id']}/return",
                       headers=auth_headers, json={"remarks": "contract closed"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "returned"


def test_returning_a_deposited_cheque_reverses_its_receipt(client, auth_headers):
    """The client hands the tenant's cheque back and takes cash instead —
    the receipt the deposit posted must void so the month reopens."""
    c = _cheque_contract(client, auth_headers)
    client.post("/api/v1/rent/generate", headers=auth_headers,
               json={"contract_id": c["id"], "upto": "2026-01-01"})
    cheque = _first_cheque(client, auth_headers, c["id"])
    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit",
               headers=auth_headers, json={})

    charge_before = client.get(f"/api/v1/rent/charges?contract_id={c['id']}",
                               headers=auth_headers).get_json()["data"][0]
    assert charge_before["status"] == "paid"

    resp = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/return",
                       headers=auth_headers, json={"remarks": "client paying cash instead"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "returned"

    charge_after = client.get(f"/api/v1/rent/charges?contract_id={c['id']}",
                              headers=auth_headers).get_json()["data"][0]
    assert charge_after["status"] == "open", "reopened once the cheque was handed back"

    receipts = client.get(f"/api/v1/rent/receipts?client_id={c['client_id']}",
                          headers=auth_headers).get_json()["data"]
    assert receipts[0]["status"] == "voided"


def test_returning_a_received_never_deposited_cheque_touches_no_receipt(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])

    resp = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/return",
                       headers=auth_headers, json={})
    assert resp.status_code == 200

    receipts = client.get(f"/api/v1/rent/receipts?client_id={c['client_id']}",
                          headers=auth_headers).get_json()["data"]
    assert receipts == []


def test_bounced_cheque_can_be_re_presented(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])
    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit", headers=auth_headers, json={})
    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/bounce",
               headers=auth_headers, json={"reason": "insufficient funds"})

    again = client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit",
                        headers=auth_headers, json={})
    assert again.status_code == 200
    assert again.get_json()["data"]["status"] == "deposited"

    receipts = client.get(f"/api/v1/rent/receipts?client_id={c['client_id']}",
                          headers=auth_headers).get_json()["data"]
    statuses = sorted(r["status"] for r in receipts)
    assert statuses == ["posted", "voided"], "the bounced deposit voided, the re-presented one posted"


def test_list_cheques_by_client_across_contracts(client, auth_headers):
    c1 = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c1["id"])  # books 2 cheques

    all_for_client = client.get(f"/api/v1/contracts/cheques?client_id={c1['client_id']}",
                                headers=auth_headers).get_json()["data"]
    assert len(all_for_client) == 2
    assert all_for_client[0]["contract_number"] == c1["contract_number"]

    only_received = client.get(
        f"/api/v1/contracts/cheques?client_id={c1['client_id']}&status=received",
        headers=auth_headers).get_json()["data"]
    assert len(only_received) == 2

    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit", headers=auth_headers, json={})
    only_received_after = client.get(
        f"/api/v1/contracts/cheques?client_id={c1['client_id']}&status=received",
        headers=auth_headers).get_json()["data"]
    assert len(only_received_after) == 1


def test_cheque_actions_are_audited(client, auth_headers):
    c = _cheque_contract(client, auth_headers)
    cheque = _first_cheque(client, auth_headers, c["id"])
    client.post(f"/api/v1/contracts/cheques/{cheque['id']}/deposit", headers=auth_headers, json={})

    rows = client.get("/api/v1/audit?module=cheque", headers=auth_headers).get_json()["data"]
    assert any(r["action"] == "deposited" for r in rows)
