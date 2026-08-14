"""Property structure: floors, units, the layout generator and renumbering.

A Unit is the atom of occupancy — rooms, flats, stores, and
shared/dedicated facilities. Contract-driven allocation arrives in
Phase 2; here occupancy is set directly via /units/{id}/status.
"""


def _make_property(client, auth_headers, name="Test P", layout=None):
    payload = {"name": name, "property_type": "full_building"}
    if layout is not None:
        payload["layout"] = layout
    return client.post("/api/v1/properties", headers=auth_headers, json=payload).get_json()["data"]


def _make_floor(client, auth_headers, prop_id, number="1"):
    return client.post(
        f"/api/v1/properties/{prop_id}/floors",
        headers=auth_headers,
        json={"floor_number": number, "floor_name": f"Floor {number}"},
    ).get_json()["data"]


def _make_unit(client, auth_headers, floor_id, number="101", unit_type="room", **extra):
    return client.post(
        f"/api/v1/floors/{floor_id}/units",
        headers=auth_headers,
        json={"unit_number": number, "unit_type": unit_type, **extra},
    ).get_json()["data"]


# ---------------------------------------------------------------- floors

def test_floor_and_unit_flow(client, auth_headers):
    prop = _make_property(client, auth_headers)

    floor = _make_floor(client, auth_headers, prop["id"], "1")
    dup = client.post(
        f"/api/v1/properties/{prop['id']}/floors",
        headers=auth_headers,
        json={"floor_number": "1"},
    )
    assert dup.status_code == 409

    unit = _make_unit(client, auth_headers, floor["id"], "101")
    assert unit["unit_number"] == "101"
    assert unit["unit_type"] == "room"
    assert unit["occupancy_status"] == "empty"

    dup_unit = client.post(
        f"/api/v1/floors/{floor['id']}/units",
        headers=auth_headers,
        json={"unit_number": "101"},
    )
    assert dup_unit.status_code == 409


def test_cannot_delete_floor_with_units(client, auth_headers):
    prop = _make_property(client, auth_headers, "Del P")
    floor = _make_floor(client, auth_headers, prop["id"], "3")
    _make_unit(client, auth_headers, floor["id"], "301")

    blocked = client.delete(f"/api/v1/floors/{floor['id']}", headers=auth_headers)
    assert blocked.status_code == 409


# ----------------------------------------------------------------- units

def test_unit_types_and_facilities(client, auth_headers):
    prop = _make_property(client, auth_headers, "Facility P")
    floor = _make_floor(client, auth_headers, prop["id"], "G")

    store = _make_unit(client, auth_headers, floor["id"], "S1", unit_type="store",
                       monthly_rent=6000)
    assert store["unit_type"] == "store"
    assert store["monthly_rent"] == 6000

    kitchen = _make_unit(client, auth_headers, floor["id"], "K1", unit_type="kitchen",
                         is_shared_facility=True)
    assert kitchen["is_shared_facility"] is True

    bad = client.post(
        f"/api/v1/floors/{floor['id']}/units",
        headers=auth_headers,
        json={"unit_number": "X1", "unit_type": "spaceship"},
    )
    assert bad.status_code == 400


def test_unit_status_transitions(client, auth_headers):
    prop = _make_property(client, auth_headers, "Status P")
    floor = _make_floor(client, auth_headers, prop["id"], "1")
    unit = _make_unit(client, auth_headers, floor["id"], "101")

    for status in ("occupied", "maintenance", "blocked", "empty"):
        r = client.post(f"/api/v1/units/{unit['id']}/status", headers=auth_headers,
                        json={"status": status})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["data"]["occupancy_status"] == status

    bad = client.post(f"/api/v1/units/{unit['id']}/status", headers=auth_headers,
                      json={"status": "on_fire"})
    assert bad.status_code == 400


def test_cannot_delete_occupied_unit(client, auth_headers):
    prop = _make_property(client, auth_headers, "Occ P")
    floor = _make_floor(client, auth_headers, prop["id"], "1")
    unit = _make_unit(client, auth_headers, floor["id"], "101")
    client.post(f"/api/v1/units/{unit['id']}/status", headers=auth_headers,
                json={"status": "occupied"})

    blocked = client.delete(f"/api/v1/units/{unit['id']}", headers=auth_headers)
    assert blocked.status_code == 409

    client.post(f"/api/v1/units/{unit['id']}/status", headers=auth_headers,
                json={"status": "empty"})
    ok = client.delete(f"/api/v1/units/{unit['id']}", headers=auth_headers)
    assert ok.status_code == 200


# ------------------------------------------------------- structure view

def test_property_structure_nests_units_under_floors(client, auth_headers):
    prop = _make_property(client, auth_headers, "Struct P")
    f1 = _make_floor(client, auth_headers, prop["id"], "1")
    f2 = _make_floor(client, auth_headers, prop["id"], "2")
    _make_unit(client, auth_headers, f1["id"], "101")
    _make_unit(client, auth_headers, f1["id"], "102")
    _make_unit(client, auth_headers, f2["id"], "201")

    resp = client.get(f"/api/v1/properties/{prop['id']}/structure", headers=auth_headers)
    assert resp.status_code == 200
    floors = resp.get_json()["data"]
    assert len(floors) == 2
    by_number = {f["floor_number"]: f for f in floors}
    assert len(by_number["1"]["units"]) == 2
    assert len(by_number["2"]["units"]) == 1

    detail = client.get(f"/api/v1/properties/{prop['id']}", headers=auth_headers).get_json()["data"]
    assert detail["floors_count"] == 2
    assert detail["units_count"] == 3


# ------------------------------------------------------ layout generator

def test_layout_creates_full_structure(client, auth_headers):
    prop = _make_property(client, auth_headers, "Layout P", layout={
        "floors": 3, "units_per_floor": 4,
    })
    assert prop["layout_generated"] == {"floors": 3, "units": 12}

    floors = client.get(f"/api/v1/properties/{prop['id']}/structure",
                        headers=auth_headers).get_json()["data"]
    assert [f["floor_number"] for f in floors] == ["1", "2", "3"]
    assert [r["unit_number"] for r in floors[0]["units"]] == ["101", "102", "103", "104"]


def test_layout_ground_floor_naming(client, auth_headers):
    prop = _make_property(client, auth_headers, "Ground P", layout={
        "floors": 2, "units_per_floor": 2, "ground_floor": True,
    })
    floors = client.get(f"/api/v1/properties/{prop['id']}/structure",
                        headers=auth_headers).get_json()["data"]
    numbers = {f["floor_number"] for f in floors}
    assert numbers == {"G", "1"}
    ground = next(f for f in floors if f["floor_number"] == "G")
    assert [r["unit_number"] for r in ground["units"]] == ["G01", "G02"]


def test_layout_respects_default_unit_type(client, auth_headers):
    prop = _make_property(client, auth_headers, "Flat P", layout={
        "floors": 1, "units_per_floor": 2, "default_unit_type": "flat_2bhk",
    })
    floors = client.get(f"/api/v1/properties/{prop['id']}/structure",
                        headers=auth_headers).get_json()["data"]
    assert all(r["unit_type"] == "flat_2bhk" for r in floors[0]["units"])


def test_layout_bounds_rejected(client, auth_headers):
    resp = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Too Big", "property_type": "full_building",
        "layout": {"floors": 999, "units_per_floor": 4},
    })
    assert resp.status_code == 400


def test_layout_invalid_unit_type_rolls_back(client, auth_headers):
    before = client.get("/api/v1/properties", headers=auth_headers).get_json()["meta"]["count"]
    resp = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Bad Type", "property_type": "full_building",
        "layout": {"floors": 1, "units_per_floor": 1, "default_unit_type": "castle"},
    })
    assert resp.status_code == 400
    after = client.get("/api/v1/properties", headers=auth_headers).get_json()["meta"]["count"]
    assert after == before, "property must not survive a failed layout"


def test_layout_refuses_when_floors_exist(app, client, auth_headers):
    """The generator is only reachable at create time over HTTP, so the
    double-build guard is exercised against the service directly."""
    import pytest
    from app.models import Property, User
    from app.services import layout as layout_service

    prop = _make_property(client, auth_headers, "Existing P")
    _make_floor(client, auth_headers, prop["id"], "1")

    with app.app_context():
        row = Property.query.get(prop["id"])
        actor = User.query.filter_by(username="admin").first()
        with pytest.raises(layout_service.LayoutError):
            layout_service.generate_structure(
                row, floors=1, units_per_floor=1, actor=actor,
            )


def test_create_without_layout_leaves_property_empty(client, auth_headers):
    prop = _make_property(client, auth_headers, "Plain P")
    assert "layout_generated" not in prop
    floors = client.get(f"/api/v1/properties/{prop['id']}/structure",
                        headers=auth_headers).get_json()["data"]
    assert floors == []


# ---------------------------------------------------------- compounds

def test_compound_builds_every_building(client, auth_headers):
    prop = _make_property(client, auth_headers, "Compound P", layout={
        "buildings": [
            {"code": "A", "floors": 2, "units_per_floor": 3, "store_count": 1},
            {"code": "B", "floors": 1, "units_per_floor": 4},
        ],
    })
    generated = prop["layout_generated"]
    assert generated["buildings"] == 2
    assert generated["rooms"] == 2 * 3 + 1 * 4          # 6 + 4
    assert generated["stores"] == 1
    assert generated["units"] == generated["rooms"] + generated["stores"]

    floors = client.get(f"/api/v1/properties/{prop['id']}/structure",
                        headers=auth_headers).get_json()["data"]
    numbers = sorted(f["floor_number"] for f in floors)
    assert numbers == ["A-1", "A-2", "A-S", "B-1"]

    a1 = next(f for f in floors if f["floor_number"] == "A-1")
    assert [u["unit_number"] for u in a1["units"]] == ["A-101", "A-102", "A-103"]
    stores = next(f for f in floors if f["floor_number"] == "A-S")
    assert [u["unit_number"] for u in stores["units"]] == ["A-S01"]
    assert stores["units"][0]["unit_type"] == "store"


def test_compound_letters_buildings_when_no_code_given(client, auth_headers):
    prop = _make_property(client, auth_headers, "Auto Letter P", layout={
        "buildings": [
            {"floors": 1, "units_per_floor": 1},
            {"floors": 1, "units_per_floor": 1},
        ],
    })
    floors = client.get(f"/api/v1/properties/{prop['id']}/structure",
                        headers=auth_headers).get_json()["data"]
    assert sorted(f["floor_number"] for f in floors) == ["A-1", "B-1"]


def test_compound_rejects_a_repeated_building_code(client, auth_headers):
    before = client.get("/api/v1/properties", headers=auth_headers).get_json()["meta"]["count"]
    resp = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Clashing Codes", "property_type": "compound",
        "layout": {"buildings": [
            {"code": "A", "floors": 1, "units_per_floor": 1},
            {"code": "A", "floors": 1, "units_per_floor": 1},
        ]},
    })
    assert resp.status_code == 400
    after = client.get("/api/v1/properties", headers=auth_headers).get_json()["meta"]["count"]
    assert after == before, "property must not survive a failed compound layout"


def test_compound_rejects_bad_bounds_on_one_building(client, auth_headers):
    resp = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Bad Building", "property_type": "compound",
        "layout": {"buildings": [
            {"code": "A", "floors": 1, "units_per_floor": 1},
            {"code": "B", "floors": 999, "units_per_floor": 1},
        ]},
    })
    assert resp.status_code == 400
    assert "Building 2" in resp.get_json()["message"]


def test_compound_refuses_when_floors_already_exist(app, client, auth_headers):
    from app.models import Property, User
    from app.services import layout as layout_service
    import pytest

    prop = _make_property(client, auth_headers, "Occupied Compound")
    _make_floor(client, auth_headers, prop["id"], "1")

    with app.app_context():
        row = Property.query.get(prop["id"])
        actor = User.query.filter_by(username="admin").first()
        with pytest.raises(layout_service.LayoutError):
            layout_service.generate_compound_structure(
                row, buildings=[{"code": "A", "floors": 1, "units_per_floor": 1}],
                actor=actor,
            )


def test_a_building_without_stores_gets_no_store_floor(client, auth_headers):
    prop = _make_property(client, auth_headers, "No Store P", layout={
        "buildings": [{"code": "A", "floors": 1, "units_per_floor": 1, "store_count": 0}],
    })
    floors = client.get(f"/api/v1/properties/{prop['id']}/structure",
                        headers=auth_headers).get_json()["data"]
    assert [f["floor_number"] for f in floors] == ["A-1"]


# --------------------------------------------------------- renumbering

def test_renumber_units_rewrites_numbers(client, auth_headers):
    prop = _make_property(client, auth_headers, "Renum P", layout={
        "floors": 1, "units_per_floor": 3,
    })
    floor = client.get(f"/api/v1/properties/{prop['id']}/floors",
                       headers=auth_headers).get_json()["data"][0]

    resp = client.post(
        f"/api/v1/properties/{prop['id']}/floors/{floor['id']}/renumber-units",
        headers=auth_headers, json={"unit_prefix": "R"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["renamed"] == 3
    numbers = sorted(r["unit_number"] for r in data["units"])
    assert numbers == ["R101", "R102", "R103"]


def test_renumber_refuses_with_occupied_unit_unless_forced(client, auth_headers):
    prop = _make_property(client, auth_headers, "Force P", layout={
        "floors": 1, "units_per_floor": 2,
    })
    floor = client.get(f"/api/v1/properties/{prop['id']}/floors",
                       headers=auth_headers).get_json()["data"][0]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    client.post(f"/api/v1/units/{units[0]['id']}/status", headers=auth_headers,
                json={"status": "occupied"})

    blocked = client.post(
        f"/api/v1/properties/{prop['id']}/floors/{floor['id']}/renumber-units",
        headers=auth_headers, json={"unit_prefix": "R"},
    )
    assert blocked.status_code == 409
    assert blocked.get_json()["details"]["force_required"] is True

    forced = client.post(
        f"/api/v1/properties/{prop['id']}/floors/{floor['id']}/renumber-units",
        headers=auth_headers, json={"unit_prefix": "R", "force": True},
    )
    assert forced.status_code == 200
    assert forced.get_json()["data"]["renamed"] == 2


def test_renumber_no_op_when_numbers_already_match(client, auth_headers):
    prop = _make_property(client, auth_headers, "NoOp P", layout={
        "floors": 1, "units_per_floor": 2,
    })
    floor = client.get(f"/api/v1/properties/{prop['id']}/floors",
                       headers=auth_headers).get_json()["data"][0]

    resp = client.post(
        f"/api/v1/properties/{prop['id']}/floors/{floor['id']}/renumber-units",
        headers=auth_headers, json={"unit_prefix": ""},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["renamed"] == 0
