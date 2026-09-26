import json

import pytest

from doorstep_receipt.webhook import (
    DuplicateWebhook,
    InvalidSignature,
    SeenRequestStore,
    parse_webhook,
    sign_payload,
    verify_signature,
)

SECRET = "test-secret"

PAYLOAD = {
    "meta": {"version": "1.0", "time": "2026-09-20T14:11:03Z", "request_id": "req-1"},
    "data": {
        "id": "evt-1",
        "type": "ding",
        "attributes": {"source": "front-door", "source_type": "doorbell", "timestamp": "2026-09-20T14:11:03Z"},
        "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
    },
}


def _raw_body(payload=PAYLOAD) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_verify_signature_accepts_correctly_signed_body():
    raw = _raw_body()
    sig = sign_payload(raw, SECRET)
    verify_signature(raw, sig, SECRET)  # must not raise


def test_verify_signature_rejects_tampered_body():
    raw = _raw_body()
    sig = sign_payload(raw, SECRET)
    tampered = _raw_body({**PAYLOAD, "data": {**PAYLOAD["data"], "id": "evt-tampered"}})
    with pytest.raises(InvalidSignature):
        verify_signature(tampered, sig, SECRET)


def test_verify_signature_rejects_wrong_secret():
    raw = _raw_body()
    sig = sign_payload(raw, "a-different-secret")
    with pytest.raises(InvalidSignature):
        verify_signature(raw, sig, SECRET)


def test_verify_signature_rejects_missing_header():
    raw = _raw_body()
    with pytest.raises(InvalidSignature):
        verify_signature(raw, "", SECRET)


def test_parse_webhook_extracts_fields():
    parsed = parse_webhook(PAYLOAD)
    assert parsed.request_id == "req-1"
    assert parsed.event_id == "evt-1"
    assert parsed.event_type == "ding"
    assert parsed.device_id == "ava1.ring.device.FRONTDOOR"
    assert parsed.timestamp == "2026-09-20T14:11:03Z"


def test_parse_webhook_motion_subtype():
    motion_payload = {
        "meta": {"version": "1.0", "time": "t", "request_id": "req-2"},
        "data": {
            "id": "evt-2",
            "type": "motion",
            "attributes": {"source": "front-door", "source_type": "camera", "sub_type": "human", "timestamp": "t"},
        },
    }
    parsed = parse_webhook(motion_payload)
    assert parsed.event_type == "motion"
    assert parsed.sub_type == "human"
    assert parsed.device_id is None  # no relationships block in this payload


def test_seen_request_store_flags_duplicates():
    store = SeenRequestStore()
    store.check_and_record("req-1")
    with pytest.raises(DuplicateWebhook):
        store.check_and_record("req-1")


def test_seen_request_store_allows_distinct_ids():
    store = SeenRequestStore()
    store.check_and_record("req-1")
    store.check_and_record("req-2")  # must not raise


def test_a_delivery_with_no_request_id_is_refused_rather_than_waved_through():
    """The old behaviour was to skip the check, which meant a correctly signed
    delivery carrying no `meta.request_id` replayed forever, appending an event
    each time. A signature proves the body was not altered; it says nothing
    about whether this is the first time the body arrived. README.md claims
    idempotency on `meta.request_id`, and that claim was only true of
    deliveries that carried one."""
    store = SeenRequestStore()

    with pytest.raises(DuplicateWebhook):
        store.check_and_record("")
