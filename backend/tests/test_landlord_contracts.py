"""Landlord contracts: per-unit allocation, amendments, and the
occupancy-isolation guarantee — mirrors test_contracts.py for the
client side."""
from datetime import date, timedelta


def _property_with_landlord(client, auth_headers, *, units_per_floor=4):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "LC Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "LC Tower", "property_type": "full_building",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": units_per_floor},
    }).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    return landlord, prop, units


def _make_agreement(client, auth_headers, prop, landlord, *, rent=20000, **extra):
    payload = {
        "landlord_id": landlord["id"],
        "start_date": "2026-01-01",
        "expiry_date": "2026-12-31",
        "monthly_rent": rent,
    }
    payload.update(extra)
    resp = client.post(f"/api/v1/properties/{prop['id']}/agreements",
                       headers=auth_headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["data"]


# --------------------------------------------------------------- creation

def test_agreement_gets_a_contract_number(client, auth_headers):
    landlord, prop, _ = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)
    assert ag["contract_number"].startswith("LCON-")
    assert ag["status"] == "active"
    assert ag["is_active"] is True
    assert ag["payment_mode"] == "cheque"


def test_landlord_contract_list_and_detail(client, auth_headers):
    landlord, prop, _ = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)

    listed = client.get("/api/v1/landlord-contracts", headers=auth_headers).get_json()["data"]
    assert any(c["id"] == ag["id"] for c in listed)

    detail = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert detail["units_count"] == 0
    assert detail["amendments"] == []

    by_q = client.get(f"/api/v1/landlord-contracts?q=LC%20Tower",
                      headers=auth_headers).get_json()["data"]
    assert any(c["id"] == ag["id"] for c in by_q)


# ------------------------------------------------------------- unit parity

def test_add_units_then_release(client, auth_headers):
    landlord, prop, units = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)

    add = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/add-units",
                      headers=auth_headers, json={
                          "unit_ids": [units[0]["id"], units[1]["id"]],
                          "effective_date": "2026-01-01", "unit_rent": 10000,
                      })
    assert add.status_code == 200, add.get_data(as_text=True)
    assert add.get_json()["data"]["amendment_type"] == "units_added"

    detail = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert detail["units_count"] == 2
    assert {u["unit"]["unit_number"] for u in detail["units"]} == {units[0]["unit_number"], units[1]["unit_number"]}

    release = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/remove-units",
                          headers=auth_headers, json={
                              "unit_ids": [units[0]["id"]], "effective_date": "2026-06-01",
                              "reason": "landlord took the store back",
                          })
    assert release.status_code == 200, release.get_data(as_text=True)

    after = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert after["units_count"] == 1
    assert after["units"][0]["unit"]["unit_number"] == units[1]["unit_number"]


def test_releasing_every_unit_is_legal_unlike_client_contracts(client, auth_headers):
    landlord, prop, units = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)
    client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/add-units",
               headers=auth_headers, json={"unit_ids": [units[0]["id"]], "effective_date": "2026-01-01"})

    resp = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/remove-units",
                       headers=auth_headers, json={
                           "unit_ids": [units[0]["id"]], "effective_date": "2026-06-01",
                           "reason": "all handed back",
                       })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    detail = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert detail["units_count"] == 0


def test_a_unit_cannot_be_sourced_from_two_landlord_contracts(client, auth_headers):
    """`create_agreement` already archives the prior active agreement
    whenever a new one is posted for the same property (one whole-
    property agreement at a time), which makes two simultaneously-
    active agreements on one property rare in normal use. It can still
    happen (a compound/mixed-use property with independent landlords
    per section, or a data anomaly) — simulate that directly to
    exercise the guard rather than relying on the everyday path."""
    landlord, prop, units = _property_with_landlord(client, auth_headers)
    ag1 = _make_agreement(client, auth_headers, prop, landlord)
    client.post(f"/api/v1/landlord-contracts/{ag1['id']}/amendments/add-units",
               headers=auth_headers, json={"unit_ids": [units[0]["id"]], "effective_date": "2026-01-01"})

    other_landlord = client.post("/api/v1/landlords", headers=auth_headers,
                                 json={"name": "Rival Owner"}).get_json()["data"]
    ag2 = _make_agreement(client, auth_headers, prop, other_landlord, rent=5000)

    from app.extensions import db
    from app.models import LandlordContract
    with client.application.app_context():
        row = LandlordContract.query.get(ag1["id"])
        row.status = "active"
        db.session.commit()

    clash = client.post(f"/api/v1/landlord-contracts/{ag2['id']}/amendments/add-units",
                        headers=auth_headers, json={"unit_ids": [units[0]["id"]], "effective_date": "2026-02-01"})
    assert clash.status_code == 409, clash.get_data(as_text=True)
    assert "already leased" in clash.get_json()["message"].lower()


def test_landlord_unit_never_touches_client_occupancy(client, auth_headers):
    """The core isolation guarantee: allocating a unit to a landlord
    contract must not mark it occupied — that projection is client-side
    only. A unit can be simultaneously sourced from a landlord and
    empty (no tenant), or sourced from a landlord AND occupied by a
    client at once."""
    landlord, prop, units = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)

    client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/add-units",
               headers=auth_headers, json={"unit_ids": [units[0]["id"]], "effective_date": "2026-01-01"})

    live = client.get(f"/api/v1/properties/{prop['id']}/units",
                      headers=auth_headers).get_json()["data"]
    by_number = {u["unit_number"]: u for u in live}
    assert by_number[units[0]["unit_number"]]["occupancy_status"] == "empty"

    # Now also let it to a client — occupancy flips from the CLIENT side,
    # independent of the landlord contract still holding it.
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Isolation Tenant"}).get_json()["data"]
    client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": 1000, "payment_mode": "cash",
    })
    live = client.get(f"/api/v1/properties/{prop['id']}/units",
                      headers=auth_headers).get_json()["data"]
    by_number = {u["unit_number"]: u for u in live}
    assert by_number[units[0]["unit_number"]]["occupancy_status"] == "occupied"

    lc_detail = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert lc_detail["units_count"] == 1, "still sourced from the landlord regardless of client occupancy"


def test_releasing_a_client_held_unit_warns_but_does_not_block(client, auth_headers):
    landlord, prop, units = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)
    client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/add-units",
               headers=auth_headers, json={"unit_ids": [units[0]["id"]], "effective_date": "2026-01-01"})

    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Mid-move Tenant"}).get_json()["data"]
    cc = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": 1000, "payment_mode": "cash",
    }).get_json()["data"]

    warned = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/remove-units",
                         headers=auth_headers, json={
                             "unit_ids": [units[0]["id"]], "effective_date": "2026-06-01",
                             "reason": "landlord reclaiming",
                         })
    assert warned.status_code == 409
    warnings = warned.get_json()["data"]["warnings"]
    assert warnings[0]["contract_number"] == cc["contract_number"]
    assert warnings[0]["client"] == "Mid-move Tenant"

    still_held = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert still_held["units_count"] == 1, "nothing changed until acknowledged"

    forced = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/remove-units",
                         headers=auth_headers, json={
                             "unit_ids": [units[0]["id"]], "effective_date": "2026-06-01",
                             "reason": "landlord reclaiming", "acknowledge_warnings": True,
                         })
    assert forced.status_code == 200, forced.get_data(as_text=True)


# ------------------------------------------------------------- amendments

def test_change_rent_and_deposit(client, auth_headers):
    landlord, prop, _ = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord, rent=20000, security_deposit=20000)

    rent = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/rent",
                       headers=auth_headers, json={"new_rent": 22000, "effective_date": "2026-06-01"})
    assert rent.status_code == 200
    assert rent.get_json()["data"]["old_rent"] == 20000
    assert rent.get_json()["data"]["new_rent"] == 22000

    dep = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/deposit",
                      headers=auth_headers, json={"new_deposit": 25000, "effective_date": "2026-06-01",
                                                  "reason": "renewal top-up"})
    assert dep.status_code == 200
    assert dep.get_json()["data"]["amendment_type"] == "deposit_change"

    detail = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert detail["monthly_rent"] == 22000
    assert detail["security_deposit"] == 25000
    assert len(detail["amendments"]) == 2


def test_free_months_granted_by_landlord(client, auth_headers):
    landlord, prop, _ = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)
    resp = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/free-months",
                       headers=auth_headers, json={"months": 2, "from_month": "2026-03-01"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["amendment_type"] == "free_months"
    assert resp.get_json()["data"]["free_months"] == 2


def test_correct_dates_fixes_a_typo(client, auth_headers):
    landlord, prop, _ = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)
    resp = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/dates",
                       headers=auth_headers, json={
                           "new_start_date": "2026-01-15", "reason": "wrong start date at signing",
                       })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    detail = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert detail["start_date"] == "2026-01-15"


def test_cancel_releases_units_and_sets_status(client, auth_headers):
    landlord, prop, units = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)
    client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/add-units",
               headers=auth_headers, json={"unit_ids": [units[0]["id"]], "effective_date": "2026-01-01"})

    cancel = client.post(f"/api/v1/landlord-contracts/{ag['id']}/cancel",
                         headers=auth_headers, json={
                             "effective_date": "2026-06-01", "reason": "landlord sold the property",
                         })
    assert cancel.status_code == 200, cancel.get_data(as_text=True)

    detail = client.get(f"/api/v1/landlord-contracts/{ag['id']}", headers=auth_headers).get_json()["data"]
    assert detail["status"] == "cancelled"
    assert detail["is_active"] is False
    assert detail["units_count"] == 0


def test_cannot_amend_a_cancelled_contract(client, auth_headers):
    landlord, prop, _ = _property_with_landlord(client, auth_headers)
    ag = _make_agreement(client, auth_headers, prop, landlord)
    client.post(f"/api/v1/landlord-contracts/{ag['id']}/cancel", headers=auth_headers,
               json={"effective_date": "2026-06-01", "reason": "closed"})

    resp = client.post(f"/api/v1/landlord-contracts/{ag['id']}/amendments/rent",
                       headers=auth_headers, json={"new_rent": 1, "effective_date": "2026-07-01"})
    assert resp.status_code == 400
    assert "cancelled" in resp.get_json()["message"].lower()
