import json

import pytest
from fastapi.testclient import TestClient

from doorstep_receipt import app as app_module
from doorstep_receipt.webhook import sign_payload

SECRET = "demo-webhook-secret"  # matches app.py's default when RING_WEBHOOK_SECRET is unset


@pytest.fixture()
def client():
    # Fresh store per test so tests don't leak events/claims into each other.
    app_module.store = app_module.DemoStore()
    app_module.seen_requests = app_module.SeenRequestStore()
    return TestClient(app_module.app)


def _signed_webhook_payload(request_id="req-a", event_type="ding", timestamp="2026-09-20T14:11:00Z"):
    payload = {
        "meta": {"version": "1.0", "time": timestamp, "request_id": request_id},
        "data": {
            "id": f"evt-{request_id}",
            "type": event_type,
            "attributes": {"source": "front-door", "source_type": "doorbell", "timestamp": timestamp},
            "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    return raw, sign_payload(raw, SECRET)


def test_webhook_rejects_bad_signature(client):
    raw, _ = _signed_webhook_payload()
    resp = client.post("/webhooks/ring", content=raw, headers={"X-Signature": "not-a-real-signature"})
    assert resp.status_code == 401


def test_webhook_accepts_correctly_signed_payload(client):
    raw, sig = _signed_webhook_payload()
    resp = client.post("/webhooks/ring", content=raw, headers={"X-Signature": sig})
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"


def test_webhook_deduplicates_on_request_id(client):
    raw, sig = _signed_webhook_payload(request_id="req-dup")
    first = client.post("/webhooks/ring", content=raw, headers={"X-Signature": sig})
    second = client.post("/webhooks/ring", content=raw, headers={"X-Signature": sig})
    assert first.json()["status"] == "stored"
    assert second.json()["status"] == "already_processed"


def test_demo_replay_ingests_fixtures(client):
    resp = client.post("/demo/replay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_events"] == 6  # six fixtures committed in fixtures/signed_webhooks/


def test_full_flow_consistent_verdict(client):
    raw, sig = _signed_webhook_payload(request_id="req-flow", timestamp="2026-09-20T14:11:00Z")
    client.post("/webhooks/ring", content=raw, headers={"X-Signature": sig})

    create = client.post(
        "/claims",
        json={
            "tracking_number": "1Z999AA10123456784",
            "carrier_name": "UPS",
            "status": "delivered",
            "claimed_at": "2026-09-20T14:11:00Z",
        },
    )
    assert create.status_code == 201
    claim_id = create.json()["claim_id"]
    assert create.json()["verdict"] == "consistent_with_camera"

    evidence = client.get(f"/claims/{claim_id}/evidence")
    assert evidence.status_code == 200
    assert "Consistent with camera" in evidence.text
    assert "1Z999AA10123456784" in evidence.text


def test_full_flow_not_consistent_verdict_with_no_events(client):
    # The replay loads the camera status samples as well as the door events.
    # Without them this claim could only be indeterminate, because a window this
    # app cannot show was being recorded is not a window it will report an
    # absence over. See coverage.py.
    client.post("/demo/replay")
    create = client.post(
        "/claims",
        json={
            "tracking_number": "9999",
            "carrier_name": "Royal Mail",
            "status": "delivered",
            "claimed_at": "2026-09-20T09:00:00Z",
            "window_minutes": 20,
        },
    )
    claim_id = create.json()["claim_id"]
    assert create.json()["verdict"] == "not_consistent_with_camera"

    payload = client.get(f"/claims/{claim_id}/evidence.json").json()
    assert payload["verdict"] == "not_consistent_with_camera"
    # The vehicle that passed at 09:05 is in the log and is marked as not an
    # arrival. Leaving it out would be editing the record; a reader can see for
    # themselves that a van going past is not somebody at a door.
    assert [e["sub_type"] for e in payload["events"]] == ["vehicle"]
    assert payload["events"][0]["counts_as_arrival"] is False
    assert payload["coverage"]["established"] is True


def test_uncovered_window_cannot_reach_not_consistent(client):
    """The fixture camera stops answering between 10:00 and 11:15 on 20 September.

    A claim inside that hour has no door events, which in a covered window would
    be "not consistent with camera". It must not be, because nothing was
    watching, and the pack has to say which of the two it is."""
    client.post("/demo/replay")
    create = client.post(
        "/claims",
        json={
            "tracking_number": "1Z999AA10123456789",
            "carrier_name": "UPS",
            "status": "delivered",
            "claimed_at": "2026-09-20T10:30:00Z",
            "window_minutes": 20,
        },
    )
    assert create.json()["verdict"] == "indeterminate"
    payload = client.get(f"/claims/{create.json()['claim_id']}/evidence.json").json()
    assert payload["events"] == []
    assert payload["coverage"]["gaps"], "an uncovered window must report its gaps"
    assert "offline" in payload["coverage"]["gaps"][0]["reason"].lower()


def test_claim_requires_tracking_number(client):
    resp = client.post(
        "/claims",
        json={"tracking_number": "", "status": "delivered", "claimed_at": "2026-09-20T09:00:00Z"},
    )
    assert resp.status_code == 400


def test_claim_rejects_unknown_status(client):
    resp = client.post(
        "/claims",
        json={"tracking_number": "123", "status": "teleported", "claimed_at": "2026-09-20T09:00:00Z"},
    )
    assert resp.status_code == 400


def test_evidence_404_for_unknown_claim(client):
    resp = client.get("/claims/does-not-exist/evidence")
    assert resp.status_code == 404


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
