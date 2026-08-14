from datetime import date, timedelta


def _scaffold(client, auth_headers):
    prop = client.post("/api/v1/properties", headers=auth_headers,
                       json={"name": "P", "property_type": "full_building"}).get_json()["data"]
    floor = client.post(f"/api/v1/properties/{prop['id']}/floors", headers=auth_headers,
                        json={"floor_number": "1"}).get_json()["data"]
    r1 = client.post(f"/api/v1/floors/{floor['id']}/units", headers=auth_headers,
                     json={"unit_number": "101"}).get_json()["data"]
    r2 = client.post(f"/api/v1/floors/{floor['id']}/units", headers=auth_headers,
                     json={"unit_number": "102"}).get_json()["data"]
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "L"}).get_json()["data"]
    return prop, floor, [r1, r2], landlord


def test_summary_endpoint(client, auth_headers):
    prop, _, units, _ = _scaffold(client, auth_headers)
    client.post(f"/api/v1/units/{units[0]['id']}/status", headers=auth_headers,
                json={"status": "occupied"})

    resp = client.get("/api/v1/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["properties"]["total"] >= 1
    assert data["units"]["total"] == 2
    assert data["units"]["occupied"] == 1
    assert data["units"]["empty"] == 1
    assert data["units"]["occupancy_percent"] == 50.0
    assert data["landlords"]["total"] >= 1
    assert "expired" in data["agreement_expiry"]
    assert "total" in data["approvals"]
    assert data["open_maintenance"] == 0


def test_alerts_endpoint(client, auth_headers):
    prop, _, units, landlord = _scaffold(client, auth_headers)
    today = date.today()

    # An agreement expiring in 5 days on the property
    client.post(f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers,
                json={
                    "landlord_id": landlord["id"],
                    "start_date": (today - timedelta(days=200)).isoformat(),
                    "expiry_date": (today + timedelta(days=5)).isoformat(),
                    "monthly_rent": 1000,
                })

    # An in-progress maintenance record on a unit
    m = client.post("/api/v1/maintenance", headers=auth_headers,
                    json={"entity_type": "unit", "entity_id": units[1]["id"], "reason": "fix"})
    assert m.status_code == 201, m.get_data(as_text=True)

    resp = client.get("/api/v1/dashboard/alerts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert len(body["critical"]["expiring_within_7_days"]) >= 1
    assert len(body["info"]["maintenance_in_progress"]) >= 1
    assert body["counts"]["critical"] >= 1
    assert body["counts"]["info"] >= 1
    assert "generated_at" in body


def test_activity_feed_reads_audit_log(client, auth_headers):
    _scaffold(client, auth_headers)

    resp = client.get("/api/v1/dashboard/activity?limit=5", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.get_json()["data"]
    assert len(rows) >= 1
    modules = {r["module"] for r in rows}
    assert "property" in modules or "unit" in modules
    assert all("username" in r for r in rows)


def test_occupancy_by_property_chart(client, auth_headers):
    prop, _, units, _ = _scaffold(client, auth_headers)
    client.post(f"/api/v1/units/{units[0]['id']}/status", headers=auth_headers,
                json={"status": "occupied"})

    resp = client.get("/api/v1/dashboard/charts/occupancy-by-property", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.get_json()["data"]
    by_id = {r["property_id"]: r for r in rows}
    assert by_id[prop["id"]]["total_units"] == 2
    assert by_id[prop["id"]]["occupied"] == 1
    assert by_id[prop["id"]]["empty"] == 1
    assert by_id[prop["id"]]["occupancy_percent"] == 50.0


def test_dashboard_requires_permission(client):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401
