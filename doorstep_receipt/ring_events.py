"""The RingEvent model and the parsing helpers that build one from Ring's
documented JSON:API and webhook shapes.

Split out of ring_client.py so the HTTP client itself stays focused on request
plumbing; this module owns only "what does a Ring event look like and how do
we get one out of a response body or a webhook payload."
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RingEvent:
    """A single normalized event from Ring's event history or a webhook."""

    event_id: str
    event_type: str  # e.g. "motion", "ding", "on_demand"
    sub_type: str | None  # e.g. "human", "vehicle", "animal", "other_motion"
    timestamp: dt.datetime
    device_id: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_human_motion(self) -> bool:
        return self.event_type == "motion" and self.sub_type == "human"

    @property
    def is_button_press(self) -> bool:
        return self.event_type in ("ding", "button_press")


def parse_timestamp(value: Any) -> dt.datetime:
    """Ring timestamps show up as either epoch millis or ISO-8601 strings in
    the documented shapes; handle both so a real response and a fixture behave
    the same way."""
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(text)
    raise ValueError(f"Unrecognized timestamp shape: {value!r}")


def event_from_jsonapi(entry: dict[str, Any]) -> RingEvent:
    """Build a RingEvent from one entry of a /v1/history/devices/{id}/events
    JSON:API response body."""
    attrs = entry.get("attributes", {})
    event_type_raw = attrs.get("event_type") or entry.get("type", "unknown")
    # Event history filtering supports dotted subtypes like "motion.human";
    # split them back out into (type, sub_type) the way webhook payloads
    # separate them into attributes.sub_type.
    sub_type = attrs.get("sub_type")
    event_type = event_type_raw
    if "." in event_type_raw:
        event_type, sub_type = event_type_raw.split(".", 1)
    ts_raw = attrs.get("start") or attrs.get("timestamp") or attrs.get("created_at")
    return RingEvent(
        event_id=entry.get("id", ""),
        event_type=event_type,
        sub_type=sub_type,
        timestamp=parse_timestamp(ts_raw),
        device_id=attrs.get("device_id"),
        raw=entry,
    )
