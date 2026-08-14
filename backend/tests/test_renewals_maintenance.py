from datetime import date, timedelta


def _make_property(client, auth_headers, name="MaintP"):
    return client.post(
        "/api/v1/properties", headers=auth_headers,
        json={"name": name, "property_type": "full_building"},
    ).get_json()["data"]


def _make_landlord(client, auth_headers, name="L"):
    return client.post("/api/v1/landlords", headers=auth_headers, json={"name": name}).get_json()["data"]


def _make_floor_units(client, auth_headers, prop_id):
    f = client.post(f"/api/v1/properties/{prop_id}/floors", headers=auth_headers,
                    json={"floor_number": "1"}).get_json()["data"]
    r1 = client.post(f"/api/v1/floors/{f['id']}/units", headers=auth_headers,
                     json={"unit_number": "101"}).get_json()["data"]
    r2 = client.post(f"/api/v1/floors/{f['id']}/units", headers=auth_headers,
                     json={"unit_number": "102"}).get_json()["data"]
    return f, [r1, r2]


# ---------- Renewals ----------

def test_renewal_archives_previous_and_records_transaction(client, auth_headers):
    prop = _make_property(client, auth_headers)
    ll = _make_landlord(client, auth_headers)
    today = date.today()

    # Initial agreement via the Phase-3 endpoint
    client.post(
        f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers,
        json={
            "landlord_id": ll["id"],
            "start_date": (today - timedelta(days=200)).isoformat(),
            "expiry_date": (today + timedelta(days=30)).isoformat(),
            "monthly_rent": 10000,
        },
    )

    # Post the renewal
    resp = client.post(
        "/api/v1/renewals", headers=auth_headers,
        json={
            "property_id": prop["id"],
            "landlord_id": ll["id"],
            "new_start_date": (today + timedelta(days=31)).isoformat(),
            "new_expiry_date": (today + timedelta(days=395)).isoformat(),
            "new_monthly_rent": 11000,
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()["data"]
    assert body["transaction_number"].startswith("LRENEW-")
    assert body["old_monthly_rent"] == 10000.0
    assert body["new_monthly_rent"] == 11000.0

    # Previous archived; new active
    agreements = client.get(
        f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers,
    ).get_json()["data"]
    active = [a for a in agreements if a["is_active"]]
    archived = [a for a in agreements if not a["is_active"]]
    assert len(active) == 1
    assert active[0]["monthly_rent"] == 11000.0
    assert len(archived) == 1
    assert archived[0]["renewal_status"] == "renewed"


def test_renewal_carries_units_and_records_amendment(client, auth_headers):
    prop = _make_property(client, auth_headers, "CarryProp")
    ll = _make_landlord(client, auth_headers, "CarryLL")
    _, units = _make_floor_units(client, auth_headers, prop["id"])
    today = date.today()

    old = client.post(
        f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers,
        json={
            "landlord_id": ll["id"],
            "start_date": (today - timedelta(days=200)).isoformat(),
            "expiry_date": (today + timedelta(days=30)).isoformat(),
            "monthly_rent": 10000,
        },
    ).get_json()["data"]

    add = client.post(f"/api/v1/landlord-contracts/{old['id']}/amendments/add-units",
                      headers=auth_headers, json={
                          "unit_ids": [units[0]["id"], units[1]["id"]],
                          "effective_date": (today - timedelta(days=200)).isoformat(),
                      })
    assert add.status_code == 200, add.get_data(as_text=True)

    new_start = today + timedelta(days=31)
    resp = client.post(
        "/api/v1/renewals", headers=auth_headers,
        json={
            "property_id": prop["id"],
            "landlord_id": ll["id"],
            "new_start_date": new_start.isoformat(),
            "new_expiry_date": (today + timedelta(days=395)).isoformat(),
            "new_monthly_rent": 11000,
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    new_agreement = resp.get_json()["data"]["new_agreement"]

    new_detail = client.get(f"/api/v1/landlord-contracts/{new_agreement['id']}",
                            headers=auth_headers).get_json()["data"]
    assert new_detail["units_count"] == 2
    assert {u["unit"]["unit_number"] for u in new_detail["units"]} == {units[0]["unit_number"], units[1]["unit_number"]}

    old_detail = client.get(f"/api/v1/landlord-contracts/{old['id']}",
                            headers=auth_headers).get_json()["data"]
    assert old_detail["renewed_to_id"] == new_agreement["id"]
    # The new term starts in 31 days, so as of *today* the old contract
    # still legitimately holds the units — the handover row (`to_date`)
    # is dated the day before the new term starts, not today.
    assert old_detail["units_count"] == 2
    renewal_amendments = [a for a in old_detail["amendments"] if a["amendment_type"] == "renewal"]
    assert len(renewal_amendments) == 1
    assert renewal_amendments[0]["old_rent"] == 10000.0
    assert renewal_amendments[0]["new_rent"] == 11000.0
    assert sorted(renewal_amendments[0]["unit_ids"]) == sorted([units[0]["id"], units[1]["id"]])


def test_renewal_with_no_prior_agreement(client, auth_headers):
    prop = _make_property(client, auth_headers, "Fresh")
    ll = _make_landlord(client, auth_headers, "L2")
    today = date.today()
    resp = client.post(
        "/api/v1/renewals", headers=auth_headers,
        json={
            "property_id": prop["id"],
            "landlord_id": ll["id"],
            "new_start_date": today.isoformat(),
            "new_expiry_date": (today + timedelta(days=365)).isoformat(),
            "new_monthly_rent": 9500,
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["old_agreement"] is None
    assert data["new_agreement"]["is_active"] is True


def test_renewal_rejects_inverted_dates(client, auth_headers):
    prop = _make_property(client, auth_headers, "Inv")
    ll = _make_landlord(client, auth_headers, "L3")
    resp = client.post(
        "/api/v1/renewals", headers=auth_headers,
        json={
            "property_id": prop["id"],
            "landlord_id": ll["id"],
            "new_start_date": "2027-01-01",
            "new_expiry_date": "2026-01-01",
        },
    )
    assert resp.status_code == 400
    assert "expiry" in resp.get_json()["message"].lower()


# ---------- Maintenance ----------

def test_unit_maintenance_and_completion_restores(client, auth_headers):
    prop = _make_property(client, auth_headers, "MP4")
    _, units = _make_floor_units(client, auth_headers, prop["id"])
    unit = units[0]
    resp = client.post(
        "/api/v1/maintenance", headers=auth_headers,
        json={"entity_type": "unit", "entity_id": unit["id"], "reason": "deep clean"},
    )
    assert resp.status_code == 201
    rec = resp.get_json()["data"]

    now = client.get(f"/api/v1/units/{unit['id']}", headers=auth_headers).get_json()["data"]
    assert now["occupancy_status"] == "maintenance"

    client.post(f"/api/v1/maintenance/{rec['id']}/complete", headers=auth_headers, json={})
    after = client.get(f"/api/v1/units/{unit['id']}", headers=auth_headers).get_json()["data"]
    assert after["occupancy_status"] == "empty"


def test_cannot_maintain_occupied_unit(client, auth_headers):
    prop = _make_property(client, auth_headers, "MP4b")
    _, units = _make_floor_units(client, auth_headers, prop["id"])
    unit = units[0]
    client.post(f"/api/v1/units/{unit['id']}/status", headers=auth_headers,
                json={"status": "occupied"})

    resp = client.post(
        "/api/v1/maintenance", headers=auth_headers,
        json={"entity_type": "unit", "entity_id": unit["id"], "reason": "no"},
    )
    assert resp.status_code == 400
    assert "occupied" in resp.get_json()["message"].lower()


def test_unknown_entity_type_rejected(client, auth_headers):
    prop = _make_property(client, auth_headers, "MP4c")
    _, units = _make_floor_units(client, auth_headers, prop["id"])
    resp = client.post(
        "/api/v1/maintenance", headers=auth_headers,
        json={"entity_type": "warehouse", "entity_id": units[0]["id"]},
    )
    assert resp.status_code == 400


def test_duplicate_open_maintenance_rejected(client, auth_headers):
    prop = _make_property(client, auth_headers, "MP5")
    _, units = _make_floor_units(client, auth_headers, prop["id"])
    first = client.post(
        "/api/v1/maintenance", headers=auth_headers,
        json={"entity_type": "unit", "entity_id": units[0]["id"]},
    )
    assert first.status_code == 201
    dup = client.post(
        "/api/v1/maintenance", headers=auth_headers,
        json={"entity_type": "unit", "entity_id": units[0]["id"]},
    )
    assert dup.status_code == 400


def test_property_maintenance_round_trip(client, auth_headers):
    prop = _make_property(client, auth_headers, "MP6")
    resp = client.post(
        "/api/v1/maintenance", headers=auth_headers,
        json={"entity_type": "property", "entity_id": prop["id"], "reason": "fire safety"},
    )
    assert resp.status_code == 201
    rec = resp.get_json()["data"]
    # Property becomes inactive for assignment purposes
    p_now = client.get(f"/api/v1/properties/{prop['id']}", headers=auth_headers).get_json()["data"]
    assert p_now["status"] == "maintenance"
    # Complete restores
    client.post(f"/api/v1/maintenance/{rec['id']}/complete", headers=auth_headers, json={})
    p_after = client.get(f"/api/v1/properties/{prop['id']}", headers=auth_headers).get_json()["data"]
    assert p_after["status"] == "active"


def test_maintenance_list_filters(client, auth_headers):
    prop = _make_property(client, auth_headers, "MP7")
    _, units = _make_floor_units(client, auth_headers, prop["id"])
    client.post("/api/v1/maintenance", headers=auth_headers,
                json={"entity_type": "unit", "entity_id": units[0]["id"]})
    rows = client.get("/api/v1/maintenance?entity_type=unit", headers=auth_headers).get_json()
    assert rows["meta"]["count"] >= 1
    by_prop = client.get(f"/api/v1/maintenance?property_id={prop['id']}", headers=auth_headers).get_json()
    assert by_prop["meta"]["count"] >= 1
