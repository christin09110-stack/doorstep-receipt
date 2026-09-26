#!/usr/bin/env python3
"""Generate HMAC-signed Ring webhook fixtures for the demo replay path.

Run: python fixtures/generate_fixtures.py

Writes fixtures/signed_webhooks/*.json, each `{"payload": {...}, "signature":
"<hex hmac>"}`, signed with the same RING_WEBHOOK_SECRET the app checks by
default ("demo-webhook-secret", overridable via env var). This mirrors the real
inbound shape: a JSON:API-style payload with meta.request_id, meta.time,
data.type, data.attributes.sub_type, data.attributes.timestamp, and a
relationships.devices.data.id link, matching PLATFORM-FACTS.md's documented
webhook event shape.

Six events across three days, chosen so every branch of reconcile.py has a
fixture behind it rather than only the happy one:

  01, 02  A doorbell press at 14:11 on 20 September and human motion at 14:13.
          A "delivered at 14:11" claim against these is CONSISTENT.
  03      A vehicle passing at 09:05 on 20 September, with no person and no
          press. A "delivered at 09:03" claim against this is NOT CONSISTENT,
          and the vehicle still appears in the event log: hiding it would be
          editing the record, and a reader can see for themselves that a van
          going past is not somebody at a door.
  04      Human motion at 14:20 on 18 September, against which an "attempted
          delivery at 14:11" claim is INDETERMINATE. Somebody was there. Which
          somebody, and what they did, is not something a camera can say.
  05, 06  A press and human motion at 11:02 on 22 September, for a second
          CONSISTENT claim so the claim file and its search have more than one
          row in them.

The quiet case needs no fixture at all: a claim whose window contains none of
these events is the empty set, and the pack renders it as an empty set.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doorstep_receipt.webhook import sign_payload  # noqa: E402

SECRET = os.environ.get("RING_WEBHOOK_SECRET", "demo-webhook-secret")
OUT_DIR = Path(__file__).resolve().parent / "signed_webhooks"

FIXTURES = [
    {
        "name": "01-button-press-1411",
        "payload": {
            "meta": {"version": "1.0", "time": "2026-09-20T14:11:03Z", "request_id": "req-fixture-001"},
            "data": {
                "id": "evt-fixture-001",
                "type": "ding",
                "attributes": {"source": "front-door", "source_type": "doorbell", "timestamp": "2026-09-20T14:11:03Z"},
                "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
            },
        },
    },
    {
        "name": "02-human-motion-1413",
        "payload": {
            "meta": {"version": "1.0", "time": "2026-09-20T14:13:40Z", "request_id": "req-fixture-002"},
            "data": {
                "id": "evt-fixture-002",
                "type": "motion",
                "attributes": {
                    "source": "front-door",
                    "source_type": "camera",
                    "sub_type": "human",
                    "timestamp": "2026-09-20T14:13:40Z",
                    "confidence": 0.94,
                },
                "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
            },
        },
    },
    {
        "name": "03-vehicle-motion-0905",
        "payload": {
            "meta": {"version": "1.0", "time": "2026-09-20T09:05:12Z", "request_id": "req-fixture-003"},
            "data": {
                "id": "evt-fixture-003",
                "type": "motion",
                "attributes": {
                    "source": "front-door",
                    "source_type": "camera",
                    "sub_type": "vehicle",
                    "timestamp": "2026-09-20T09:05:12Z",
                    "confidence": 0.88,
                },
                "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
            },
        },
    },
    {
        "name": "04-human-motion-1420-sept18",
        "payload": {
            "meta": {"version": "1.0", "time": "2026-09-18T14:20:07Z", "request_id": "req-fixture-004"},
            "data": {
                "id": "evt-fixture-004",
                "type": "motion",
                "attributes": {
                    "source": "front-door",
                    "source_type": "camera",
                    "sub_type": "human",
                    "timestamp": "2026-09-18T14:20:07Z",
                    "confidence": 0.91,
                },
                "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
            },
        },
    },
    {
        "name": "05-button-press-1102-sept22",
        "payload": {
            "meta": {"version": "1.0", "time": "2026-09-22T11:02:44Z", "request_id": "req-fixture-005"},
            "data": {
                "id": "evt-fixture-005",
                "type": "ding",
                "attributes": {"source": "front-door", "source_type": "doorbell", "timestamp": "2026-09-22T11:02:44Z"},
                "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
            },
        },
    },
    {
        "name": "06-human-motion-1103-sept22",
        "payload": {
            "meta": {"version": "1.0", "time": "2026-09-22T11:03:20Z", "request_id": "req-fixture-006"},
            "data": {
                "id": "evt-fixture-006",
                "type": "motion",
                "attributes": {
                    "source": "front-door",
                    "source_type": "camera",
                    "sub_type": "human",
                    "timestamp": "2026-09-22T11:03:20Z",
                    "confidence": 0.96,
                },
                "relationships": {"devices": {"data": {"id": "ava1.ring.device.FRONTDOOR"}}},
            },
        },
    },
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fixture in FIXTURES:
        raw_body = json.dumps(fixture["payload"]).encode("utf-8")
        signature = sign_payload(raw_body, SECRET)
        out_path = OUT_DIR / f"{fixture['name']}.json"
        out_path.write_text(json.dumps({"payload": fixture["payload"], "signature": signature}, indent=2))
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
