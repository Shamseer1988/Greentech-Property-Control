"""Client master — the tenants GreenTech lets units to."""
from datetime import date, timedelta


def test_client_crud(client, auth_headers):
    resp = client.post("/api/v1/clients", headers=auth_headers, json={
        "name": "IMDAAD FACILITY SERVICES MANAGEMENT",
        "name_ar": "امداد لإدارة المرافق",
        "client_type": "company",
        "contact_person": "Rahim",
        "mobile": "+97455512345",
        "qid_cr_number": "CR-118822",
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    c = resp.get_json()["data"]
    assert c["code"].startswith("CL-")
    assert c["name_ar"] == "امداد لإدارة المرافق"
    assert c["status"] == "active"

    listed = client.get("/api/v1/clients", headers=auth_headers).get_json()
    assert listed["meta"]["count"] == 1

    upd = client.put(f"/api/v1/clients/{c['id']}", headers=auth_headers,
                     json={"contact_person": "Kareem", "status": "inactive"})
    assert upd.status_code == 200
    assert upd.get_json()["data"]["contact_person"] == "Kareem"
    assert upd.get_json()["data"]["status"] == "inactive"

    one = client.get(f"/api/v1/clients/{c['id']}", headers=auth_headers)
    assert one.status_code == 200
    assert one.get_json()["data"]["code"] == c["code"]


def test_client_codes_are_sequential(client, auth_headers):
    first = client.post("/api/v1/clients", headers=auth_headers,
                        json={"name": "A Co"}).get_json()["data"]
    second = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "B Co"}).get_json()["data"]
    assert first["code"] == "CL-0001"
    assert second["code"] == "CL-0002"


def test_client_rejects_bad_enum_values(client, auth_headers):
    bad_type = client.post("/api/v1/clients", headers=auth_headers,
                           json={"name": "X", "client_type": "alien"})
    assert bad_type.status_code == 422

    bad_status = client.post("/api/v1/clients", headers=auth_headers,
                             json={"name": "X", "status": "exploded"})
    assert bad_status.status_code == 422


def test_client_search_by_arabic_name_and_cr(client, auth_headers):
    client.post("/api/v1/clients", headers=auth_headers, json={
        "name": "AL ANBER PAINT", "name_ar": "العنبر للدهانات",
        "qid_cr_number": "CR-9090",
    })
    client.post("/api/v1/clients", headers=auth_headers, json={"name": "Other Co"})

    by_ar = client.get("/api/v1/clients?q=العنبر", headers=auth_headers).get_json()
    assert by_ar["meta"]["count"] == 1
    assert by_ar["data"][0]["name"] == "AL ANBER PAINT"

    by_cr = client.get("/api/v1/clients?q=cr-9090", headers=auth_headers).get_json()
    assert by_cr["meta"]["count"] == 1


def test_client_status_filter(client, auth_headers):
    a = client.post("/api/v1/clients", headers=auth_headers,
                    json={"name": "Active Co"}).get_json()["data"]
    client.post("/api/v1/clients", headers=auth_headers,
                json={"name": "Gone Co", "status": "blacklisted"})
    rows = client.get("/api/v1/clients?status=active", headers=auth_headers).get_json()
    assert [r["id"] for r in rows["data"]] == [a["id"]]


def test_client_appears_in_global_search(client, auth_headers):
    c = client.post("/api/v1/clients", headers=auth_headers,
                    json={"name": "Searchable Client", "qid_cr_number": "CR-5150"}).get_json()["data"]
    r = client.get("/api/v1/search?q=searchable", headers=auth_headers)
    assert r.status_code == 200
    assert any(x["id"] == c["id"] for x in r.get_json()["data"]["clients"])


def test_client_requires_permission(client):
    assert client.get("/api/v1/clients").status_code == 401


def test_client_write_is_audited(client, auth_headers):
    c = client.post("/api/v1/clients", headers=auth_headers,
                    json={"name": "Audited Co"}).get_json()["data"]
    client.put(f"/api/v1/clients/{c['id']}", headers=auth_headers,
               json={"mobile": "+97450000000"})

    rows = client.get("/api/v1/audit?module=client", headers=auth_headers).get_json()["data"]
    actions = {r["action"] for r in rows}
    assert {"create", "update"} <= actions


# ---------------------------------------------------------- landlord AR

def test_landlord_accepts_arabic_name_and_doc_expiry(client, auth_headers):
    expiry = (date.today() + timedelta(days=40)).isoformat()
    resp = client.post("/api/v1/landlords", headers=auth_headers, json={
        "name": "SAOUD SAAD M A AL KUWARI",
        "name_ar": "سعود سعد الكوارى",
        "qid_cr_number": "CR-36-2023",
        "qid_cr_expiry_date": expiry,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    ll = resp.get_json()["data"]
    assert ll["name_ar"] == "سعود سعد الكوارى"
    assert ll["qid_cr_expiry_date"] == expiry

    found = client.get("/api/v1/landlords?q=سعود", headers=auth_headers).get_json()
    assert found["meta"]["count"] == 1
