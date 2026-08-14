def _seed(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Searchable LL", "qid_cr_number": "CR-7777"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers,
                       json={"name": "FindMe Tower", "property_type": "full_building",
                             "city": "Doha", "landlord_id": landlord["id"]}).get_json()["data"]
    floor = client.post(f"/api/v1/properties/{prop['id']}/floors", headers=auth_headers,
                        json={"floor_number": "1"}).get_json()["data"]
    unit = client.post(f"/api/v1/floors/{floor['id']}/units", headers=auth_headers,
                       json={"unit_number": "707"}).get_json()["data"]
    return prop, unit, landlord


def test_search_min_chars(client, auth_headers):
    r = client.get("/api/v1/search?q=a", headers=auth_headers)
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["properties"] == []
    assert data["units"] == []
    assert data["landlords"] == []


def test_search_finds_property_by_name(client, auth_headers):
    prop, *_ = _seed(client, auth_headers)
    r = client.get("/api/v1/search?q=findme", headers=auth_headers)
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert any(p["id"] == prop["id"] for p in data["properties"])
    assert data["properties"][0]["href"] == f"/properties/{prop['id']}"


def test_search_finds_unit_by_number(client, auth_headers):
    _, unit, _ = _seed(client, auth_headers)
    r = client.get("/api/v1/search?q=707", headers=auth_headers)
    assert any(u["id"] == unit["id"] for u in r.get_json()["data"]["units"])


def test_search_finds_landlord_by_qid(client, auth_headers):
    _, _, ll = _seed(client, auth_headers)
    r = client.get("/api/v1/search?q=cr-7777", headers=auth_headers)
    assert any(x["id"] == ll["id"] for x in r.get_json()["data"]["landlords"])


def test_search_finds_client_contract_by_number(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Search Contract Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Search Contract Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 2},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Search Contract Client"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]],
        "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": 1000, "payment_mode": "cash",
    }).get_json()["data"]

    needle = contract["contract_number"][-6:].lower()
    r = client.get(f"/api/v1/search?q={needle}", headers=auth_headers)
    assert r.status_code == 200
    hits = r.get_json()["data"]["contracts"]
    assert any(h["id"] == contract["id"] for h in hits)


def test_search_min_chars_includes_new_groups(client, auth_headers):
    r = client.get("/api/v1/search?q=a", headers=auth_headers)
    data = r.get_json()["data"]
    assert data["contracts"] == []
    assert data["agreements"] == []
