"""Evidence pack rendering: the document this whole product exists to produce.

Design direction (SPEC.md, "Design"): an evidence dossier, not a smart-home
dashboard. Deep parchment ground, ink serif for prose, monospace for anything
that is a machine record, and one rotated double-ruled stamp in sealing-wax red
or muted forest green for the verdict. The tokens now live in
``templates/_shell.html`` rather than in this file, because there are five
screens instead of one and a design system copied into five files is a design
system that drifts.

Two things this module owns beyond layout:

- **Provenance.** A claims desk reading a reconciliation is entitled to know
  where each side of it came from: which camera, and whether the carrier's
  figures were read off a screenshot by a model, matched by this app's own
  pattern rules, or typed by the person making the claim. The pack says so, with
  the model id when a model was involved, and repeats any warning the read
  produced instead of burying it.
- **The last guard pass.** ``guard.assert_document_clean`` runs over the
  assembled page. Every string was already guarded on the way in, so this should
  never fire. It is here because "should never fire" is how things ship broken.
"""

from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass
from typing import Any

from . import basis
from .guard_document import assert_document_clean
from . import timestamps as ts
from .carriers import resolve
from .reconcile import ReconciliationResult, Verdict
from .ring_client import RingEvent
from .templating import page, render

STAMP_LABELS = {
    Verdict.CONSISTENT: "Consistent with camera",
    Verdict.NOT_CONSISTENT: "Not consistent with camera",
    Verdict.INDETERMINATE: "On record, not conclusive",
}

_SOURCE_LABELS = {
    "bedrock": "Read from the carrier's own tracking page by a multimodal model on Amazon Bedrock.",
    "pattern": (
        "Read from the pasted tracking page by this app's own pattern rules, because the model was "
        "not reachable. Pattern rules cover the six carrier formats in carriers.py and nothing else."
    ),
    "manual": "Typed in by the person making this claim, from the tracking page they were looking at.",
    "none": "Not read automatically. The delivery details on this pack were entered by hand.",
}


@dataclass
class Attachment:
    label: str
    reference: str
    available: bool = True


def _fmt(value: dt.datetime, label: str = "UTC", seconds: bool = False) -> str:
    """One way of writing a time, from timestamps.py. Never a bare wall clock."""
    return ts.canonical(value, seconds=seconds, label=label)


def _event_label(e: RingEvent) -> str:
    """Plain English for a reader who has never seen Ring's event vocabulary.
    The raw code stays alongside it so nothing is reworded away."""
    if e.is_button_press:
        return "Doorbell button pressed"
    if e.is_human_motion:
        return "Person detected"
    if e.event_type == "motion":
        return f"Motion detected ({e.sub_type or 'unclassified'})"
    return e.event_type.replace("_", " ").capitalize()


def _event_code(e: RingEvent) -> str:
    return f"{e.event_type}.{e.sub_type}" if e.sub_type else e.event_type


def _event_table_html(result: ReconciliationResult, label: str = "UTC") -> str:
    if not result.matched_events:
        return '<p class="empty-set">No events were recorded in this window.</p>'
    rows = "\n".join(
        "<tr>"
        # Escaped like every other value on this page. `label` reaches here from
        # `timezone_printed`, a field a model fills in off a photographed web
        # page, and this was the one interpolation on the page that trusted it.
        f'<td class="nowrap" data-label="Time (earliest first)">'
        f'{html.escape(_fmt(e.timestamp, label, seconds=True))}</td>'
        f'<td data-label="Event">{html.escape(_event_label(e))} '
        f'<span class="event-code">({html.escape(_event_code(e))})</span></td>'
        f'<td data-label="Basis"><span class="basis">{basis.RECORDED}</span>'
        + (f'<br><span class="basis">classification {basis.REPORTED}</span>' if e.sub_type else "")
        + "</td>"
        f'<td data-label="Arrival at door">{"yes" if (e.is_human_motion or e.is_button_press) else "no"}</td>'
        f'<td data-label="ID">{html.escape(e.event_id)}</td>'
        "</tr>"
        for e in result.matched_events
    )
    note = (
        f'<p class="device-note">{html.escape(basis.DEVICE_CLASSIFICATION_NOTE)}</p>'
        if any(e.sub_type for e in result.matched_events)
        else ""
    )
    return (
        '<table class="log"><thead><tr><th scope="col">Time (earliest first)</th>'
        '<th scope="col">Event</th><th scope="col">Basis</th>'
        '<th scope="col">Arrival at door</th><th scope="col">ID</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>{note}"
    )


def _coverage_html(result: ReconciliationResult, label: str = "UTC") -> str:
    """Coverage sits beside the finding, in the same type size.

    A disclaimer set smaller than the claim it qualifies is a disclaimer its
    author hoped would not be read, and a reader whose job is rejection reads it
    first.
    """
    if not result.coverage_gaps:
        return (
            "<p>Every part of this window falls between two camera status samples no more than "
            "30 minutes apart, in which the device answered as online. That is what this app can "
            "say. It is not a claim that the camera recorded continuously: this app polls a status "
            "endpoint on a schedule and does not look between polls.</p>"
        )
    rows = "".join(
        "<tr>"
        f'<td class="nowrap" data-label="Interval">{html.escape(ts.window_text(g.start, g.end, label))}</td>'
        f'<td data-label="Why">{html.escape(g.reason)}</td>'
        "</tr>"
        for g in result.coverage_gaps
    )
    return (
        '<table class="log"><thead><tr><th scope="col">Interval</th>'
        '<th scope="col">Why coverage is not established</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
        "<p>An absence of events across an interval that was not established as recorded is not a "
        "finding, and this pack does not present it as one.</p>"
    )


def _corrections_html(corrections, label: str = "UTC") -> str:
    if not corrections:
        return ""
    rows = "".join(
        "<tr>"
        f'<td class="nowrap" data-label="Rev">{c.revision}</td>'
        f'<td class="nowrap" data-label="Made">{html.escape(_fmt(c.created_at))}</td>'
        f'<td data-label="Field">{html.escape(c.field)}</td>'
        f'<td data-label="Was">{html.escape(c.old_value)}</td>'
        f'<td data-label="Now">{html.escape(c.new_value)}</td>'
        f'<td data-label="Finding">{html.escape(c.old_verdict.replace("_", " "))} to '
        f'{html.escape(c.new_verdict.replace("_", " "))}</td>'
        f'<td data-label="Reason">{html.escape(c.reason)}</td>'
        "</tr>"
        for c in corrections
    )
    return (
        "<h2>Corrections to this claim</h2>"
        "<p>Each row supersedes the revision above it. A superseded finding is kept rather than "
        "removed: a record that can be corrected but does not show that it was corrected has had "
        "its history destroyed, and a correction that looks like a deletion reads as a cover-up.</p>"
        '<table class="log"><thead><tr><th scope="col">Rev</th><th scope="col">Made</th>'
        '<th scope="col">Field</th><th scope="col">Was</th><th scope="col">Now</th>'
        '<th scope="col">Finding</th><th scope="col">Reason given</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def _provenance_html(source: str, model_id: str, warnings: list[str]) -> str:
    parts = [f'<p class="note">{html.escape(_SOURCE_LABELS.get(source, _SOURCE_LABELS["none"]))}']
    if source == "bedrock" and model_id:
        parts.append(f" Model: <code>{html.escape(model_id)}</code>.")
    parts.append("</p>")
    if warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
        parts.append(f'<div class="note refused"><strong>Noted while reading</strong><ul>{items}</ul></div>')
    return "".join(parts)


def _definition(term: str, value: str, marker: str = "") -> str:
    if not value:
        return ""
    mark = f'<span class="basis">{marker}</span>' if marker else ""
    return f"<dt>{html.escape(term)}{mark}</dt><dd>{html.escape(value)}</dd>"


def evidence_body(
    result: ReconciliationResult,
    device_name: str,
    attachments: list[Attachment],
    claim_id: str = "",
    source: str = "manual",
    model_id: str = "",
    warnings: list[str] | None = None,
    generated_at: dt.datetime | None = None,
    revision: int = 1,
    corrections=None,
    controls_html: str = "",
) -> str:
    claim = result.claim
    window_start, window_end = claim.window()
    label = claim.timezone_label
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc)
    attachment_items = "\n".join(
        f"<li>{html.escape(a.label)}: "
        f"{html.escape(a.reference) if a.available else 'not available: ' + html.escape(a.reference)}</li>"
        for a in attachments
    ) or "<li>No attachments available for this window.</li>"

    timezone_note = (
        f"{label}, as printed on the tracking page."
        if claim.timezone_observed
        else f"{label}. The tracking page printed no timezone, so this one came from the browser "
             f"rather than from the page."
    )
    # Named from the carrier the width actually came from, not from the name on
    # the claim. Those are the same carrier now that a number and a name that
    # disagree are refused outright, and the sentence should be true because of
    # where it reads the number rather than because of that.
    width_carrier = resolve(claim.carrier_code).display_name
    adjusted = (
        f' <strong>Adjusted</strong> from {claim.default_window_minutes} minutes, which is the '
        f"width this app uses for {html.escape(width_carrier)}."
        if claim.window_adjusted
        else ""
    )

    return render(
        "evidence_pack.html",
        claim_id=claim_id or "not assigned",
        revision_text=f"{revision}" if revision == 1 else f"{revision} (supersedes rev. {revision - 1})",
        tracking_number=claim.tracking_number,
        carrier_name=claim.carrier_name,
        verdict_code=result.verdict.value,
        stamp_label=STAMP_LABELS[result.verdict],
        status_label=claim.status.value.replace("_", " "),
        claimed_at=_fmt(claim.claimed_at, label),
        status_line_html=_definition("Status line printed", claim.status_text, basis.REPORTED),
        printed_when_html=_definition("Time as printed", claim.claimed_at_text, basis.REPORTED),
        location_note_html=_definition("Location note printed", claim.location_note, basis.REPORTED),
        window_text=ts.window_text(window_start, window_end, label),
        window_adjusted_html=adjusted,
        window_reason=resolve(claim.carrier_code).window_reason,
        device_name=device_name,
        timezone_note=timezone_note,
        provenance_html=_provenance_html(source, model_id, warnings or []),
        event_table_html=_event_table_html(result, label),
        coverage_html=_coverage_html(result, label),
        corrections_html=_corrections_html(corrections or [], label),
        summary_sentence=result.summary_sentence,
        attachment_items_html=attachment_items,
        generated_at=_fmt(generated_at),
        controls_html=controls_html,
    )


def render_html(
    result: ReconciliationResult,
    device_name: str,
    attachments: list[Attachment],
    generated_at: dt.datetime | None = None,
    claim_id: str = "",
    source: str = "manual",
    model_id: str = "",
    warnings: list[str] | None = None,
    nav_html: str = "",
    revision: int = 1,
    corrections=None,
    controls_html: str = "",
) -> str:
    """The whole page, guarded as a whole before it is returned."""
    claim = result.claim
    body = evidence_body(
        result, device_name, attachments, claim_id, source, model_id, warnings, generated_at,
        revision, corrections, controls_html,
    )
    html_page = page(
        title=f"Claim {claim.tracking_number}: {claim.carrier_name}",
        subtitle="Evidence pack",
        body_html=body,
        nav_html=nav_html,
    )
    return assert_document_clean(html_page, where="evidence pack")


def to_dict(
    result: ReconciliationResult,
    device_name: str,
    attachments: list[Attachment],
    claim_id: str = "",
    source: str = "manual",
    model_id: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """JSON form of the evidence pack, for API consumers, the dispute pack and tests."""
    claim = result.claim
    window_start, window_end = claim.window()
    return {
        "claim_id": claim_id,
        "tracking_number": claim.tracking_number,
        "carrier_name": claim.carrier_name,
        "carrier_code": claim.carrier_code,
        "claimed_status": claim.status.value,
        "claimed_status_text": claim.status_text,
        "location_note": claim.location_note,
        "claimed_at": claim.claimed_at.isoformat(),
        "timezone": {"label": claim.timezone_label, "observed_on_page": claim.timezone_observed},
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "minutes": claim.window_minutes,
            "reason": resolve(claim.carrier_code).window_reason,
        },
        "device_name": device_name,
        "verdict": result.verdict.value,
        "verdict_label": STAMP_LABELS[result.verdict],
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "sub_type": e.sub_type,
                "timestamp": e.timestamp.isoformat(),
                "counts_as_arrival": bool(e.is_human_motion or e.is_button_press),
            }
            for e in result.matched_events
        ],
        "summary_sentence": result.summary_sentence,
        "coverage": {
            "established": not result.coverage_gaps,
            "indeterminate_reason": result.indeterminate_reason,
            "gaps": [
                {"start": g.start.isoformat(), "end": g.end.isoformat(), "minutes": g.minutes, "reason": g.reason}
                for g in result.coverage_gaps
            ],
        },
        "carrier_reading": {"source": source, "model_id": model_id, "warnings": warnings or []},
        "attachments": [
            {"label": a.label, "reference": a.reference, "available": a.available} for a in attachments
        ],
    }
