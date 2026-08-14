"""Client contracts: allocation, amendments, cancellation, renewal.

Scenarios mirror real rows from the New-2026 sheet — a client holding
several numbered rooms, a mid-year rent reduction, dropping rooms, and
a CANCELLED contract.
"""
from datetime import date, timedelta

from app.extensions import db
from app.services import contracts as contract_service


def _scaffold(client, auth_headers, *, units_per_floor=5, floors=1):
    """A property with numbered units, plus a client to let them to."""
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "ST-36 Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "ST-36", "property_type": "building_with_store",
        "landlord_id": landlord["id"],
        "layout": {"floors": floors, "units_per_floor": units_per_floor},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "IMDAAD FACILITY SERVICES"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    return prop, tenant, units


def _make_contract(client, auth_headers, prop, tenant, units, *,
                   mode="cash", rent=5400, **extra):
    payload = {
        "client_id": tenant["id"],
        "property_id": prop["id"],
        "unit_ids": [u["id"] for u in units],
        "start_date": "2026-01-01",
        "expiry_date": "2026-12-31",
        "monthly_rent": rent,
        "payment_mode": mode,
    }
    payload.update(extra)
    return client.post("/api/v1/contracts", headers=auth_headers, json=payload)


# ------------------------------------------------------------- creation

def test_create_contract_allocates_named_units(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    resp = _make_contract(client, auth_headers, prop, tenant, units[:3],
                          opening_balance=47100, security_deposit=5400)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    c = resp.get_json()["data"]

    assert c["contract_number"].startswith("CON-")
    assert c["status"] == "active"
    assert c["units_count"] == 3
    assert c["opening_balance"] == 47100
    assert c["security_deposit"] == 5400
    assert sorted(u["unit"]["unit_number"] for u in c["units"]) == ["101", "102", "103"]

    # Occupancy is derived, not typed.
    live = client.get(f"/api/v1/properties/{prop['id']}/units",
                      headers=auth_headers).get_json()["data"]
    by_number = {u["unit_number"]: u for u in live}
    assert by_number["101"]["occupancy_status"] == "occupied"
    assert by_number["104"]["occupancy_status"] == "empty"


def test_cannot_double_let_a_unit(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    first = _make_contract(client, auth_headers, prop, tenant, units[:2])
    assert first.status_code == 201

    other = client.post("/api/v1/clients", headers=auth_headers,
                        json={"name": "Second Co"}).get_json()["data"]
    clash = _make_contract(client, auth_headers, prop, other, units[1:3])
    assert clash.status_code == 409
    msg = clash.get_json()["message"]
    assert "102" in msg and "CON-" in msg


def test_contract_rejects_units_from_another_property(client, auth_headers):
    prop_a, tenant, units_a = _scaffold(client, auth_headers)
    prop_b, _, units_b = _scaffold(client, auth_headers)
    resp = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop_a["id"],
        "unit_ids": [units_b[0]["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 1000, "payment_mode": "cash",
    })
    assert resp.status_code == 400
    assert "do not belong" in resp.get_json()["message"]


def test_shared_facility_cannot_be_allocated(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    floors = client.get(f"/api/v1/properties/{prop['id']}/floors",
                        headers=auth_headers).get_json()["data"]
    kitchen = client.post(f"/api/v1/floors/{floors[0]['id']}/units", headers=auth_headers,
                          json={"unit_number": "K1", "unit_type": "kitchen",
                                "is_shared_facility": True}).get_json()["data"]
    resp = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [kitchen["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 500, "payment_mode": "cash",
    })
    assert resp.status_code == 400
    assert "shared" in resp.get_json()["message"].lower()


def test_dedicated_facility_can_be_allocated(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    floors = client.get(f"/api/v1/properties/{prop['id']}/floors",
                        headers=auth_headers).get_json()["data"]
    kitchen = client.post(f"/api/v1/floors/{floors[0]['id']}/units", headers=auth_headers,
                          json={"unit_number": "K2", "unit_type": "kitchen",
                                "is_shared_facility": False}).get_json()["data"]
    resp = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"], kitchen["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 5400, "payment_mode": "cash",
    })
    assert resp.status_code == 201
    assert resp.get_json()["data"]["units_count"] == 2


def test_contract_validation(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)

    no_units = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"], "unit_ids": [],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 100, "payment_mode": "cash"})
    assert no_units.status_code == 400

    bad_mode = _make_contract(client, auth_headers, prop, tenant, units[:1], mode="barter")
    assert bad_mode.status_code == 400

    inverted = _make_contract(client, auth_headers, prop, tenant, units[:1],
                              start_date="2026-12-31", expiry_date="2026-01-01")
    assert inverted.status_code == 400


def test_available_units_endpoint_marks_held_ones(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    _make_contract(client, auth_headers, prop, tenant, units[:2])

    resp = client.get(f"/api/v1/contracts/available-units?property_id={prop['id']}",
                      headers=auth_headers)
    assert resp.status_code == 200
    rows = {r["unit_number"]: r for r in resp.get_json()["data"]}
    assert rows["101"]["is_available"] is False
    assert rows["101"]["held_by"]["client_name"] == "IMDAAD FACILITY SERVICES"
    assert rows["103"]["is_available"] is True
    assert resp.get_json()["meta"]["available"] == 3


# ------------------------------------------------------------ amendments

def test_rent_reduction_is_a_dated_amendment(client, auth_headers):
    """The 28,000 -> 26,000 mid-year case from the New-2026 sheet."""
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1],
                       rent=28000).get_json()["data"]

    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                       json={"new_rent": 26000, "effective_date": "2026-04-01",
                             "reason": "negotiated reduction"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    amendment = resp.get_json()["data"]
    assert amendment["amendment_type"] == "rent_change"
    assert amendment["old_rent"] == 28000
    assert amendment["new_rent"] == 26000
    assert amendment["effective_date"] == "2026-04-01"
    assert amendment["sequence"] == 1

    detail = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert detail["monthly_rent"] == 26000
    assert len(detail["amendments"]) == 1, "history preserved, not overwritten"


def test_rent_change_rejects_no_op(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1], rent=5000).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                       json={"new_rent": 5000, "effective_date": "2026-04-01"})
    assert resp.status_code == 400


def test_free_months_recorded(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1]).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/free-months",
                       headers=auth_headers,
                       json={"months": 2, "from_month": "2026-02-15",
                             "reason": "fit-out period"})
    assert resp.status_code == 200
    a = resp.get_json()["data"]
    assert a["amendment_type"] == "free_months"
    assert a["free_months"] == 2
    assert a["free_from_month"] == "2026-02-01", "normalised to the 1st"


def test_drop_two_of_five_rooms(client, auth_headers):
    """The phase's headline case: reduce the room count on a live contract."""
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:5]).get_json()["data"]
    assert c["units_count"] == 5

    drop = [units[3]["id"], units[4]["id"]]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/remove-units",
                       headers=auth_headers,
                       json={"unit_ids": drop, "effective_date": "2026-06-30",
                             "reason": "client downsized"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["amendment_type"] == "units_removed"

    detail = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert detail["units_count"] == 3
    assert sorted(u["unit"]["unit_number"] for u in detail["units"]) == ["101", "102", "103"]

    live = {u["unit_number"]: u for u in client.get(
        f"/api/v1/properties/{prop['id']}/units", headers=auth_headers).get_json()["data"]}
    assert live["104"]["occupancy_status"] == "empty"
    assert live["105"]["occupancy_status"] == "empty"
    assert live["103"]["occupancy_status"] == "occupied"

    # The released units are free for someone else.
    other = client.post("/api/v1/clients", headers=auth_headers,
                        json={"name": "Next Tenant"}).get_json()["data"]
    reuse = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": other["id"], "property_id": prop["id"], "unit_ids": drop,
        "start_date": "2026-07-01", "expiry_date": "2027-06-30",
        "monthly_rent": 2000, "payment_mode": "cash"})
    assert reuse.status_code == 201


def test_cannot_remove_every_unit(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:2]).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/remove-units",
                       headers=auth_headers,
                       json={"unit_ids": [units[0]["id"], units[1]["id"]],
                             "effective_date": "2026-06-30"})
    assert resp.status_code == 400
    assert "cancel the contract" in resp.get_json()["message"].lower()


def test_cannot_remove_a_unit_not_held(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:2]).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/remove-units",
                       headers=auth_headers,
                       json={"unit_ids": [units[4]["id"]], "effective_date": "2026-06-30"})
    assert resp.status_code == 400


def test_add_units_to_a_live_contract(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:2]).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/add-units",
                       headers=auth_headers,
                       json={"unit_ids": [units[2]["id"]], "effective_date": "2026-03-01",
                             "reason": "expanded"})
    assert resp.status_code == 200
    detail = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert detail["units_count"] == 3


def test_add_units_rejects_one_already_let(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    mine = _make_contract(client, auth_headers, prop, tenant, units[:2]).get_json()["data"]
    other = client.post("/api/v1/clients", headers=auth_headers,
                        json={"name": "Rival"}).get_json()["data"]
    client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": other["id"], "property_id": prop["id"],
        "unit_ids": [units[3]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": 1000, "payment_mode": "cash"})

    resp = client.post(f"/api/v1/contracts/{mine['id']}/amendments/add-units",
                       headers=auth_headers,
                       json={"unit_ids": [units[3]["id"]], "effective_date": "2026-03-01"})
    assert resp.status_code == 409


# ---------------------------------------------------------- cancellation

def test_cancellation_releases_units_and_keeps_history(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:3]).get_json()["data"]

    resp = client.post(f"/api/v1/contracts/{c['id']}/cancel", headers=auth_headers,
                       json={"effective_date": "2026-05-31", "reason": "client vacated"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    detail = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert detail["status"] == "cancelled"
    assert detail["cancellation_date"] == "2026-05-31"
    assert detail["cancellation_reason"] == "client vacated"
    assert detail["units_count"] == 0, "no units held today"

    live = {u["unit_number"]: u for u in client.get(
        f"/api/v1/properties/{prop['id']}/units", headers=auth_headers).get_json()["data"]}
    assert all(live[n]["occupancy_status"] == "empty" for n in ("101", "102", "103"))

    # The allocation rows survive so past occupancy is reconstructable.
    assert any(a["amendment_type"] == "cancellation" for a in detail["amendments"])


def test_cancellation_requires_a_reason(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1]).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/cancel", headers=auth_headers,
                       json={"effective_date": "2026-05-31"})
    assert resp.status_code == 400


def test_cancelled_contract_cannot_be_amended(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1]).get_json()["data"]
    client.post(f"/api/v1/contracts/{c['id']}/cancel", headers=auth_headers,
                json={"effective_date": "2026-05-31", "reason": "gone"})

    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/rent", headers=auth_headers,
                       json={"new_rent": 1, "effective_date": "2026-06-01"})
    assert resp.status_code == 400
    assert "cancelled" in resp.get_json()["message"].lower()


# --------------------------------------------------------------- renewal

def test_renewal_carries_units_and_supersedes(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:2],
                       rent=5400).get_json()["data"]

    resp = client.post(f"/api/v1/contracts/{c['id']}/renew", headers=auth_headers,
                       json={"new_start_date": "2027-01-01",
                             "new_expiry_date": "2027-12-31",
                             "new_monthly_rent": 5800})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    renewal = resp.get_json()["data"]
    assert renewal["monthly_rent"] == 5800
    assert renewal["units_count"] == 2, "same units carried forward"
    assert renewal["contract_number"] != c["contract_number"]

    old = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert old["status"] == "renewed"
    assert old["renewed_to_id"] == renewal["id"]

    # Units stay occupied across the handover.
    live = {u["unit_number"]: u for u in client.get(
        f"/api/v1/properties/{prop['id']}/units", headers=auth_headers).get_json()["data"]}
    assert live["101"]["occupancy_status"] == "occupied"


# --------------------------------------------------------- dates correction

def test_correct_dates_fixes_typo_and_shifts_allocation(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1]).get_json()["data"]

    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/dates", headers=auth_headers,
                       json={"new_start_date": "2026-01-15", "reason": "wrong start date at signing"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    detail = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert detail["start_date"] == "2026-01-15"
    assert detail["expiry_date"] == "2026-12-31", "left blank, stays unchanged"
    assert detail["status"] == "active", "same contract number, not superseded"
    assert detail["units"][0]["from_date"] == "2026-01-15", "allocation kept in sync"

    correction = next(a for a in detail["amendments"] if a["amendment_type"] == "dates_correction")
    assert correction["old_start_date"] == "2026-01-01"
    assert correction["new_start_date"] == "2026-01-15"
    assert correction["reason"] == "wrong start date at signing"


def test_correct_dates_requires_a_reason(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1]).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/dates", headers=auth_headers,
                       json={"new_expiry_date": "2027-06-30"})
    assert resp.status_code == 400


def test_correct_dates_rejects_expiry_before_start(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1]).get_json()["data"]
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/dates", headers=auth_headers,
                       json={"new_expiry_date": "2025-01-01", "reason": "typo"})
    assert resp.status_code == 400
    assert "before the start date" in resp.get_json()["message"]


def test_cancelled_contract_dates_cannot_be_corrected(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    c = _make_contract(client, auth_headers, prop, tenant, units[:1]).get_json()["data"]
    client.post(f"/api/v1/contracts/{c['id']}/cancel", headers=auth_headers,
                json={"effective_date": "2026-05-31", "reason": "gone"})

    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/dates", headers=auth_headers,
                       json={"new_start_date": "2026-01-15", "reason": "typo"})
    assert resp.status_code == 400
    assert "cancelled" in resp.get_json()["message"].lower()


def test_correct_dates_reopens_a_contract_the_sweep_wrongly_expired(client, auth_headers, app):
    prop, tenant, units = _scaffold(client, auth_headers)
    past_expiry = (date.today() - timedelta(days=5)).isoformat()
    c = _make_contract(client, auth_headers, prop, tenant, units[:1],
                       start_date="2025-01-01", expiry_date=past_expiry).get_json()["data"]

    with app.app_context():
        touched = contract_service.expire_due_contracts()
        db.session.commit()
    assert c["id"] in touched

    expired = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert expired["status"] == "expired"
    live = {u["unit_number"]: u for u in client.get(
        f"/api/v1/properties/{prop['id']}/units", headers=auth_headers).get_json()["data"]}
    assert live[units[0]["unit_number"]]["occupancy_status"] == "empty"

    future_expiry = (date.today() + timedelta(days=180)).isoformat()
    resp = client.post(f"/api/v1/contracts/{c['id']}/amendments/dates", headers=auth_headers,
                       json={"new_expiry_date": future_expiry,
                             "reason": "expiry date was entered wrong, contract is still running"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    fixed = client.get(f"/api/v1/contracts/{c['id']}", headers=auth_headers).get_json()["data"]
    assert fixed["status"] == "active"
    assert fixed["units"][0]["to_date"] is None, "reopened, not left closed at the old expiry"
    live = {u["unit_number"]: u for u in client.get(
        f"/api/v1/properties/{prop['id']}/units", headers=auth_headers).get_json()["data"]}
    assert live[units[0]["unit_number"]]["occupancy_status"] == "occupied"


# ------------------------------------------------------------- listing

def test_list_filters_and_expiring(client, auth_headers):
    prop, tenant, units = _scaffold(client, auth_headers)
    soon = (date.today() + timedelta(days=20)).isoformat()
    client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2025-01-01",
        "expiry_date": soon, "monthly_rent": 1400, "payment_mode": "cheque"})
    _make_contract(client, auth_headers, prop, tenant, units[1:2], mode="cash")

    by_mode = client.get("/api/v1/contracts?mode=cheque", headers=auth_headers).get_json()
    assert by_mode["meta"]["count"] == 1

    by_client = client.get(f"/api/v1/contracts?client_id={tenant['id']}",
                           headers=auth_headers).get_json()
    assert by_client["meta"]["count"] == 2

    expiring = client.get("/api/v1/contracts/expiring?days=30",
                          headers=auth_headers).get_json()
    assert expiring["meta"]["count"] == 1
    assert expiring["data"][0]["days_left"] == 20


def test_contract_endpoints_require_auth(client):
    assert client.get("/api/v1/contracts").status_code == 401
