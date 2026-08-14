"""Approval gates on the money-critical actions.

The rule these tests defend: while a request is pending, the portal must
read exactly as though nobody had asked. The rent is the old rent, the
units are still allocated, the receipt is still posted. Anything less
means a number on a report moved on one person's say-so.
"""
from datetime import date


def _enable(app, key: str, value: bool = True):
    from app.extensions import db
    from app.services import settings as settings_service
    with app.app_context():
        settings_service.set_value(key, value, actor_id=1)
        db.session.commit()


def _scaffold(client, auth_headers, *, units_per_floor=3):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "ST-36 Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "ST-36", "property_type": "building_with_store",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": units_per_floor},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "IMDAAD FACILITY SERVICES"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [u["id"] for u in units],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 28000, "payment_mode": "cash",
    }).get_json()["data"]
    return prop, tenant, contract


def _reduce_rent(client, auth_headers, contract, to=26000):
    return client.post(
        f"/api/v1/contracts/{contract['id']}/amendments/rent",
        headers=auth_headers,
        json={"new_rent": to, "effective_date": "2026-07-01", "reason": "market"},
    )


def _fetch(client, auth_headers, contract):
    return client.get(f"/api/v1/contracts/{contract['id']}",
                      headers=auth_headers).get_json()["data"]


def _queue(client, auth_headers, module):
    return client.get(f"/api/v1/approvals?module={module}",
                      headers=auth_headers).get_json()["data"]


# --------------------------------------------------------- rent reduction

def test_rent_reduction_applies_immediately_when_toggle_is_off(client, auth_headers):
    _, _, contract = _scaffold(client, auth_headers)
    resp = _reduce_rent(client, auth_headers, contract)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fetch(client, auth_headers, contract)["monthly_rent"] == 26000.0
    assert _queue(client, auth_headers, "rent_reduction") == []


def test_rent_reduction_waits_for_approval_and_changes_nothing_meanwhile(
        app, client, auth_headers):
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)

    resp = _reduce_rent(client, auth_headers, contract)
    assert resp.status_code == 202, resp.get_data(as_text=True)
    req = resp.get_json()["data"]
    assert req["module"] == "rent_reduction"
    assert req["status"] == "pending"
    assert req["payload"]["new_rent"] == 26000

    # The whole point: nothing has moved.
    detail = _fetch(client, auth_headers, contract)
    assert detail["monthly_rent"] == 28000.0
    assert [a for a in detail["amendments"] if a["amendment_type"] == "rent_change"] == []
    # …but the contract says out loud that something is waiting.
    assert len(detail["pending_approvals"]) == 1
    assert detail["pending_approvals"][0]["transaction_number"] == req["transaction_number"]

    ok = client.post(f"/api/v1/approvals/{req['id']}/approve",
                     headers=auth_headers, json={"remarks": "agreed with owner"})
    assert ok.status_code == 200, ok.get_data(as_text=True)

    after = _fetch(client, auth_headers, contract)
    assert after["monthly_rent"] == 26000.0
    amendments = [a for a in after["amendments"] if a["amendment_type"] == "rent_change"]
    assert len(amendments) == 1
    assert amendments[0]["old_rent"] == 28000.0
    assert amendments[0]["new_rent"] == 26000.0
    assert after["pending_approvals"] == []


def test_rejected_rent_reduction_leaves_the_rent_alone(app, client, auth_headers):
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)
    req = _reduce_rent(client, auth_headers, contract).get_json()["data"]

    resp = client.post(f"/api/v1/approvals/{req['id']}/reject",
                       headers=auth_headers, json={"remarks": "no"})
    assert resp.status_code == 200

    after = _fetch(client, auth_headers, contract)
    assert after["monthly_rent"] == 28000.0
    assert after["status"] == "active"       # the contract itself is untouched
    assert after["amendments"] == []
    assert after["pending_approvals"] == []


def test_rent_increase_is_not_gated(app, client, auth_headers):
    """Only reductions cost the company money; an increase posts at once."""
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)
    resp = _reduce_rent(client, auth_headers, contract, to=30000)
    assert resp.status_code == 200
    assert _fetch(client, auth_headers, contract)["monthly_rent"] == 30000.0


def test_pending_rent_reduction_does_not_reach_the_rent_engine(app, client, auth_headers):
    """A queued reduction must not price a single charge."""
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)
    _reduce_rent(client, auth_headers, contract)

    client.post("/api/v1/rent/generate", headers=auth_headers,
                json={"contract_id": contract["id"], "upto": "2026-08-01"})
    charges = client.get(f"/api/v1/rent/charges?contract_id={contract['id']}",
                         headers=auth_headers).get_json()["data"]
    july = [c for c in charges if str(c["period_month"]).startswith("2026-07")]
    assert july, "July should have been generated"
    assert july[0]["amount"] == 28000.0


def test_second_request_for_the_same_contract_is_refused(app, client, auth_headers):
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)
    assert _reduce_rent(client, auth_headers, contract).status_code == 202

    again = _reduce_rent(client, auth_headers, contract, to=25000)
    assert again.status_code == 409
    assert "already awaiting approval" in again.get_json()["message"]
    assert len(_queue(client, auth_headers, "rent_reduction")) == 1


def test_approval_revalidates_against_todays_state(app, client, auth_headers):
    """A reduction queued before the contract was cancelled must fail on
    approval rather than write a change onto a dead contract."""
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)
    req = _reduce_rent(client, auth_headers, contract).get_json()["data"]

    cancel = client.post(f"/api/v1/contracts/{contract['id']}/cancel", headers=auth_headers,
                         json={"effective_date": "2026-06-30", "reason": "vacated"})
    assert cancel.status_code == 200

    resp = client.post(f"/api/v1/approvals/{req['id']}/approve",
                       headers=auth_headers, json={})
    assert resp.status_code == 400
    assert "cancelled" in resp.get_json()["message"].lower()
    # Still pending — nobody has been told a lie about the outcome.
    assert _queue(client, auth_headers, "rent_reduction")[0]["status"] == "pending"


# ----------------------------------------------------- contract cancellation

def test_cancellation_waits_and_keeps_units_allocated(app, client, auth_headers):
    _enable(app, "approval.contract_cancellation.required")
    prop, _, contract = _scaffold(client, auth_headers)

    resp = client.post(f"/api/v1/contracts/{contract['id']}/cancel", headers=auth_headers,
                       json={"effective_date": "2026-06-30", "reason": "client vacated"})
    assert resp.status_code == 202, resp.get_data(as_text=True)
    req = resp.get_json()["data"]

    detail = _fetch(client, auth_headers, contract)
    assert detail["status"] == "active"
    assert detail["units_count"] == 3

    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    assert all(u["occupancy_status"] == "occupied" for u in units)

    ok = client.post(f"/api/v1/approvals/{req['id']}/approve", headers=auth_headers, json={})
    assert ok.status_code == 200, ok.get_data(as_text=True)

    after = _fetch(client, auth_headers, contract)
    assert after["status"] == "cancelled"
    assert after["cancellation_reason"] == "client vacated"
    freed = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    assert all(u["occupancy_status"] == "empty" for u in freed)


def test_cancellation_without_a_reason_is_refused_at_the_desk(app, client, auth_headers):
    """Don't queue something that can only fail later."""
    _enable(app, "approval.contract_cancellation.required")
    _, _, contract = _scaffold(client, auth_headers)
    resp = client.post(f"/api/v1/contracts/{contract['id']}/cancel",
                       headers=auth_headers, json={"effective_date": "2026-06-30"})
    assert resp.status_code == 400
    assert "reason" in resp.get_json()["message"].lower()
    assert _queue(client, auth_headers, "contract_cancellation") == []


# ------------------------------------------------------------ receipt void

def _receipt(client, auth_headers, tenant, contract, amount=28000):
    client.post("/api/v1/rent/generate", headers=auth_headers,
                json={"contract_id": contract["id"], "upto": "2026-01-01"})
    resp = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": amount,
        "receipt_date": "2026-01-05", "mode": "cash",
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def test_receipt_void_waits_and_the_money_stays_on_the_books(app, client, auth_headers):
    _enable(app, "approval.receipt_void.required")
    _, tenant, contract = _scaffold(client, auth_headers)
    receipt = _receipt(client, auth_headers, tenant, contract)

    resp = client.post(f"/api/v1/rent/receipts/{receipt['id']}/void",
                       headers=auth_headers, json={"reason": "wrong client"})
    assert resp.status_code == 202, resp.get_data(as_text=True)
    req = resp.get_json()["data"]

    still = client.get(f"/api/v1/rent/receipts/{receipt['id']}",
                       headers=auth_headers).get_json()["data"]
    assert still["status"] == "posted"

    charges = client.get(f"/api/v1/rent/charges?contract_id={contract['id']}",
                         headers=auth_headers).get_json()["data"]
    assert charges[0]["allocated"] == 28000.0

    ok = client.post(f"/api/v1/approvals/{req['id']}/approve", headers=auth_headers, json={})
    assert ok.status_code == 200, ok.get_data(as_text=True)

    voided = client.get(f"/api/v1/rent/receipts/{receipt['id']}",
                        headers=auth_headers).get_json()["data"]
    assert voided["status"] == "voided"
    assert voided["void_reason"] == "wrong client"
    reopened = client.get(f"/api/v1/rent/charges?contract_id={contract['id']}",
                          headers=auth_headers).get_json()["data"]
    assert reopened[0]["allocated"] == 0


def test_rejected_void_leaves_the_receipt_posted(app, client, auth_headers):
    _enable(app, "approval.receipt_void.required")
    _, tenant, contract = _scaffold(client, auth_headers)
    receipt = _receipt(client, auth_headers, tenant, contract)
    req = client.post(f"/api/v1/rent/receipts/{receipt['id']}/void",
                      headers=auth_headers,
                      json={"reason": "mistake"}).get_json()["data"]

    client.post(f"/api/v1/approvals/{req['id']}/reject",
                headers=auth_headers, json={"remarks": "receipt is correct"})

    still = client.get(f"/api/v1/rent/receipts/{receipt['id']}",
                       headers=auth_headers).get_json()["data"]
    assert still["status"] == "posted"
    assert still["void_reason"] is None


# ------------------------------------------------------------------ queue

def test_queue_reports_every_module(app, client, auth_headers):
    for key in ("approval.rent_reduction.required",
                "approval.contract_cancellation.required"):
        _enable(app, key)
    _, _, first = _scaffold(client, auth_headers)
    _reduce_rent(client, auth_headers, first)

    counts = client.get("/api/v1/approvals/counts",
                        headers=auth_headers).get_json()["data"]
    assert counts["rent_reduction"] == 1
    assert counts["contract_cancellation"] == 0
    assert counts["total"] == 1


def test_queue_rows_carry_a_readable_summary(app, client, auth_headers):
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)
    _reduce_rent(client, auth_headers, contract)

    row = _queue(client, auth_headers, "rent_reduction")[0]
    assert row["module_label"] == "Rent reduction"
    assert "28,000.00 to 26,000.00" in row["summary"]
    assert row["entity_reference"] == contract["contract_number"]


def test_requesting_an_approval_is_audited(app, client, auth_headers):
    _enable(app, "approval.rent_reduction.required")
    _, _, contract = _scaffold(client, auth_headers)
    _reduce_rent(client, auth_headers, contract)

    rows = client.get("/api/v1/audit?module=approval",
                      headers=auth_headers).get_json()["data"]
    assert any(r["action"] == "request" for r in rows)


def test_approving_an_already_cancelled_contract_cannot_double_release(
        app, client, auth_headers):
    """Two operators, one contract: the second approval must not run."""
    _enable(app, "approval.contract_cancellation.required")
    _, _, contract = _scaffold(client, auth_headers)
    req = client.post(f"/api/v1/contracts/{contract['id']}/cancel", headers=auth_headers,
                      json={"effective_date": "2026-06-30",
                            "reason": "vacated"}).get_json()["data"]

    assert client.post(f"/api/v1/approvals/{req['id']}/approve",
                       headers=auth_headers, json={}).status_code == 200
    again = client.post(f"/api/v1/approvals/{req['id']}/approve",
                        headers=auth_headers, json={})
    assert again.status_code == 400
    assert "already approved" in again.get_json()["message"].lower()
