"""Unit Types master — mirrors PropertyType's deactivate-only,
never-hard-deleted pattern (see test_masters.py's property-type tests),
extended with `is_facility` and `bulk_mode`, the two fields the property
layout wizard reads to decide how a building of that type generates its
floors/units."""


def _make_property(client, auth_headers, name="UT Prop"):
    return client.post("/api/v1/properties", headers=auth_headers,
                       json={"name": name, "property_type": "full_building"}).get_json()["data"]


def _make_floor(client, auth_headers, prop_id, number="1"):
    return client.post(f"/api/v1/properties/{prop_id}/floors", headers=auth_headers,
                       json={"floor_number": number}).get_json()["data"]


def test_unit_type_seeded_and_classified(client, auth_headers):
    seeded = client.get("/api/v1/units/types", headers=auth_headers).get_json()["data"]
    by_code = {t["code"]: t for t in seeded}
    assert {"room", "store", "kitchen", "shop"} <= set(by_code)
    assert all(t["is_active"] for t in seeded)

    assert by_code["room"]["bulk_mode"] == "floors"
    assert by_code["room"]["is_facility"] is False
    assert by_code["kitchen"]["bulk_mode"] == "floors"
    assert by_code["kitchen"]["is_facility"] is True
    assert by_code["store"]["bulk_mode"] == "count"
    assert by_code["store"]["is_facility"] is False


def test_unit_type_create_deactivate_and_reject_unknown(client, auth_headers):
    created = client.post("/api/v1/units/types", headers=auth_headers,
                          json={"name": "Warehouse", "bulk_mode": "count"})
    assert created.status_code == 201, created.get_data(as_text=True)
    utype = created.get_json()["data"]
    assert utype["code"] == "WAREHOUSE"
    assert utype["bulk_mode"] == "count"
    assert utype["is_facility"] is False

    dup = client.post("/api/v1/units/types", headers=auth_headers,
                      json={"name": "warehouse"})
    assert dup.status_code == 409

    prop = _make_property(client, auth_headers, "WH Prop")
    floor = _make_floor(client, auth_headers, prop["id"])
    unit = client.post(f"/api/v1/floors/{floor['id']}/units", headers=auth_headers,
                       json={"unit_number": "W1", "unit_type": "WAREHOUSE"})
    assert unit.status_code == 201, unit.get_data(as_text=True)

    off = client.patch(f"/api/v1/units/types/{utype['id']}", headers=auth_headers,
                       json={"is_active": False})
    assert off.status_code == 200
    assert off.get_json()["data"]["is_active"] is False

    active_only = client.get("/api/v1/units/types?active_only=1",
                             headers=auth_headers).get_json()["data"]
    assert "WAREHOUSE" not in {t["code"] for t in active_only}

    blocked = client.post(f"/api/v1/floors/{floor['id']}/units", headers=auth_headers,
                          json={"unit_number": "W2", "unit_type": "WAREHOUSE"})
    assert blocked.status_code == 400


def test_deactivated_unit_type_stays_valid_on_its_own_unit(client, auth_headers):
    created = client.post("/api/v1/units/types", headers=auth_headers,
                          json={"name": "Legacy Type"}).get_json()["data"]
    prop = _make_property(client, auth_headers, "Legacy Prop")
    floor = _make_floor(client, auth_headers, prop["id"])
    unit = client.post(f"/api/v1/floors/{floor['id']}/units", headers=auth_headers,
                       json={"unit_number": "L1", "unit_type": created["code"]}).get_json()["data"]

    client.patch(f"/api/v1/units/types/{created['id']}", headers=auth_headers,
                json={"is_active": False})

    unchanged = client.put(f"/api/v1/units/{unit['id']}", headers=auth_headers,
                           json={"remarks": "still fine", "unit_type": created["code"]})
    assert unchanged.status_code == 200, unchanged.get_data(as_text=True)

    switch_away = client.put(f"/api/v1/units/{unit['id']}", headers=auth_headers,
                             json={"unit_type": "room"})
    assert switch_away.status_code == 200

    switch_back = client.put(f"/api/v1/units/{unit['id']}", headers=auth_headers,
                             json={"unit_type": created["code"]})
    assert switch_back.status_code == 400


def test_bulk_mode_update_is_validated(client, auth_headers):
    created = client.post("/api/v1/units/types", headers=auth_headers,
                          json={"name": "Odd Type"}).get_json()["data"]
    bad = client.patch(f"/api/v1/units/types/{created['id']}", headers=auth_headers,
                       json={"bulk_mode": "sideways"})
    assert bad.status_code == 400

    good = client.patch(f"/api/v1/units/types/{created['id']}", headers=auth_headers,
                        json={"bulk_mode": "count", "is_facility": True})
    assert good.status_code == 200
    data = good.get_json()["data"]
    assert data["bulk_mode"] == "count"
    assert data["is_facility"] is True
