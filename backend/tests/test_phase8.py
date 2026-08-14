"""Phase 8 — modern feature tests.

Covers:
  * notifications feed + mark-read + unread-count (8b)
  * audit log diff payload on update rows (8d)
  * SSE auth gating and publish round-trip via in-process queue (8a)
"""
import json
import threading
import time


# ---------------------------------------------------------------------------
# 8b — notifications
# ---------------------------------------------------------------------------
def test_notifications_feed_empty_initially(client, auth_headers):
    r = client.get("/api/v1/notifications")
    assert r.status_code == 200
    body = r.get_json()
    assert body["data"] == []
    assert body["meta"]["unread"] == 0


def test_notifications_create_and_list(client, app, auth_headers):
    from app.services import notifications as notif_service
    from app.extensions import db
    from app.models import User

    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        notif_service.create_for(
            user_id=admin.id, type="test", title="Hello",
            body="Just a test.", link="/dashboard",
        )
        db.session.commit()

    feed = client.get("/api/v1/notifications").get_json()
    assert feed["meta"]["unread"] == 1
    assert feed["data"][0]["title"] == "Hello"
    assert feed["data"][0]["is_read"] is False

    count = client.get("/api/v1/notifications/unread-count").get_json()
    assert count["data"]["unread"] == 1


def test_notification_mark_read(client, app, auth_headers):
    from app.services import notifications as notif_service
    from app.extensions import db
    from app.models import User

    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        n = notif_service.create_for(user_id=admin.id, type="t", title="X")
        db.session.commit()
        nid = n.id

    r = client.post(f"/api/v1/notifications/{nid}/read", headers=auth_headers)
    assert r.status_code == 200
    assert r.get_json()["data"]["is_read"] is True

    feed = client.get("/api/v1/notifications").get_json()
    assert feed["meta"]["unread"] == 0


def test_notification_mark_all_read(client, app, auth_headers):
    from app.services import notifications as notif_service
    from app.extensions import db
    from app.models import User

    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        for i in range(3):
            notif_service.create_for(user_id=admin.id, type="t", title=f"#{i}")
        db.session.commit()

    r = client.post("/api/v1/notifications/read-all", headers=auth_headers)
    assert r.status_code == 200
    assert r.get_json()["data"]["marked"] == 3
    assert client.get("/api/v1/notifications/unread-count").get_json()["data"]["unread"] == 0


def test_notification_404_for_other_users_row(client, app, auth_headers):
    from app.services import notifications as notif_service
    from app.extensions import db
    from app.models import User, Role

    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        # Create another user and drop a notification on THEM
        other_role = Role.query.first()
        other = User(username="other", email="other@x.com", full_name="O",
                     is_active=True, is_super_user=False)
        other.set_password("Password123")
        other.roles.append(other_role)
        db.session.add(other)
        db.session.flush()
        n = notif_service.create_for(user_id=other.id, type="t", title="Not yours")
        db.session.commit()
        nid = n.id
        assert other.id != admin.id

    r = client.post(f"/api/v1/notifications/{nid}/read", headers=auth_headers)
    assert r.status_code == 404


def test_notifications_require_auth(client):
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.get("/api/v1/notifications/unread-count").status_code == 401
    assert client.post("/api/v1/notifications/1/read").status_code == 401


# ---------------------------------------------------------------------------
# 8d — audit diff
# ---------------------------------------------------------------------------
def test_audit_diff_on_update_row(client, auth_headers):
    """Updating a landlord writes an audit row with old/new value;
    the audit feed renders the precomputed diff."""
    ll = client.post("/api/v1/landlords", headers=auth_headers,
                     json={"name": "Diff Subject", "contact_person": "Cook"}).get_json()["data"]
    # Change contact_person + add mobile
    client.put(f"/api/v1/landlords/{ll['id']}", headers=auth_headers,
               json={"contact_person": "Head cook", "mobile": "5550000"})

    rows = client.get("/api/v1/audit?action=update&module=landlord",
                      headers=auth_headers).get_json()["data"]
    update = next(r for r in rows if r["entity_id"] == str(ll["id"]))
    diff = update["diff"]
    assert diff is not None
    fields = {d["field"]: d for d in diff}
    assert fields["contact_person"]["before"] == "Cook"
    assert fields["contact_person"]["after"] == "Head cook"
    assert "mobile" in fields
    assert fields["mobile"]["before"] in (None, "")
    assert fields["mobile"]["after"] == "5550000"
    # Bookkeeping fields filtered out of the diff.
    assert "updated_at" not in fields
    assert "updated_by" not in fields


def test_audit_no_diff_on_create_row(client, auth_headers):
    client.post("/api/v1/landlords", headers=auth_headers, json={"name": "Created"})
    rows = client.get("/api/v1/audit?action=create", headers=auth_headers).get_json()["data"]
    # Create rows shouldn't have a diff field.
    for r in rows[:5]:
        assert "diff" not in r or r["diff"] is None


# ---------------------------------------------------------------------------
# 8a — SSE
# ---------------------------------------------------------------------------
def test_sse_requires_auth(client):
    # No login cookie → 401.
    r = client.get("/api/v1/events/stream")
    assert r.status_code == 401


def test_sse_rejects_unknown_channel(client, auth_headers):
    r = client.get("/api/v1/events/stream?channel=hacker")
    assert r.status_code == 400


def test_sse_publish_routes_through_in_process_queue(app):
    """In tests REDIS_URL is unset, so events.publish broadcasts via the
    in-process queue. Subscribe in a thread, publish from another, and
    confirm the payload reaches the subscriber. This is the unit-level
    equivalent of the full GET /events/stream round-trip without dealing
    with Flask's streaming response in the test client."""
    from app.services import events as event_service

    received: list[str] = []

    def consume():
        # subscribe() yields forever; break after one real payload.
        for body in event_service.subscribe("occupancy"):
            if body:  # skip keepalive empties
                received.append(body)
                return

    with app.app_context():
        t = threading.Thread(target=lambda: app.test_request_context().__enter__() and consume(), daemon=True)
        t.start()
        # Give the subscriber a beat to register on the channel.
        time.sleep(0.1)
        event_service.publish("occupancy", {"hello": "world"})
        t.join(timeout=2.0)

    assert received, "subscriber never received a payload"
    payload = json.loads(received[0])
    assert payload["hello"] == "world"
