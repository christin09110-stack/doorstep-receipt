"""The document that leaves the app: print-grade, to DOCUMENT-CRAFT.md.

Doorstep Receipt renders the same record twice, on purpose.

The **screen pack** (``evidence.py``) is parchment, ink and a sealing-wax stamp.
That is this product's own voice and it is what the person who made the claim
looks at.

The **filed record**, here, is white paper and black ink on an A4 page box that
also fits US Letter. It is what goes in the zip and gets attached to a claim
form, and its reader is somebody whose job is to reject things and for whom
rejection is cheaper than acceptance. On that document every decorative choice
is a small claim that it came from a marketing department, so there are none:
no colour, no rounded corners, no shadows, no icons, nothing centred, nothing
justified, and a stated limit wherever there is a finding.

What it takes from the reference, and where each came from:

- **Masthead identity block** (CPR PD 32 §17.2): record number, form identifier
  with revision, exhibit range, prepared date, revision with supersession.
- **Provenance block** (FRE 901(b)(9): "evidence describing a process or system
  and showing that it produces an accurate result"): the device, its coverage and
  its blind spots, the clock, the event source and how its signature was checked,
  which parts of the prose were drafted by software, and the tool with its version.
- **Three bases in the gutter** (CPR PD 32 §18.2, since 1999): every finding
  marked RECORDED, REPORTED or INFERRED as a printed word, with its source or its
  rule named beside it.
- **Absence findings carry their coverage in the same type size**, in the same
  paragraph. A disclaimer set smaller than the claim it qualifies is a disclaimer
  its author hoped nobody would read.
- **Gaps are entries.** An unavailable clip is a row in the manifest with a
  reason, not a silence.

The stylesheet is inlined rather than linked. A pack whose files get separated in
an email thread must still render as the document it was, and a record that
renders in Charter here and Times there is two documents with one record number.
This repository ships no font files, so the stack does fall back: that is the
failure mode the reference warns about and it is stated in README.md rather than
hidden.
"""

from __future__ import annotations

import html

from . import basis
from . import timestamps as ts
from .guard_document import assert_document_clean
from .templating import TEMPLATE_DIR, render

FORM_ID = "DR-EVP Rev. 2026-09"


def _stylesheet() -> str:
    return "<style>\n" + (TEMPLATE_DIR / "record.css").read_text(encoding="utf-8") + "\n</style>"


def _block(number: str, mark: basis.Basis, body_html: str, source_line: str = "") -> str:
    exhibit = f'<span class="exh">{html.escape(mark.exhibit)}</span>' if mark.exhibit else ""
    source = f'<p class="source">{html.escape(source_line)}</p>' if source_line else ""
    return (
        f'<div class="block" data-basis="{mark.marker}">'
        f'<div class="mark"><span class="no">{html.escape(number)}</span>'
        f'<span class="basis">{mark.marker}</span>{exhibit}</div>'
        f'<div class="body">{body_html}{source}</div>'
        f"</div>"
    )


def _findings_html(record, exhibits: dict[str, str]) -> str:
    claim = record.claim
    result = record.result
    label = claim.timezone_label
    window_start, window_end = claim.window()
    window = ts.window_text(window_start, window_end, label)
    blocks = []

    verbatim = (
        f' The page displayed this as <span class="verbatim">"{html.escape(claim.claimed_at_text)}"</span>;'
        f" it is normalised above to minute precision, which is the precision the page gave."
        if claim.claimed_at_text
        else ""
    )
    status_line = (
        f' The status line as printed read <span class="verbatim">"{html.escape(claim.status_text)}"</span>.'
        if claim.status_text
        else ""
    )
    blocks.append(
        _block(
            "1",
            basis.reported(f"carrier tracking page, {claim.carrier_name}"),
            f"<p>The carrier's tracking page for {html.escape(claim.tracking_number)} "
            f"({html.escape(claim.carrier_name)}) showed the status "
            f"<span class='verbatim'>{html.escape(claim.status.value.replace('_', ' '))}</span> "
            f"at <time>{html.escape(ts.canonical(claim.claimed_at, label=label))}</time>."
            f"{status_line}{verbatim}</p>",
            source_line=f"Reported by the account holder from the carrier's page, entered "
            f"{ts.canonical(record.created_at)}.",
        )
    )

    if result.matched_events:
        rows = "".join(
            f"<p>An event with identifier <code>{html.escape(e.event_id)}</code> and device "
            f"timestamp <time>{html.escape(ts.canonical(e.timestamp, seconds=True, label=label))}</time> "
            f"is present in this app's event record.</p>"
            for e in result.matched_events
        )
        blocks.append(
            _block("2", basis.recorded(exhibits.get("events", "E1")), rows,
                   source_line="Received as a Ring webhook and stored at receipt. Identifiers are "
                               "listed in exhibit " + exhibits.get("events", "E1") + ".")
        )
        classified = [e for e in result.matched_events if e.sub_type]
        if classified:
            listed = ", ".join(
                f"<code>{html.escape(e.event_id)}</code> as <code>sub_type: {html.escape(e.sub_type)}</code>"
                for e in classified
            )
            blocks.append(
                _block(
                    "3",
                    basis.reported("Ring, by automatic device classification"),
                    f"<p>The device classified {listed}. {html.escape(basis.DEVICE_CLASSIFICATION_NOTE)}</p>",
                )
            )
    else:
        blocks.append(
            _block(
                "2",
                basis.recorded(exhibits.get("events", "E1")),
                f"<p>No event of any type is present in this app's event record for this device with a "
                f"device timestamp inside {html.escape(window)}.</p>",
                source_line="Exhibit " + exhibits.get("events", "E1") + " lists the window and returns no rows.",
            )
        )

    rule = (
        "an event of type button_press, or of type motion with the device classification human, "
        "with a device timestamp inside the window"
    )
    coverage_sentence = (
        "The device answered as online across the whole window, at the sample times listed below."
        if not result.coverage_gaps
        else "The device did not answer as online across the whole window: "
        + "; ".join(ts.window_text(g.start, g.end, label) for g in result.coverage_gaps)
        + "."
    )
    blocks.append(
        _block(
            "4",
            basis.inferred("interval test and set membership over the event record"),
            f"<p>Rule applied: {html.escape(rule)}. Window applied to: "
            f"<time>{html.escape(window)}</time>. Coverage during that window: "
            f"{html.escape(coverage_sentence)}</p>"
            f"<p>{html.escape(result.summary_sentence)}</p>"
            f"<p>This is a record of activity at one door. A parcel left at a side entrance, "
            f"handed to a neighbour, or placed outside this camera's field of view would not "
            f"appear here. Treat a missing entry as missing information.</p>",
        )
    )
    if result.indeterminate_reason:
        blocks.append(
            _block(
                "5",
                basis.inferred("coverage test over the camera status samples"),
                f"<p>{html.escape(result.indeterminate_reason)}</p>",
            )
        )
    return "".join(blocks)


def _event_log_html(record) -> str:
    label = record.claim.timezone_label
    if not record.result.matched_events:
        return (
            '<table class="log"><thead><tr><th>Time (earliest first)</th><th>Event</th>'
            "<th>Basis</th><th>Identifier</th></tr></thead><tbody>"
            '<tr class="empty-row"><td colspan="4">No rows. No event is present in this app\'s '
            "event record inside the window stated above.</td></tr></tbody></table>"
        )
    rows = "".join(
        "<tr>"
        f'<td><time>{html.escape(ts.canonical(e.timestamp, seconds=True, label=label))}</time></td>'
        f"<td>{html.escape(e.event_type)}"
        + (f" / <code>sub_type: {html.escape(e.sub_type)}</code>" if e.sub_type else "")
        + "</td>"
        f'<td class="basis-cell">{basis.RECORDED}'
        + (f"<br>classification {basis.REPORTED}" if e.sub_type else "")
        + "</td>"
        f"<td><code>{html.escape(e.event_id)}</code></td>"
        "</tr>"
        for e in record.result.matched_events
    )
    return (
        '<table class="log"><thead><tr><th>Time (earliest first)</th><th>Event</th>'
        f"<th>Basis</th><th>Identifier</th></tr></thead><tbody>{rows}</tbody></table>"
        f"<p>Times are {html.escape(label)}. The event is recorded; any classification beside it "
        "is the device manufacturer's and has not been checked by a person.</p>"
    )


def _coverage_html(record) -> str:
    label = record.claim.timezone_label
    if not record.result.coverage_gaps:
        return (
            "<p>Every part of this window falls between two camera status samples no more than "
            "30 minutes apart, in which the device answered as online. That is what this app can "
            "say. It is not a statement that the camera was recording continuously: this app polls "
            "a status endpoint on a schedule and does not look between polls.</p>"
        )
    rows = "".join(
        "<tr>"
        f'<td><time>{html.escape(ts.window_text(g.start, g.end, label))}</time></td>'
        f"<td>{html.escape(g.reason)}</td>"
        "</tr>"
        for g in record.result.coverage_gaps
    )
    return (
        '<table class="log"><thead><tr><th>Interval</th><th>Why coverage is not established</th>'
        f"</tr></thead><tbody>{rows}</tbody></table>"
        "<p>An absence of events across an interval that was not established as recorded is not a "
        "finding, and this record does not present it as one.</p>"
    )


def _corrections_html(record) -> str:
    if not record.corrections:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{c.revision}</td>"
        f'<td><time>{html.escape(ts.canonical(c.created_at))}</time></td>'
        f"<td>{html.escape(c.field)}</td>"
        f"<td>{html.escape(c.old_value)}</td>"
        f"<td>{html.escape(c.new_value)}</td>"
        f"<td>{html.escape(c.old_verdict.replace('_', ' '))} to {html.escape(c.new_verdict.replace('_', ' '))}</td>"
        f"<td>{html.escape(c.reason)}</td>"
        "</tr>"
        for c in record.corrections
    )
    return (
        '<h2 class="section">Corrections to this record</h2>'
        "<p>Each row supersedes the revision above it. A superseded finding is kept rather than "
        "removed: a record that can be corrected but does not show that it was corrected has had "
        "its history destroyed, and a correction that looks like a deletion reads as a cover-up.</p>"
        '<table class="log"><thead><tr><th>Rev</th><th>Made</th><th>Field</th><th>Was</th>'
        f"<th>Now</th><th>Finding</th><th>Reason given</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def build(record, manifest, version: str = "0.2.0", exhibits: dict[str, str] | None = None) -> str:
    """Render the filed record for one claim."""
    exhibits = exhibits or {}
    # Two different times, and they are not interchangeable.
    #
    # `Prepared` in the masthead is when this revision of the record came into
    # existence. It belongs to the identity block — the block a reader
    # photographs when they need to quote the document — and it must be the
    # same on every render, or two people opening record aac3ff8b revision 1
    # are holding documents that disagree about when it was made, which is the
    # first thing a reader whose job is rejection will notice.
    #
    # `Produced by` below is when this particular rendering was run, which is a
    # different fact and is stated separately.
    revision_at = record.corrections[-1].created_at if record.corrections else record.created_at
    prepared = ts.canonical(revision_at, seconds=True)
    rendered = ts.canonical(manifest.built_at, seconds=True)
    device = record.device_name
    revision = record.revision
    revision_text = f"{revision}" if revision == 1 else f"{revision} (supersedes rev. {revision - 1})"
    exhibit_ids = [i.exhibit_id for i in manifest.items]
    exhibit_range = f"{exhibit_ids[0]} to {exhibit_ids[-1]}" if len(exhibit_ids) > 1 else (exhibit_ids[0] if exhibit_ids else "none")

    carrier_source = {
        "bedrock": f"Read from an image or text of the carrier's own tracking page by "
                   f"{record.reading_model or 'a multimodal model'} on Amazon Bedrock, then checked "
                   f"against this app's carrier registry. Every field was shown to the account "
                   f"holder for correction before this record was created.",
        "pattern": "Read from text of the carrier's own tracking page by this app's pattern rules, "
                   "the drafting model being unreachable, then shown to the account holder for "
                   "correction before this record was created.",
        "manual": "Typed in by the account holder from the carrier's tracking page.",
        "none": "Entered by the account holder. Nothing was read automatically.",
    }.get(record.reading_source, "Entered by the account holder.")

    letter = record.latest_letter
    prose_line = (
        f"The covering letter in exhibit {exhibits.get('letter', 'E3')} was drafted by "
        f"{record.reading_model or 'a model on Amazon Bedrock'} from the fields in this record and "
        f"{'edited by the account holder' if letter and letter.source == 'user' else 'accepted unchanged'}. "
        if letter and letter.source in ("bedrock", "user")
        else "No prose in this record was drafted by software. The findings above are produced by "
             "fixed sentences with this record's own values substituted. "
    ) + (
        "Every string in this record, including anything a model wrote, was checked against this "
        "app's refused-language rules before it was rendered."
    )

    # The document-level check runs here, not only on the evidence pack. This
    # is the rendering that goes into the zip and on to the carrier and the
    # ombudsman, so it is the one that most needs the last pass. Every string
    # was guarded on the way in; this catches the one that was not.
    return assert_document_clean(render(
        "filed_record.html",
        stylesheet_html=_stylesheet(),
        record_no=record.claim_id,
        form_id=FORM_ID,
        version=version,
        revision_text=revision_text,
        exhibit_range=exhibit_range,
        prepared=prepared,
        device_line=f"Ring doorbell, named {device} by the account holder. "
                    f"Device identifier {record.device_id or 'not recorded'}.",
        coverage_line="The camera's field of view as installed by the account holder. This app has "
                      "no way to inspect it and does not assert what it shows.",
        blind_spots="Anything outside that field of view: a side or rear entrance, a porch out of "
                    "shot, a parcel handed to a neighbour, or a parcel left beyond the camera's "
                    "range. None of these would appear in this record.",
        event_source="Ring webhook. HMAC-SHA256 signature over the raw request body, checked at "
                     "receipt against the account's shared secret; duplicates rejected on "
                     "meta.request_id. Camera status comes from GET /v1/devices/{id}/status, "
                     "polled on a schedule, because Ring publishes no offline event.",
        clock_line="Device clock, as reported by Ring in each event. Drift not measured: Ring "
                   "publishes no clock reference for a doorbell and this app does not invent one. "
                   "Times in this record are not corrected for drift.",
        carrier_source=carrier_source,
        prose_line=prose_line,
        produced_by=f"Doorstep Receipt {version}, record renderer {version}. "
                    f"This sheet was rendered {rendered}.",
        checking_line="See the exhibit list and integrity manifest on the last sheet. It carries "
                      "the full digest of every file in this pack and the command that checks them.",
        findings_html=_findings_html(record, exhibits),
        event_log_html=_event_log_html(record),
        coverage_html=_coverage_html(record),
        corrections_html=_corrections_html(record),
        manifest_scope=manifest.scope_sentence,
        manifest_html=manifest.html_table(),
    ), where="filed record")
