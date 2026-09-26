"""The exhibits themselves: the spreadsheets, and the list of what is missing.

Split from ``dispute_pack.py`` so that assembling the zip and deciding what
goes in it are separate things to read. A claims desk lives in a spreadsheet,
so the event log and the camera status samples are CSV rather than something
prettier.

``gaps_for`` is the half that matters. It enumerates what this pack should have
contained and does not, with the reason: the clip that needs a
continuous-recording plan, the still that cannot exist because no event exists
to take it from, and every interval where the camera's coverage was not
established. Those are entries in the manifest, not absences from it.
"""

from __future__ import annotations

import csv
import io

from . import timestamps as ts
from .coverage import ONLINE, STATUS_EVENT_TYPE
from .manifest import PackGap

def event_log_csv(record) -> bytes:
    """The event log as a spreadsheet, because a claims desk lives in one."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["timestamp", "timezone", "event_type", "device_classification", "basis",
         "counts_as_arrival", "event_id", "device_id"]
    )
    for event in record.result.matched_events:
        writer.writerow(
            [
                ts.short(event.timestamp, seconds=True),
                record.claim.timezone_label,
                event.event_type,
                event.sub_type or "",
                "RECORDED; classification REPORTED by device" if event.sub_type else "RECORDED",
                "yes" if (event.is_human_motion or event.is_button_press) else "no",
                event.event_id,
                event.device_id or "",
            ]
        )
    return buffer.getvalue().encode("utf-8")


def status_csv(record, events) -> bytes:
    """The camera status samples the coverage findings rest on."""
    window_start, window_end = record.claim.window()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["sample_time", "timezone", "device_answered", "inside_checked_window"])
    for event in sorted((e for e in events if e.event_type == STATUS_EVENT_TYPE), key=lambda e: e.timestamp):
        writer.writerow(
            [
                ts.short(event.timestamp, seconds=True),
                record.claim.timezone_label,
                event.sub_type or ONLINE,
                "yes" if window_start <= event.timestamp <= window_end else "no",
            ]
        )
    return buffer.getvalue().encode("utf-8")


def gaps_for(record) -> list[PackGap]:
    gaps = [
        PackGap(
            "G1",
            "Video clip of the checked window",
            "Ring clip retrieval requires a continuous-recording plan on the account. Without one "
            "the endpoint returns 416 TIMESTAMP_NOT_FOUND, and no clip was retrieved for this claim.",
        )
    ]
    if not record.result.matched_events:
        gaps.append(
            PackGap(
                "G2",
                "Watermarked still from the checked window",
                "No event exists inside the window to take a still from. Ring watermarks its own "
                "snapshots and the watermark cannot be turned off, which is why a still would have "
                "carried provenance had there been one.",
            )
        )
    for index, gap in enumerate(record.result.coverage_gaps, start=len(gaps) + 1):
        gaps.append(
            PackGap(
                f"G{index}",
                f"Camera coverage for {ts.window_text(gap.start, gap.end, record.claim.timezone_label)}",
                gap.reason,
            )
        )
    return gaps
