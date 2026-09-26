"""Ring webhook signature verification and normalization.

ASSUMPTION, stated plainly: Ring's own documentation says only "HMAC-SHA256
signature in X-Signature, must return 2xx within 5 seconds, deduplicate on
meta.request_id", but does not publish the exact canonicalisation (what bytes get
hashed) or a worked example. This module hashes the raw request body with
HMAC-SHA256 and compares a hex digest against X-Signature, which is the
conventional shape for this kind of header (GitHub, Stripe use the same pattern)
and the only interpretation the documented sentence supports. If Ring's real
recipe differs (a timestamp folded into the signed string, a different
encoding), this function is the one place that needs to change.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any


class InvalidSignature(Exception):
    """Raised when a webhook's X-Signature does not match the computed HMAC."""


class DuplicateWebhook(Exception):
    """Raised when a webhook's meta.request_id has already been processed."""


def verify_signature(raw_body: bytes, signature_header: str, secret: str) -> None:
    """Verify an inbound Ring webhook's HMAC-SHA256 signature.

    Raises InvalidSignature if the signature does not match. Uses a
    constant-time comparison so this check cannot be used as a timing oracle.
    """
    if not signature_header:
        raise InvalidSignature("Missing X-Signature header")
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise InvalidSignature("X-Signature does not match computed HMAC-SHA256 digest")


def sign_payload(raw_body: bytes, secret: str) -> str:
    """Compute the X-Signature value a real Ring webhook sender would attach.

    Used both by the app's own signature check (symmetrically, for tests) and by
    fixtures/generate_fixtures.py to produce realistic signed fixtures for the
    demo replay path.
    """
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


@dataclass
class ParsedWebhook:
    request_id: str
    event_id: str
    event_type: str
    sub_type: str | None
    device_id: str | None
    timestamp: str
    raw: dict[str, Any]


def parse_webhook(payload: dict[str, Any]) -> ParsedWebhook:
    """Normalize a Ring webhook body into the fields the reconciliation engine
    needs. Shape per PLATFORM-FACTS.md: motion_detected carries
    attributes.sub_type of motion/human/vehicle/other_motion; button_press has no
    sub_type. Deduplication key is meta.request_id."""
    meta = payload.get("meta", {})
    data = payload.get("data", {})
    attrs = data.get("attributes", {})
    event_type = data.get("type", "unknown")
    sub_type = attrs.get("sub_type")
    device_id = None
    relationships = data.get("relationships", {})
    device_link = relationships.get("devices", {}).get("data", {})
    if isinstance(device_link, dict):
        device_id = device_link.get("id")
    return ParsedWebhook(
        request_id=meta.get("request_id", ""),
        event_id=data.get("id", ""),
        event_type=event_type,
        sub_type=sub_type,
        device_id=device_id,
        timestamp=attrs.get("timestamp") or meta.get("time", ""),
        raw=payload,
    )


class SeenRequestStore:
    """In-memory idempotency guard on meta.request_id.

    A real deployment would back this with persistent storage; for this
    submission an in-memory set is honest about scope (single-process demo) and
    is exercised directly by tests.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_record(self, request_id: str) -> None:
        # An empty id used to be waved through, which meant a correctly signed
        # delivery with no `meta.request_id` replayed forever and appended an
        # event every time. A signature proves the body was not altered; it
        # says nothing about whether this is the first time it arrived. The
        # README's claim of idempotency on `meta.request_id` was only true for
        # deliveries that carried one, so a delivery that cannot be
        # deduplicated is refused rather than accepted unchecked.
        if not request_id:
            raise DuplicateWebhook("no request_id, cannot deduplicate")
        if request_id in self._seen:
            raise DuplicateWebhook(request_id)
        self._seen.add(request_id)
