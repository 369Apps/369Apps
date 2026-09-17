from fastapi.testclient import TestClient

from app.main import app
from app.store import STORE


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_auto_run_availability():
    r = client.post(
        "/intake",
        json={
            "channel": "whatsapp",
            "channel_user_id": "wa:+15551234567",
            "text": "Am I available Tuesday afternoon?",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["matched_op"] == "calendar.check_availability"
    assert data["state"] == "completed"
    assert data["consequence"] == "A"


def test_approval_required_for_booking():
    r = client.post(
        "/intake",
        json={
            "channel": "whatsapp",
            "channel_user_id": "wa:+15551234567",
            "text": "Book a meeting tomorrow at 2pm titled Investor intro",
            "idempotency_key": "test-book-1",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["matched_op"] == "calendar.create_event"
    assert data["state"] == "awaiting_approval"
    assert data["approval_url"]
    assert "token=" in data["approval_url"]

    approval_id = data["approval_url"].split("/approve/")[1].split("?")[0]
    token = data["approval_url"].split("token=")[1]
    r2 = client.post(
        f"/approve/{approval_id}",
        json={"token": token, "decision": "approved"},
    )
    assert r2.status_code == 200
    assert r2.json()["state"] == "completed"

    audit = client.get(f"/jobs/{data['job_id']}/audit").json()
    actions = [e["action"] for e in audit["events"]]
    assert "issue" in actions
    assert "approval_decision" in actions
    assert "execute" in actions


def test_out_of_catalog():
    r = client.post(
        "/intake",
        json={
            "channel": "whatsapp",
            "channel_user_id": "wa:+15551234567",
            "text": "Write me a poem about quantum foam",
            "idempotency_key": "test-ooc-1",
        },
    )
    assert r.status_code == 200
    assert r.json()["state"] == "out_of_catalog"


def test_unknown_identity():
    r = client.post(
        "/intake",
        json={
            "channel": "whatsapp",
            "channel_user_id": "wa:+19999999999",
            "text": "Book a meeting tomorrow at 2pm titled Hello",
            "idempotency_key": "test-unk-1",
        },
    )
    assert r.status_code == 200
    assert r.json()["state"] == "escalated"


def test_catalog_endpoint():
    r = client.get("/catalog")
    assert r.status_code == 200
    assert len(r.json()["ops"]) >= 5
    # sanity: store still has demo tenant
    assert STORE.get_tenant("client_demo") is not None
