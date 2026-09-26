"""Reconciliation engine: what the carrier claimed versus what the camera saw.

Language rule, from PLATFORM-FACTS.md's Ring section: Ring's own classifier has
been documented mislabeling a motorised wheelchair as a package, so this engine
never accuses a person and never asserts what a human did. It only states what
is and is not on record: "a person was recorded at the door at 14:11", never
"the driver did not come." There is no verdict category for driver dishonesty.

Since the upgrade that rule is not held by careful writing alone. Every sentence
this engine produces is run through ``guard.py`` before it is returned, and a
sentence that trips a rule raises rather than rendering. These sentences are
written by hand and should never trip one; the check is here so that the day
somebody edits one carelessly, a test fails instead of a claims desk receiving
an accusation this app cannot support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import guard
from . import timestamps as ts
from .coverage import STATUS_EVENT_TYPE, CoverageGap, gaps_in_window
from .carrier import CarrierClaim, CarrierStatus
from .ring_client import RingEvent


class Verdict(str, Enum):
    CONSISTENT = "consistent_with_camera"
    NOT_CONSISTENT = "not_consistent_with_camera"
    INDETERMINATE = "indeterminate"


@dataclass
class ReconciliationResult:
    claim: CarrierClaim
    matched_events: list[RingEvent] = field(default_factory=list)
    verdict: Verdict = Verdict.INDETERMINATE
    summary_sentence: str = ""
    coverage_gaps: list[CoverageGap] = field(default_factory=list)
    # Why the verdict is indeterminate, when it is. "Indeterminate" on its own
    # tells a claims desk nothing; "the camera was not known to be recording for
    # 22 minutes of the window" tells them what to do next.
    indeterminate_reason: str = ""

    @property
    def window_start_end(self):
        return self.claim.window()

    @property
    def window_reason(self) -> str:
        """Why this claim's window is the width it is, in the carrier's terms."""
        from .carriers import resolve

        return resolve(self.claim.carrier_code).window_reason

    @property
    def arrival_events(self) -> list[RingEvent]:
        """The events in the window that could be an arrival at the door.

        A vehicle passing is in ``matched_events`` because hiding it would be
        editing the record. It is not in this list because a vehicle is not
        somebody at a door.
        """
        return [e for e in self.matched_events if e.is_human_motion or e.is_button_press]


def _events_in_window(events: list[RingEvent], claim: CarrierClaim) -> list[RingEvent]:
    """Events at the door inside the window, earliest first.

    Camera status samples are excluded. They arrive in the same stream and have
    the same shape, but they are a record of whether the camera was answering,
    not a record of anything happening at the door. They belong in the pack's
    provenance block (see coverage.py), never in its event log, where a reader
    would reasonably read every row as something that happened outside.
    """
    start, end = claim.window()
    return sorted(
        (e for e in events if start <= e.timestamp <= end and e.event_type != STATUS_EVENT_TYPE),
        key=lambda e: e.timestamp,
    )


def _fmt(value, label: str = "UTC") -> str:
    return ts.canonical(value, label=label)


def reconcile(claim: CarrierClaim, events: list[RingEvent]) -> ReconciliationResult:
    """Compare a carrier's claimed status against Ring events in the claim's
    time window and produce a verdict plus a plain-English sentence.

    Rules (deliberately simple and legible; this is the part a judge, and a
    claims-desk reader, has to be able to audit by eye):

    1. status == DELIVERED:
       - a human-motion or button-press event exists in the window -> CONSISTENT
       - no such event exists -> NOT_CONSISTENT ("nothing was recorded")
    2. status in {ATTEMPTED_DELIVERY, OUT_FOR_DELIVERY}:
       - a human-motion or button-press event exists in the window ->
         INDETERMINATE. This is not treated as catching the carrier out: the
         event could be a neighbour, a different visitor, or the same driver
         genuinely knocking without a package. The sentence says only what is
         on record.
       - no such event exists -> CONSISTENT (nothing recorded is what an
         attempted-but-not-completed status would look like on camera too, so
         this is not flagged as a discrepancy).
    3. Coverage overrides rule 1's second branch. A NOT_CONSISTENT verdict is
       downgraded to INDETERMINATE, with a stated reason, whenever any part of
       the window is not established as recorded (see coverage.py). Nothing
       recorded while nothing was recording is not a finding.
    """
    relevant = _events_in_window(events, claim)
    arrival_events = [e for e in relevant if e.is_human_motion or e.is_button_press]
    window_start, window_end = claim.window()
    gaps = gaps_in_window(events, window_start, window_end)
    label = claim.timezone_label
    window = ts.window_text(window_start, window_end, label)
    claimed = _fmt(claim.claimed_at, label)

    # Every sentence names the window it is about. That is not decoration: the
    # window is adjustable, and an adjusted window can turn a delivery that did
    # happen into a delivery that was not observed. "Nothing was recorded
    # between 14:05 and 14:35" survives being wrong, because a reader who knows
    # the right time can see at once that the wrong hour was checked. "No
    # delivery was made" does not survive being wrong at all.
    if claim.status == CarrierStatus.DELIVERED:
        if arrival_events:
            first = arrival_events[0]
            verdict = Verdict.CONSISTENT
            what = "a button press" if first.is_button_press else "a person"
            sentence = (
                f"The carrier's tracking marked this parcel delivered at {claimed}. "
                f"Camera record for {window}: {what} was recorded at the door at "
                f"{_fmt(first.timestamp, label)}."
            )
        else:
            verdict = Verdict.NOT_CONSISTENT
            sentence = (
                f"The carrier's tracking marked this parcel delivered at {claimed}. "
                f"Camera record for {window}: no arrival was recorded at the door in "
                f"that window, at any point before or after the time the carrier gives."
            )
    else:
        # ATTEMPTED_DELIVERY or OUT_FOR_DELIVERY
        status_words = claim.status.value.replace("_", " ")
        if arrival_events:
            first = arrival_events[0]
            verdict = Verdict.INDETERMINATE
            what = "a button press" if first.is_button_press else "a person"
            sentence = (
                f"The carrier's tracking shows '{status_words}' at {claimed}. "
                f"Camera record for {window}: {what} was recorded at the door at "
                f"{_fmt(first.timestamp, label)}. This does not establish who that was "
                f"or what happened; it is offered as the record, not a conclusion."
            )
        else:
            verdict = Verdict.CONSISTENT
            sentence = (
                f"The carrier's tracking shows '{status_words}' at {claimed}. "
                f"Camera record for {window}: no arrival was recorded at the door, which "
                f"is what an attempt that did not reach the door would also look like."
            )

    # A "not consistent" verdict says nothing was recorded. That is only a
    # finding if the camera was recording. Where coverage is not established the
    # verdict is downgraded rather than stated, and the reason is named: an empty
    # event log because nobody came and an empty event log because nobody was
    # watching look identical, and only one of them is evidence.
    reason = ""
    if gaps and verdict == Verdict.NOT_CONSISTENT:
        verdict = Verdict.INDETERMINATE
        total = sum(g.minutes for g in gaps)
        reason = (
            f"No arrival was recorded, but the camera was not known to be recording for "
            f"{total} minute(s) of this window. {gaps[0].reason}"
        )
        sentence = (
            f"{sentence} The camera's own coverage of this window is incomplete: "
            f"{ts.window_text(gaps[0].start, gaps[0].end, label)} is not established as recorded. "
            f"An absence of events over a period that was not being recorded is not a finding."
        )
    elif gaps:
        reason = (
            f"Part of this window was not established as recorded. {gaps[0].reason}"
        )

    # These sentences are written by hand above. The check is cheap, and it means
    # the product's central promise is enforced by code on every path rather than
    # by whoever last edited this file.
    guard.assert_clean(sentence, "reconciliation sentence")

    return ReconciliationResult(
        claim=claim,
        matched_events=relevant,
        verdict=verdict,
        summary_sentence=sentence,
        coverage_gaps=gaps,
        indeterminate_reason=reason,
    )
