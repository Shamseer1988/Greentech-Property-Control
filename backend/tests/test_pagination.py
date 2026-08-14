"""app/utils/pagination.py, and its wiring into the list routes that
either had no cap before (audit) or a hardcoded, page-2-unreachable
cap (expenses, agreements)."""


def _make_landlords(client, auth_headers, n):
    for i in range(n):
        resp = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": f"Page Landlord {i:03d}"})
        assert resp.status_code == 201, resp.get_data(as_text=True)


def test_default_page_and_size(client, auth_headers):
    _make_landlords(client, auth_headers, 5)
    resp = client.get("/api/v1/landlords", headers=auth_headers)
    assert resp.status_code == 200
    meta = resp.get_json()["meta"]
    assert meta["page"] == 1
    assert meta["per_page"] == 25
    assert meta["total_count"] == 5
    assert meta["total_pages"] == 1


def test_second_page_returns_the_remainder(client, auth_headers):
    _make_landlords(client, auth_headers, 7)
    first = client.get("/api/v1/landlords?per_page=5&page=1", headers=auth_headers).get_json()
    second = client.get("/api/v1/landlords?per_page=5&page=2", headers=auth_headers).get_json()

    assert len(first["data"]) == 5
    assert len(second["data"]) == 2
    assert first["meta"]["total_count"] == 7
    assert first["meta"]["total_pages"] == 2

    first_ids = {r["id"] for r in first["data"]}
    second_ids = {r["id"] for r in second["data"]}
    assert first_ids.isdisjoint(second_ids)


def test_per_page_is_clamped_to_the_route_max(client, auth_headers):
    _make_landlords(client, auth_headers, 3)
    resp = client.get("/api/v1/landlords?per_page=10000", headers=auth_headers)
    # landlords.py uses the default paginate() cap (max_per_page=200).
    assert resp.get_json()["meta"]["per_page"] == 200


def test_out_of_range_page_returns_an_empty_page_not_an_error(client, auth_headers):
    _make_landlords(client, auth_headers, 2)
    resp = client.get("/api/v1/landlords?page=99", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] == []
    assert resp.get_json()["meta"]["total_count"] == 2


def test_audit_log_is_no_longer_unbounded(client, auth_headers):
    # Generate more than one page's worth of audit activity, then confirm
    # a second page is reachable — before this, /audit had no page param
    # at all and silently capped at 100-500 rows with no way to see more.
    _make_landlords(client, auth_headers, 3)
    resp = client.get("/api/v1/audit?per_page=1&page=1", headers=auth_headers)
    assert resp.status_code == 200
    meta = resp.get_json()["meta"]
    assert meta["total_count"] >= 3
    assert meta["total_pages"] >= 3
    assert len(resp.get_json()["data"]) == 1


def test_expenses_money_total_covers_the_full_filtered_set_not_just_the_page(client, auth_headers):
    category = client.post("/api/v1/expenses/categories", headers=auth_headers,
                           json={"name": "Pagination Test Cat", "kind": "indirect"}).get_json()["data"]
    for i in range(3):
        resp = client.post("/api/v1/expenses", headers=auth_headers, json={
            "category_id": category["id"], "period_month": "2026-01-01", "amount": 1000,
        })
        assert resp.status_code == 201, resp.get_data(as_text=True)

    resp = client.get("/api/v1/expenses?month=2026-01-01&per_page=1", headers=auth_headers)
    assert resp.status_code == 200
    meta = resp.get_json()["meta"]
    # One row on this page, but the money total must still reflect all 3.
    assert len(resp.get_json()["data"]) == 1
    assert meta["total"] == 3000.0
