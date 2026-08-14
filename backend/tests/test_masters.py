import io
from datetime import date, timedelta


def test_landlord_create(client, auth_headers):
    resp = client.post(
        "/api/v1/landlords",
        headers=auth_headers,
        json={"name": "Al Mansoor Holdings", "mobile": "+97455551234"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["code"].startswith("LL-")


def test_property_with_agreement_and_expiry(client, auth_headers):
    landlord = client.post(
        "/api/v1/landlords", headers=auth_headers, json={"name": "Al Faris Properties"}
    ).get_json()["data"]

    prop = client.post(
        "/api/v1/properties",
        headers=auth_headers,
        json={
            "name": "Doha Building 12",
            "property_type": "full_building",
            "city": "Doha",
            "zone": "27",
        },
    )
    assert prop.status_code == 201, prop.get_data(as_text=True)
    p = prop.get_json()["data"]
    assert p["code"].startswith("PROP-")

    today = date.today()
    near_expiry = (today + timedelta(days=20)).isoformat()
    ag = client.post(
        f"/api/v1/properties/{p['id']}/agreements",
        headers=auth_headers,
        json={
            "landlord_id": landlord["id"],
            "start_date": (today - timedelta(days=300)).isoformat(),
            "expiry_date": near_expiry,
            "monthly_rent": 12000,
            "agreement_number": "AGR-2025-001",
        },
    )
    assert ag.status_code == 201, ag.get_data(as_text=True)

    # Renewal: posting a second active agreement archives the previous one
    new_expiry = (today + timedelta(days=400)).isoformat()
    ag2 = client.post(
        f"/api/v1/properties/{p['id']}/agreements",
        headers=auth_headers,
        json={
            "landlord_id": landlord["id"],
            "start_date": near_expiry,
            "expiry_date": new_expiry,
            "monthly_rent": 13000,
        },
    )
    assert ag2.status_code == 201
    all_agreements = client.get(
        f"/api/v1/properties/{p['id']}/agreements", headers=auth_headers
    ).get_json()["data"]
    active = [a for a in all_agreements if a["is_active"]]
    archived = [a for a in all_agreements if not a["is_active"]]
    assert len(active) == 1
    assert len(archived) == 1
    assert archived[0]["renewal_status"] == "renewed"

    # Detail view exposes active agreement
    detail = client.get(f"/api/v1/properties/{p['id']}", headers=auth_headers).get_json()["data"]
    assert detail["active_agreement"]["id"] == active[0]["id"]


def test_expiring_agreements_buckets(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers, json={"name": "Bucket LL"}).get_json()["data"]
    today = date.today()

    for name, days_from_now in [("near", 5), ("medium", 25), ("far", 80), ("expired", -3)]:
        prop = client.post(
            "/api/v1/properties",
            headers=auth_headers,
            json={"name": f"Bucket {name}", "property_type": "villa"},
        ).get_json()["data"]
        client.post(
            f"/api/v1/properties/{prop['id']}/agreements",
            headers=auth_headers,
            json={
                "landlord_id": landlord["id"],
                "start_date": (today - timedelta(days=200)).isoformat(),
                "expiry_date": (today + timedelta(days=days_from_now)).isoformat(),
            },
        )

    resp = client.get("/api/v1/properties/agreements/expiring?days=90", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()
    by_bucket = {row["bucket"] for row in body["data"]}
    assert "7" in by_bucket
    assert "30" in by_bucket
    assert "90" in by_bucket
    assert "expired" in by_bucket
    summary = body["meta"]["summary"]
    assert summary["expired"] >= 1


def test_attachment_upload_and_download(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers, json={"name": "Att LL"}).get_json()["data"]
    prop = client.post(
        "/api/v1/properties",
        headers=auth_headers,
        json={"name": "Attach P", "property_type": "flat_building"},
    ).get_json()["data"]
    client.post(
        f"/api/v1/properties/{prop['id']}/agreements",
        headers=auth_headers,
        json={
            "landlord_id": landlord["id"],
            "start_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )

    data = {
        "entity_type": "property",
        "entity_id": str(prop["id"]),
        "category": "agreement",
        "file": (io.BytesIO(b"%PDF-1.4 test"), "agreement.pdf"),
    }
    resp = client.post(
        "/api/v1/attachments",
        headers=auth_headers,
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    att_id = resp.get_json()["data"]["id"]

    listed = client.get(
        f"/api/v1/attachments?entity_type=property&entity_id={prop['id']}",
        headers=auth_headers,
    ).get_json()
    assert listed["meta"]["count"] == 1

    dl = client.get(f"/api/v1/attachments/{att_id}/download", headers=auth_headers)
    assert dl.status_code == 200
    assert dl.data.startswith(b"%PDF")


def test_property_view_requires_permission(client):
    resp = client.get("/api/v1/properties")
    assert resp.status_code == 401


def _make_property(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "LL Status"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers,
                       json={"name": "Status HQ", "property_type": "full_building",
                             "landlord_id": landlord["id"]}).get_json()["data"]
    return prop, landlord


def test_status_change_happy_path(client, auth_headers):
    prop, _ = _make_property(client, auth_headers)
    r = client.post(f"/api/v1/properties/{prop['id']}/status", headers=auth_headers,
                    json={"status": "on_hold", "reason": "agreement-expired"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["data"]["status"] == "on_hold"


def test_status_change_rejects_invalid_status(client, auth_headers):
    prop, _ = _make_property(client, auth_headers)
    r = client.post(f"/api/v1/properties/{prop['id']}/status", headers=auth_headers,
                    json={"status": "exploded", "reason": "x"})
    assert r.status_code == 400


def test_status_change_requires_reason_when_leaving_active(client, auth_headers):
    prop, _ = _make_property(client, auth_headers)
    r = client.post(f"/api/v1/properties/{prop['id']}/status", headers=auth_headers,
                    json={"status": "inactive"})
    assert r.status_code == 400
    assert "reason" in r.get_json()["message"].lower()


def test_status_change_blocked_by_occupancy(client, auth_headers):
    prop, _ = _make_property(client, auth_headers)
    floor = client.post(f"/api/v1/properties/{prop['id']}/floors", headers=auth_headers,
                        json={"floor_number": "1"}).get_json()["data"]
    unit = client.post(f"/api/v1/floors/{floor['id']}/units", headers=auth_headers,
                       json={"unit_number": "101"}).get_json()["data"]
    occ = client.post(f"/api/v1/units/{unit['id']}/status", headers=auth_headers,
                      json={"status": "occupied"})
    assert occ.status_code == 200, occ.get_data(as_text=True)

    r = client.post(f"/api/v1/properties/{prop['id']}/status", headers=auth_headers,
                    json={"status": "inactive", "reason": "shutting down"})
    assert r.status_code == 409, r.get_data(as_text=True)
    body = r.get_json()
    assert body["details"]["blocked"] is True
    assert body["details"]["occupied"] == 1
    assert any(u["unit_number"] == "101" for u in body["details"]["sample_units"])


def test_put_status_now_rejected(client, auth_headers):
    prop, _ = _make_property(client, auth_headers)
    r = client.put(f"/api/v1/properties/{prop['id']}", headers=auth_headers,
                   json={"status": "on_hold"})
    assert r.status_code == 400
    assert "/status" in r.get_json()["message"]


# --------------------------------------------------------- property types

def test_property_type_seeded_and_usable(client, auth_headers):
    seeded = client.get("/api/v1/properties/types", headers=auth_headers).get_json()["data"]
    codes = {t["code"] for t in seeded}
    assert {"full_building", "villa", "store", "compound"} <= codes
    assert all(t["is_active"] for t in seeded)


def test_property_type_create_deactivate_and_reject_unknown(client, auth_headers):
    created = client.post("/api/v1/properties/types", headers=auth_headers,
                          json={"name": "Warehouse"})
    assert created.status_code == 201, created.get_data(as_text=True)
    ptype = created.get_json()["data"]
    assert ptype["code"] == "WAREHOUSE"

    dup = client.post("/api/v1/properties/types", headers=auth_headers,
                      json={"name": "warehouse"})
    assert dup.status_code == 409

    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Cold Store", "property_type": "WAREHOUSE"})
    assert prop.status_code == 201, prop.get_data(as_text=True)

    off = client.patch(f"/api/v1/properties/types/{ptype['id']}", headers=auth_headers,
                       json={"is_active": False})
    assert off.status_code == 200
    assert off.get_json()["data"]["is_active"] is False

    active_only = client.get("/api/v1/properties/types?active_only=1",
                             headers=auth_headers).get_json()["data"]
    assert "WAREHOUSE" not in {t["code"] for t in active_only}

    blocked = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Another Cold Store", "property_type": "WAREHOUSE"})
    assert blocked.status_code == 400


def test_deactivated_property_type_stays_valid_on_its_own_property(client, auth_headers):
    """Deactivating a type must not strand the properties that already
    carry it — an edit that doesn't touch the type should keep saving."""
    created = client.post("/api/v1/properties/types", headers=auth_headers,
                          json={"name": "Legacy Type"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Old School", "property_type": created["code"]}).get_json()["data"]

    client.patch(f"/api/v1/properties/types/{created['id']}", headers=auth_headers,
                json={"is_active": False})

    unchanged = client.put(f"/api/v1/properties/{prop['id']}", headers=auth_headers,
                           json={"remarks": "still fine", "property_type": created["code"]})
    assert unchanged.status_code == 200, unchanged.get_data(as_text=True)

    switch_away = client.put(f"/api/v1/properties/{prop['id']}", headers=auth_headers,
                             json={"property_type": "villa"})
    assert switch_away.status_code == 200

    switch_back = client.put(f"/api/v1/properties/{prop['id']}", headers=auth_headers,
                             json={"property_type": created["code"]})
    assert switch_back.status_code == 400
