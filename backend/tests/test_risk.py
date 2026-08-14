"""Client risk scoring: ageing + bounced cheques + late payments -> a
weighted score and tier."""
from datetime import date, timedelta

from app.services import risk as risk_service


def _cash_contract(client, auth_headers, *, rent=3000, start=None, expiry="2027-12-31"):
    start = start or (date.today() - timedelta(days=200)).isoformat()
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Risk Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Risk Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 3},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Risk Client"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]],
        "start_date": start, "expiry_date": expiry,
        "monthly_rent": rent, "payment_mode": "cash",
    }).get_json()["data"]
    return tenant, contract


def _cheque_contract(client, auth_headers, *, rent=3000):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Risk Cheque Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Risk Cheque Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 3},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Risk Cheque Client"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": rent, "payment_mode": "cheque",
    }).get_json()["data"]
    return tenant, contract


def test_empty_portfolio_has_no_risk_rows(app):
    with app.app_context():
        assert risk_service.client_risk_report() == []


def test_overdue_client_appears_with_days_overdue_and_a_tier(client, auth_headers, app):
    tenant, contract = _cash_contract(client, auth_headers, rent=3000)
    # Generate charges going back ~6 months, all left unpaid.
    upto = date.today().replace(day=1).isoformat()
    resp = client.post("/api/v1/rent/generate", headers=auth_headers,
                       json={"upto": upto, "contract_id": contract["id"]})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    with app.app_context():
        rows = risk_service.client_risk_report()
    row = next((r for r in rows if r["client_id"] == tenant["id"]), None)
    assert row is not None
    assert row["days_overdue"] > 0
    assert row["outstanding"] > 0
    assert row["tier"] in ("low", "medium", "high")
    assert row["score"] > 0


def test_bounced_cheque_raises_the_score(client, auth_headers, app):
    tenant, contract = _cheque_contract(client, auth_headers, rent=3000)
    cheque_date = date.today().isoformat()
    resp = client.post(f"/api/v1/contracts/{contract['id']}/cheques", headers=auth_headers, json={
        "cheques": [{"cheque_number": "200001", "bank_name": "QNB",
                     "cheque_date": cheque_date, "amount": 3000}],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    cheque_id = resp.get_json()["data"][0]["id"]

    dep = client.post(f"/api/v1/contracts/cheques/{cheque_id}/deposit", headers=auth_headers, json={})
    assert dep.status_code == 200, dep.get_data(as_text=True)
    bounce = client.post(f"/api/v1/contracts/cheques/{cheque_id}/bounce", headers=auth_headers,
                         json={"reason": "insufficient funds"})
    assert bounce.status_code == 200, bounce.get_data(as_text=True)

    with app.app_context():
        rows = risk_service.client_risk_report()
    row = next((r for r in rows if r["client_id"] == tenant["id"]), None)
    assert row is not None
    assert row["bounced_cheques_12m"] == 1
    assert row["score"] > 0


def test_report_sorted_by_score_descending(client, auth_headers, app):
    low_tenant, low_contract = _cash_contract(client, auth_headers, rent=100,
                                              start=(date.today() - timedelta(days=35)).isoformat())
    high_tenant, high_contract = _cash_contract(client, auth_headers, rent=5000,
                                                start=(date.today() - timedelta(days=365)).isoformat())
    upto = date.today().replace(day=1).isoformat()
    for contract_id in (low_contract["id"], high_contract["id"]):
        client.post("/api/v1/rent/generate", headers=auth_headers,
                   json={"upto": upto, "contract_id": contract_id})

    with app.app_context():
        rows = risk_service.client_risk_report()
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_route_requires_permission(client):
    resp = client.get("/api/v1/reports/client-risk")
    assert resp.status_code == 401


def test_route_returns_ranked_rows(client, auth_headers):
    _cash_contract(client, auth_headers, rent=2000)
    resp = client.get("/api/v1/reports/client-risk", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "columns" in data and "rows" in data
