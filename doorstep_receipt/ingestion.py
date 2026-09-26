"""Wires webhook verification, parsing and storage into one call.

Split out of app.py so the route handlers stay thin. This is the one function
both `/webhooks/ring` (a real webhook) and `/demo/replay` (the fixture replay)
call, so the demo path exercises the identical verify-and-store code a real
Ring webhook would hit, never a shortcut around it.
"""

from __future__ import annotations

import json

from .ring_events import RingEvent, parse_timestamp
from .store import DemoStore
from .webhook import SeenRequestStore, parse_webhook, verify_signature


def ingest_webhook_body(
    raw_body: bytes,
    signature: str,
    secret: str,
    store: DemoStore,
    seen_requests: SeenRequestStore,
) -> RingEvent:
    """Verify, parse, deduplicate and store one Ring webhook body.

    Raises InvalidSignature (bad/missing X-Signature) or DuplicateWebhook
    (meta.request_id already seen) from webhook.py; callers translate those
    into the right HTTP response.
    """
    verify_signature(raw_body, signature, secret)
    payload = json.loads(raw_body)
    parsed = parse_webhook(payload)
    seen_requests.check_and_record(parsed.request_id)
    event = RingEvent(
        event_id=parsed.event_id,
        event_type=parsed.event_type,
        sub_type=parsed.sub_type,
        timestamp=parse_timestamp(parsed.timestamp),
        device_id=parsed.device_id,
        raw=parsed.raw,
    )
    store.add_event(event)
    return event
