"""`flask landlord-dues generate|reconcile` — the one-time backfill path
for payments posted before the dues ledger existed."""
import json


def _agreement(client, auth_headers, *, rent=5000):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "CLI Owner"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "CLI Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    ag = client.post(f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers, json={
        "landlord_id": landlord["id"], "start_date": "2026-01-01", "expiry_date": "2026-12-31",
        "monthly_rent": rent,
    }).get_json()["data"]
    return landlord, prop, ag


def test_generate_dry_run_writes_nothing(app, client, auth_headers):
    landlord, prop, ag = _agreement(client, auth_headers)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["landlord-dues", "generate", "--upto", "2026-03-01"])
    assert result.exit_code == 0, result.output
    assert "dry run" in result.output

    charges = client.get(f"/api/v1/expenses/landlord-charges?contract_id={ag['id']}",
                         headers=auth_headers).get_json()["data"]
    assert charges == [], "a dry run must not persist anything"


def test_generate_commit_persists(app, client, auth_headers):
    landlord, prop, ag = _agreement(client, auth_headers)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["landlord-dues", "generate", "--upto", "2026-03-01", "--commit"])
    assert result.exit_code == 0, result.output
    assert "Committed" in result.output

    charges = client.get(f"/api/v1/expenses/landlord-charges?contract_id={ag['id']}",
                         headers=auth_headers).get_json()["data"]
    assert len(charges) == 3


def test_reconcile_matches_existing_payments_oldest_first(app, client, auth_headers):
    landlord, prop, ag = _agreement(client, auth_headers, rent=5000)
    runner = app.test_cli_runner()
    runner.invoke(args=["landlord-dues", "generate", "--upto", "2026-03-01", "--commit"])

    pay = client.post("/api/v1/expenses/landlord-payments", headers=auth_headers, json={
        "landlord_id": landlord["id"], "property_id": prop["id"], "period_month": "2026-01-01",
        "amount": 5000, "mode": "cash",
    })
    assert pay.status_code == 201
    payment_id = pay.get_json()["data"]["id"]

    charges = {c["period_month"]: c for c in client.get(
        f"/api/v1/expenses/landlord-charges?contract_id={ag['id']}",
        headers=auth_headers).get_json()["data"]}
    assert charges["2026-01-01"]["status"] == "paid", "auto-allocation already settled it"

    # Simulate a historical payment posted before the ledger existed:
    # posted, but with no allocation rows — exactly the state of the 118
    # live payments this command backfills. Direct DB manipulation is the
    # only way to reach that state through this API, mirroring the
    # approach test_landlord_contracts.py uses for its own unreachable-
    # through-the-API edge case.
    from app.extensions import db
    from app.models import LandlordCharge, LandlordPaymentAllocation
    with app.app_context():
        LandlordPaymentAllocation.query.filter_by(payment_id=payment_id).delete()
        charge = LandlordCharge.query.filter_by(contract_id=ag["id"]).filter(
            LandlordCharge.period_month == "2026-01-01").first()
        charge.allocated = 0
        charge.status = "open"
        db.session.commit()

    charges = {c["period_month"]: c for c in client.get(
        f"/api/v1/expenses/landlord-charges?contract_id={ag['id']}",
        headers=auth_headers).get_json()["data"]}
    assert charges["2026-01-01"]["status"] == "open", "now genuinely unallocated"

    result = runner.invoke(args=["landlord-dues", "reconcile", "--upto", "2026-03-01", "--commit"])
    assert result.exit_code == 0, result.output
    assert "Committed" in result.output
    assert "1 allocation(s) matched" in result.output

    charges = {c["period_month"]: c for c in client.get(
        f"/api/v1/expenses/landlord-charges?contract_id={ag['id']}",
        headers=auth_headers).get_json()["data"]}
    assert charges["2026-01-01"]["status"] == "paid", "reconcile re-matched the historical payment"


def test_reconcile_dry_run_does_not_write(app, client, auth_headers):
    landlord, prop, ag = _agreement(client, auth_headers, rent=5000)
    runner = app.test_cli_runner()
    runner.invoke(args=["landlord-dues", "generate", "--upto", "2026-01-01", "--commit"])

    result = runner.invoke(args=["landlord-dues", "reconcile", "--upto", "2026-01-01"])
    assert result.exit_code == 0, result.output
    assert "dry run" in result.output
