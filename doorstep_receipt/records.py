"""Claim records, and the codecs that put one in a database row and back.

A claim is stored as the outcome that was reached, not as the inputs that would
let it be recomputed. That is deliberate and it is the difference between a log
and a record. If the reconciliation rules change next month, a claim filed today
must still read exactly as it read when it was filed, because the user may
already have sent it to a retailer. Re-deriving a verdict on read would mean a
document could quietly change its mind after being cited, which is the one thing
an evidence pack is not allowed to do.

So ``events_json`` holds the camera events as they were matched, the verdict and
the sentence are stored verbatim, and nothing on the read path calls
``reconcile()``.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

from .carrier import CarrierClaim, CarrierStatus
from .coverage import CoverageGap
from .guard import GuardFinding
from .reconcile import ReconciliationResult, Verdict
from .ring_events import RingEvent


@dataclass
class ClaimLetter:
    """A revision of the letter the user sends to the retailer."""

    body: str
    subject: str = ""
    revision: int = 1
    source: str = "template"  # "bedrock", "template" or "user"
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    guard_note: str = ""

    @property
    def was_refused(self) -> bool:
        return bool(self.guard_note)


# What happened after the pack was sent. The research behind this app found that
# 439 of 691 posts about a parcel marked delivered also complain about the claim
# process, and Citizens Advice's number is that a third of people take no action
# at all. The evidence pack answers the first five minutes. Whether they get
# their money back is decided in the weeks after, and a claim nobody followed up
# is the same outcome as a claim nobody made.
OUTCOMES = {
    "open": "Not sent yet",
    "sent": "Sent to the retailer",
    "refunded": "Refunded or replaced",
    "refused": "Refused by the retailer",
    "no_reply": "No reply",
    "withdrawn": "Withdrawn",
}
CHASE_AFTER_DAYS = 14


@dataclass
class Correction:
    """One change to a claim after it was first filed, with what it changed.

    Corrections are appended, never applied in place. A record that can be
    edited but does not show that it was edited has had its history destroyed,
    and on a document somebody may already have sent to a retailer, a silent
    change is worse than no change at all. The superseded verdict is kept beside
    the new one.

    This exists because the editable window is the most dangerous control in the
    product: shift a window by twenty minutes and a delivery that did happen
    becomes a delivery that was not observed, with this app's formatting making
    the error look authoritative. Keeping both findings, and printing the window
    that was actually used, is what makes the control safe enough to offer.
    """

    revision: int
    field: str
    old_value: str
    new_value: str
    reason: str
    old_verdict: str
    new_verdict: str
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


@dataclass
class ClaimRecord:
    claim_id: str
    result: ReconciliationResult
    device_name: str
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    reading_source: str = "manual"
    reading_model: str = ""
    reading_warnings: list[str] = field(default_factory=list)
    notes: str = ""
    device_id: str = ""
    outcome: str = "open"
    outcome_note: str = ""
    outcome_at: dt.datetime | None = None
    letters: list[ClaimLetter] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)

    @property
    def revision(self) -> int:
        return len(self.corrections) + 1

    @property
    def outcome_label(self) -> str:
        return OUTCOMES.get(self.outcome, self.outcome)

    def needs_chasing(self, now: dt.datetime | None = None) -> bool:
        """Sent, no answer, and long enough ago to be worth a second letter."""
        if self.outcome != "sent" or self.outcome_at is None:
            return False
        now = now or dt.datetime.now(dt.timezone.utc)
        return (now - self.outcome_at).days >= CHASE_AFTER_DAYS

    def days_since_sent(self, now: dt.datetime | None = None) -> int | None:
        if self.outcome_at is None:
            return None
        return ((now or dt.datetime.now(dt.timezone.utc)) - self.outcome_at).days

    @property
    def claim(self) -> CarrierClaim:
        return self.result.claim

    @property
    def verdict(self) -> Verdict:
        return self.result.verdict

    @property
    def latest_letter(self) -> ClaimLetter | None:
        return self.letters[-1] if self.letters else None

    def search_text(self) -> str:
        """Everything a user might type into the search box, in one string."""
        claim = self.claim
        parts = [
            self.claim_id,
            claim.tracking_number,
            claim.carrier_name,
            claim.carrier_code,
            claim.status.value.replace("_", " "),
            claim.status_text,
            claim.location_note,
            claim.reference,
            self.device_name,
            self.result.verdict.value.replace("_", " "),
            self.outcome,
            self.outcome_label,
            self.outcome_note,
            self.result.summary_sentence,
            self.notes,
            self.latest_letter.body if self.latest_letter else "",
        ]
        return "\n".join(p for p in parts if p)


def event_to_json(event: RingEvent) -> dict:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "sub_type": event.sub_type,
        "timestamp": event.timestamp.isoformat(),
        "device_id": event.device_id,
        "raw": event.raw,
    }


def event_from_json(data: dict) -> RingEvent:
    return RingEvent(
        event_id=data["event_id"],
        event_type=data["event_type"],
        sub_type=data.get("sub_type"),
        timestamp=dt.datetime.fromisoformat(data["timestamp"]),
        device_id=data.get("device_id"),
        raw=data.get("raw") or {},
    )


def claim_to_row(record: ClaimRecord) -> dict:
    claim = record.claim
    return {
        "claim_id": record.claim_id,
        "created_at": record.created_at.isoformat(),
        "tracking_number": claim.tracking_number,
        "carrier_code": claim.carrier_code,
        "carrier_name": claim.carrier_name,
        "status": claim.status.value,
        "claimed_at": claim.claimed_at.isoformat(),
        "claimed_at_text": claim.claimed_at_text,
        "window_minutes": claim.window_minutes,
        "default_window_minutes": claim.default_window_minutes,
        "status_text": claim.status_text,
        "location_note": claim.location_note,
        "reference": claim.reference,
        "timezone_label": claim.timezone_label,
        "timezone_observed": int(claim.timezone_observed),
        "verdict": record.result.verdict.value,
        "summary_sentence": record.result.summary_sentence,
        "device_name": record.device_name,
        "reading_source": record.reading_source,
        "reading_model": record.reading_model,
        "reading_warnings": json.dumps(record.reading_warnings),
        "notes": record.notes,
        "device_id": record.device_id,
        "outcome": record.outcome,
        "outcome_note": record.outcome_note,
        "outcome_at": record.outcome_at.isoformat() if record.outcome_at else "",
        "events_json": json.dumps([event_to_json(e) for e in record.result.matched_events]),
        "coverage_json": json.dumps(
            [
                {"start": g.start.isoformat(), "end": g.end.isoformat(), "reason": g.reason}
                for g in record.result.coverage_gaps
            ]
        ),
        "indeterminate_reason": record.result.indeterminate_reason,
        "search_text": record.search_text().lower(),
    }


def claim_from_row(row) -> ClaimRecord:
    claim = CarrierClaim(
        tracking_number=row["tracking_number"],
        carrier_name=row["carrier_name"],
        status=CarrierStatus(row["status"]),
        claimed_at=dt.datetime.fromisoformat(row["claimed_at"]),
        window_minutes=row["window_minutes"],
        carrier_code=row["carrier_code"],
        status_text=row["status_text"] or "",
        location_note=row["location_note"] or "",
        reference=row["reference"] or "",
        timezone_label=row["timezone_label"] or "UTC",
        timezone_observed=bool(row["timezone_observed"]),
        claimed_at_text=row["claimed_at_text"] or "",
        default_window_minutes=row["default_window_minutes"] or row["window_minutes"],
    )
    result = ReconciliationResult(
        claim=claim,
        matched_events=[event_from_json(e) for e in json.loads(row["events_json"] or "[]")],
        verdict=Verdict(row["verdict"]),
        summary_sentence=row["summary_sentence"],
        coverage_gaps=[
            CoverageGap(
                dt.datetime.fromisoformat(g["start"]),
                dt.datetime.fromisoformat(g["end"]),
                g["reason"],
            )
            for g in json.loads(row["coverage_json"] or "[]")
        ],
        indeterminate_reason=row["indeterminate_reason"] or "",
    )
    return ClaimRecord(
        claim_id=row["claim_id"],
        result=result,
        device_name=row["device_name"],
        created_at=dt.datetime.fromisoformat(row["created_at"]),
        reading_source=row["reading_source"] or "manual",
        reading_model=row["reading_model"] or "",
        reading_warnings=json.loads(row["reading_warnings"] or "[]"),
        notes=row["notes"] or "",
        device_id=row["device_id"] or "",
        outcome=row["outcome"] or "open",
        outcome_note=row["outcome_note"] or "",
        outcome_at=dt.datetime.fromisoformat(row["outcome_at"]) if row["outcome_at"] else None,
    )


def findings_note(findings: list[GuardFinding]) -> str:
    """The one-line record of a guard refusal, stored with the letter revision.

    Rule names only. This string is persisted on the letter and rendered back
    onto the claim page, so a phrase repeated here is a phrase published here,
    whatever the label beside it says.
    """
    if not findings:
        return ""
    return ", ".join(sorted({f.rule for f in findings}))
