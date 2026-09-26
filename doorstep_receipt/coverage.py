"""Was the camera watching? The difference between two very different findings.

An empty event log means one of two things and they are not close to each other.
Either nothing happened at the door, or nothing was being recorded. A pack that
reports the first when the truth is the second is evidence of nothing, and it is
the one way this product could do real harm: a confident "not consistent with
camera" on a claim form, about an hour when the doorbell was unplugged.

So coverage is established before a "not consistent" verdict is allowed to
stand, and where it is not established the verdict is downgraded and the reason
is named.

**How coverage is known, stated plainly, because it is a limitation.** Ring
publishes no offline webhook. What it publishes is
``GET /v1/devices/{id}/status``, which ``ring_client.get_device_status`` calls
and ``status_poller.py`` samples on a schedule. A sample is a point in time, not
an interval. This app therefore treats the span between two consecutive online
samples as covered only when they are no further apart than ``MAX_SAMPLE_GAP``,
and treats everything else as not established, including the time before the
first sample and after the last.

That is weaker than "the camera was recording" and the pack says the weaker
thing. What the record supports is: the device answered as online at 08:10 and
again at 08:25, and this app did not look in between.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .ring_events import RingEvent

STATUS_EVENT_TYPE = "device_status"
ONLINE = "online"
OFFLINE = "offline"

# How far apart two online samples may be before the span between them stops
# counting as covered. Fifteen minutes is the poller's default interval, doubled,
# so a single missed poll does not open a gap but two in a row do.
MAX_SAMPLE_GAP = dt.timedelta(minutes=30)


@dataclass(frozen=True)
class CoverageGap:
    """An interval overlapping the window in which coverage is not established."""

    start: dt.datetime
    end: dt.datetime
    reason: str

    @property
    def minutes(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 60))


def sample(timestamp: dt.datetime, online: bool = True, device_id: str = "dev-1") -> RingEvent:
    """A camera status sample, in the same RingEvent shape everything else uses."""
    return RingEvent(
        event_id=f"status-{timestamp.isoformat()}",
        event_type=STATUS_EVENT_TYPE,
        sub_type=ONLINE if online else OFFLINE,
        timestamp=timestamp,
        device_id=device_id,
    )


def status_samples(events: list[RingEvent]) -> list[RingEvent]:
    return sorted((e for e in events if e.event_type == STATUS_EVENT_TYPE), key=lambda e: e.timestamp)


def covered_spans(events: list[RingEvent]) -> list[tuple[dt.datetime, dt.datetime]]:
    """The spans this app can say the camera answered as online across.

    Only the gap between two consecutive online samples counts, and only when it
    is no wider than MAX_SAMPLE_GAP. A lone sample covers an instant, and an
    instant is not a span.
    """
    samples = status_samples(events)
    spans: list[tuple[dt.datetime, dt.datetime]] = []
    for earlier, later in zip(samples, samples[1:]):
        if (earlier.sub_type or ONLINE) != ONLINE or (later.sub_type or ONLINE) != ONLINE:
            continue
        if later.timestamp - earlier.timestamp <= MAX_SAMPLE_GAP:
            spans.append((earlier.timestamp, later.timestamp))
    return _merge(spans)


def _merge(spans: list[tuple[dt.datetime, dt.datetime]]) -> list[tuple[dt.datetime, dt.datetime]]:
    merged: list[tuple[dt.datetime, dt.datetime]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _offline_at(events: list[RingEvent], start: dt.datetime, end: dt.datetime) -> bool:
    return any(
        (s.sub_type or ONLINE) == OFFLINE and start <= s.timestamp <= end
        for s in status_samples(events)
    )


def gaps_in_window(
    events: list[RingEvent], window_start: dt.datetime, window_end: dt.datetime
) -> list[CoverageGap]:
    """Every part of the window that coverage does not account for."""
    if not status_samples(events):
        return [
            CoverageGap(
                window_start,
                window_end,
                "This app holds no camera status samples for this window, so it cannot say "
                "whether the camera was recording.",
            )
        ]

    gaps: list[CoverageGap] = []
    cursor = window_start
    for span_start, span_end in covered_spans(events):
        if span_end <= cursor:
            continue
        if span_start >= window_end:
            break
        if span_start > cursor:
            gaps.append(CoverageGap(cursor, min(span_start, window_end), _reason(events, cursor, span_start)))
        cursor = max(cursor, span_end)
    if cursor < window_end:
        gaps.append(CoverageGap(cursor, window_end, _reason(events, cursor, window_end)))
    return [g for g in gaps if g.start < g.end]


def _reason(events: list[RingEvent], start: dt.datetime, end: dt.datetime) -> str:
    if _offline_at(events, start, end):
        return (
            "A camera status sample reported the device offline in this interval. The interval is "
            "bounded by the samples either side of it and is no narrower than the polling interval."
        )
    return (
        "No two camera status samples less than 30 minutes apart cover this interval, so this app "
        "did not establish that the camera was recording across it."
    )


def covered(events: list[RingEvent], window_start: dt.datetime, window_end: dt.datetime) -> bool:
    return not gaps_in_window(events, window_start, window_end)
