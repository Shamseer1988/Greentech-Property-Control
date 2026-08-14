"""Cash-flow forecast: 30/60/90-day incoming/outgoing buckets built from
open rent charges, pending cheques and open landlord charges."""
from datetime import date, timedelta

from app.services import cashflow as cashflow_service


def _cash_contract(client, auth_headers, *, rent=5000):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "CF Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "CF Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 3},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "CF Cash Client"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": rent, "payment_mode": "cash",
    }).get_json()["data"]
    return landlord, prop, contract


def _cheque_contract(client, auth_headers, *, rent=6000):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "CF Cheque Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "CF Cheque Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 3},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "CF Cheque Client"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": rent, "payment_mode": "cheque",
    }).get_json()["data"]
    return landlord, prop, contract


def test_empty_portfolio_forecasts_zero(app):
    with app.app_context():
        result = cashflow_service.forecast(as_of=date(2026, 1, 1))
    for bucket in result["buckets"].values():
        assert bucket == {"expected_in": 0.0, "expected_out": 0.0, "net": 0.0}


def test_cash_mode_rent_charge_counts_as_incoming(client, auth_headers, app):
    today = date.today()
    _, _, contract = _cash_contract(client, auth_headers, rent=5000)
    # Generate charges up to a month within the 90-day window so at least
    # one open RentCharge exists to forecast against.
    upto = (today + timedelta(days=60)).replace(day=1).isoformat()
    resp = client.post("/api/v1/rent/generate", headers=auth_headers,
                       json={"upto": upto, "contract_id": contract["id"]})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    with app.app_context():
        result = cashflow_service.forecast(as_of=today)
    assert result["buckets"]["90"]["expected_in"] > 0


def test_cheque_mode_contract_is_not_double_counted(client, auth_headers, app):
    today = date.today()
    _, _, contract = _cheque_contract(client, auth_headers, rent=6000)

    # Generate the accounting-side charge (RentCharge) AND register the
    # physical cheque that actually settles it, both for the same month —
    # the forecast must count this once, via the cheque, not twice.
    upto = today.replace(day=1).isoformat()
    client.post("/api/v1/rent/generate", headers=auth_headers,
               json={"upto": upto, "contract_id": contract["id"]})

    cheque_date = (today + timedelta(days=10)).isoformat()
    resp = client.post(f"/api/v1/contracts/{contract['id']}/cheques", headers=auth_headers, json={
        "cheques": [{"cheque_number": "100001", "bank_name": "QNB",
                     "cheque_date": cheque_date, "amount": 6000}],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)

    with app.app_context():
        result = cashflow_service.forecast(as_of=today)
    # Exactly one 6000 in the 30-day bucket — the cheque's contribution —
    # not 12000 (which double-counting the RentCharge too would produce).
    assert result["buckets"]["30"]["expected_in"] == 6000.0


def test_landlord_charge_counts_as_outgoing(client, auth_headers, app):
    today = date.today()
    landlord, prop, _ = _cash_contract(client, auth_headers, rent=5000)
    agreement_resp = client.post(f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers, json={
        "landlord_id": landlord["id"],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31", "monthly_rent": 4000,
    })
    assert agreement_resp.status_code == 201, agreement_resp.get_data(as_text=True)
    agreement = agreement_resp.get_json()["data"]

    upto = (today + timedelta(days=60)).replace(day=1).isoformat()
    resp = client.post("/api/v1/expenses/landlord-dues/generate", headers=auth_headers,
                       json={"upto": upto, "contract_id": agreement["id"]})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    with app.app_context():
        result = cashflow_service.forecast(as_of=today)
    assert result["buckets"]["90"]["expected_out"] > 0


def test_buckets_are_cumulative_not_deltas(client, auth_headers, app):
    today = date.today()
    _, _, contract = _cash_contract(client, auth_headers, rent=1000)
    upto = (today + timedelta(days=85)).replace(day=1).isoformat()
    client.post("/api/v1/rent/generate", headers=auth_headers,
               json={"upto": upto, "contract_id": contract["id"]})

    with app.app_context():
        result = cashflow_service.forecast(as_of=today)
    b = result["buckets"]
    assert b["30"]["expected_in"] <= b["60"]["expected_in"] <= b["90"]["expected_in"]


def test_route_requires_permission(client):
    resp = client.get("/api/v1/dashboard/cashflow-forecast")
    assert resp.status_code == 401


def test_route_returns_forecast(client, auth_headers):
    resp = client.get("/api/v1/dashboard/cashflow-forecast", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert set(data["buckets"].keys()) == {"30", "60", "90"}
