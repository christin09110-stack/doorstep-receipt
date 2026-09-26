"""Page construction for every screen that is not the evidence pack itself.

``evidence.py`` owns the document, because the document is the product. This
owns the four screens around it: intake, the review step, the claim file, the
letter editor and the pack page. All of them use the same parchment shell and
the same tokens, from ``templates/_shell.html``.

The review step is the one worth defending. A model reads the carrier's page and
this app could go straight from that reading to a stored claim. It does not. The
reading is shown, every field is editable, and nothing is written until the
person accepts it. A model that misreads a 3 as an 8 in a tracking number should
cost a correction, not a wrong document sent to a retailer.
"""

from __future__ import annotations

import datetime as dt
import html
import json

from . import timestamps as ts
from .manifest import grouped
from . import guard
from .carrier import CarrierStatus
from .carriers import CARRIERS, UNKNOWN_CARRIER
from .evidence import STAMP_LABELS
from .records import OUTCOMES, ClaimLetter, ClaimRecord
from .reconcile import Verdict
from .templating import page, render

_STATUS_LABELS = {
    CarrierStatus.DELIVERED: "Delivered",
    CarrierStatus.ATTEMPTED_DELIVERY: "Attempted delivery",
    CarrierStatus.OUT_FOR_DELIVERY: "Out for delivery",
}

_SOURCE_SENTENCES = {
    "bedrock": "A multimodal model on Amazon Bedrock read this off the page you gave it.",
    "pattern": "This app's own pattern rules read this off the text you pasted, because the model was not reachable.",
    "none": "Nothing could be read automatically, so these fields are blank.",
    "manual": "These fields are yours to fill in.",
}


def _options(pairs: list[tuple[str, str]], selected: str) -> str:
    return "".join(
        f'<option value="{html.escape(value)}"{" selected" if value == selected else ""}>'
        f"{html.escape(label)}</option>"
        for value, label in pairs
    )


def carrier_options(selected: str, blank_label: str | None = None) -> str:
    pairs = [] if blank_label is None else [("", blank_label)]
    pairs += [(c.code, c.display_name) for c in CARRIERS]
    pairs.append((UNKNOWN_CARRIER.code, "Not listed"))
    return _options(pairs, selected)


def status_options(selected: str) -> str:
    return _options([(s.value, _STATUS_LABELS[s]) for s in CarrierStatus], selected)


def verdict_options(selected: str) -> str:
    return _options([("", "Any verdict")] + [(v.value, STAMP_LABELS[v]) for v in Verdict], selected)


def nav(active: str, claim_id: str = "") -> str:
    links = [("/", "New claim", "new"), ("/claims", "Claim file", "claims")]
    if claim_id:
        links += [
            (f"/claims/{claim_id}/evidence", "Evidence pack", "evidence"),
            (f"/claims/{claim_id}/letter", "Letter", "letter"),
            (f"/claims/{claim_id}/pack", "Dispute pack", "pack"),
        ]
    items = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if key == active else ""}>{html.escape(label)}</a>'
        for href, label, key in links
    )
    return f'<nav class="tabs">{items}</nav>'


def intake_page(
    event_count: int, sample_count: int, claim_count: int, reader_up: bool, reader_detail: str
) -> str:
    if event_count == 0:
        demo_html = """
  <h2>There is no camera record here yet</h2>
  <p>
    Ring's event history starts at the moment consent is granted and there is no backfill,
    so a freshly connected app can only speak to deliveries from today onward. That is the
    app's most important limitation and it is also the first thing you see.
  </p>
  <p>
    This build has never run against a live Ring device, because Ring documents no
    simulator anywhere and a real run needs a US device on an active Protection plan.
    What it can do is replay six HMAC-signed webhook fixtures through the same
    signature-checking code a real webhook would hit, plus a recorded run of camera
    status samples, one of which contains a deliberate outage.
  </p>
  <form method="post" action="/demo/replay"><button type="submit">Load the demo camera record</button></form>
"""
    else:
        demo_html = """
  <h2>What is on record</h2>
  <p>
    A doorbell press and human motion around 14:11 on 20 September 2026, a vehicle passing
    at 09:05 that morning, human motion at 14:20 on the 18th, and a press with motion at
    11:02 on the 22nd. The camera also stopped answering between 10:00 and 11:15 on the
    20th, so a claim landing in that hour cannot reach a finding of absence at all.
  </p>
"""
    body = render(
        "intake.html",
        reader_state="up" if reader_up else "down",
        reader_status=(
            f"reachable ({reader_detail})" if reader_up
            else f"not reachable ({reader_detail}). Pasted text will be read by pattern rules instead."
        ),
        event_count=event_count,
        sample_count=sample_count,
        claim_count=claim_count,
        demo_html=demo_html,
    )
    return page("Start a claim", body, nav("new"), "Intake")


def _warnings_html(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
    return f'<div class="note refused"><strong>Noted while reading</strong><ul>{items}</ul></div>'


def review_page(reading, tz_offset: int, tz_label: str, device_name: str = "Front Door") -> str:
    carrier = reading.carrier or UNKNOWN_CARRIER
    local = reading.claimed_at.strftime("%Y-%m-%dT%H:%M") if reading.claimed_at else ""
    body = render(
        "review.html",
        source_sentence=_SOURCE_SENTENCES.get(reading.source, _SOURCE_SENTENCES["manual"])
        + (f" Model: {reading.model_id}, confidence {reading.confidence}." if reading.source == "bedrock" else ""),
        warnings_html=_warnings_html(reading.warnings),
        tracking_number=reading.tracking_number,
        carrier_options_html=carrier_options(carrier.code),
        status_options_html=status_options(reading.status.value if reading.status else ""),
        claimed_at_local=local,
        status_text=reading.status_text,
        device_name=device_name,
        notes="",
        tz_offset=tz_offset,
        tz_label=tz_label,
        reading_source=reading.source,
        reading_model=reading.model_id,
        reading_warnings=json.dumps(reading.warnings),
        window_note=f"For {carrier.display_name} that is {carrier.default_window_minutes} minutes each way. "
        f"{carrier.window_reason}",
    )
    return page("Check what was read", body, nav("new"), "Review")


def outcome_options(selected: str, blank_label: str | None = None) -> str:
    pairs = [] if blank_label is None else [("", blank_label)]
    return _options(pairs + list(OUTCOMES.items()), selected)


def claim_controls(record: ClaimRecord, notice_html: str = "") -> str:
    """The two things a claim needs after the pack exists: a correction, and an outcome.

    The correction form is the dangerous one and it is written to look it. It
    says what changing the window does before it offers the field, it asks for a
    reason, and it states that both findings will stay on the record. See
    app.correct_claim.
    """
    claim = record.claim
    local = claim.claimed_at.strftime("%Y-%m-%dT%H:%M")
    offset = int((claim.claimed_at.utcoffset() or dt.timedelta()).total_seconds() // 60)
    chase = ""
    if record.needs_chasing():
        chase = (
            f'<div class="note refused"><strong>Waiting {record.days_since_sent()} days</strong><br>'
            "This was sent and nothing has come back. Two weeks with no reply is the point at "
            "which a second letter is worth writing.</div>"
        )
    return f"""
  {notice_html}{chase}
  <h2>Where this claim has got to</h2>
  <form method="post" action="/claims/{record.claim_id}/outcome">
    <div class="row">
      <div class="field">
        <label for="outcome">Outcome</label>
        <select id="outcome" name="outcome">{outcome_options(record.outcome)}</select>
      </div>
      <div class="field" style="flex: 2 1 260px">
        <label for="note">What happened (searchable)</label>
        <input type="text" id="note" name="note" value="{html.escape(record.outcome_note, quote=True)}"
          placeholder="e.g. emailed claims@ on the 22nd, reference 4471">
      </div>
    </div>
    <button type="submit" class="secondary">Record the outcome</button>
  </form>

  <h2>Correct the time or the window</h2>
  <p>
    Changing either of these changes the hour the camera is checked against, and a
    wrong hour produces a finding about a time nothing was expected to happen. It
    is offered because somebody does mistype a delivery time, and a claim built on
    a typo should be fixable. Both findings stay on the record afterwards, with the
    reason you give, and the pack prints the window it actually used.
  </p>
  <form method="post" action="/claims/{record.claim_id}/correct">
    <div class="row">
      <div class="field">
        <label for="claimed_at">Time the tracking page gives</label>
        <input type="datetime-local" id="claimed_at" name="claimed_at" value="{local}" required>
      </div>
      <div class="field">
        <label for="window_minutes">Window either way, in minutes</label>
        <input type="text" id="window_minutes" name="window_minutes"
          value="{claim.window_minutes}" required>
      </div>
      <div class="field" style="flex: 2 1 260px">
        <label for="reason">Why you are changing it</label>
        <input type="text" id="reason" name="reason"
          placeholder="e.g. I read the tracking page as 2:11, it says 12:11">
      </div>
    </div>
    <input type="hidden" name="tz_offset" value="{offset}">
    <button type="submit" class="secondary">Recompute and keep both</button>
  </form>
"""


def _claim_row(record: ClaimRecord) -> str:
    claim = record.claim
    verdict = record.result.verdict
    return (
        "<tr>"
        # `nowrap` on the two dates: a date printed as 2026- / 09-23 over two
        # lines reads as a rendering accident on a page whose whole claim is
        # that it was produced carefully. `break-anywhere` on the tracking
        # number, the one cell that holds a 22-digit unbreakable token and the
        # one that was forcing this table wider than the paper it sits on.
        f'<td class="nowrap" data-label="Filed">{record.created_at.strftime("%Y-%m-%d")}</td>'
        f'<td class="break-anywhere" data-label="Tracking">'
        f'<a href="/claims/{record.claim_id}/evidence">'
        f"{html.escape(claim.tracking_number)}</a></td>"
        f'<td data-label="Carrier">{html.escape(claim.carrier_name)}</td>'
        f'<td class="nowrap" data-label="Claimed">'
        f'{claim.claimed_at.strftime("%Y-%m-%d %H:%M")}</td>'
        f'<td data-label="Verdict"><span class="stamp-chip {verdict.value}">'
        f"{html.escape(STAMP_LABELS[verdict])}</span></td>"
        f'<td data-label="Outcome">{html.escape(record.outcome_label)}'
        + ('<br><span class="chase">no reply yet</span>' if record.needs_chasing() else "")
        + "</td>"
        f'<td data-label="Note">{html.escape(record.notes)}</td>'
        "</tr>"
    )


def claims_index_page(
    records: list[ClaimRecord],
    query: str,
    verdict: str,
    carrier: str,
    outcome: str,
    tally: str,
    chasing: list[ClaimRecord] | None = None,
) -> str:
    if records:
        rows = "".join(_claim_row(r) for r in records)
        results = (
            '<table class="log"><thead><tr><th scope="col">Filed</th><th scope="col">Tracking</th>'
            '<th scope="col">Carrier</th><th scope="col">Carrier claimed</th>'
            '<th scope="col">Verdict</th><th scope="col">Outcome</th>'
            '<th scope="col">Your note</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>"
        )
        heading = f"{len(records)} claim{'s' if len(records) != 1 else ''}"
    elif query or verdict or carrier:
        results = '<p class="empty-set">No claim on file matches that search.</p>'
        heading = "No matches"
    else:
        results = (
            '<p class="empty-set">No claims on file yet. Start one from the intake screen.</p>'
        )
        heading = "Nothing on file"
    chasing = chasing or []
    chase_html = ""
    if chasing:
        items = "".join(
            f'<li><a href="/claims/{r.claim_id}/evidence">{html.escape(r.claim.tracking_number)}</a> '
            f"({html.escape(r.claim.carrier_name)}), sent {r.days_since_sent()} days ago</li>"
            for r in chasing
        )
        chase_html = (
            '<div class="note refused"><strong>Worth chasing</strong>'
            f"<ul>{items}</ul>"
            "Two weeks with no reply is the point at which a second letter is worth writing. "
            "The research behind this app found that a third of people with a delivery problem "
            "take no action at all, and a claim nobody followed up ends the same way as a claim "
            "nobody made.</div>"
        )
    body = render(
        "claims_index.html",
        chase_html=chase_html,
        query=query,
        verdict_options_html=verdict_options(verdict),
        carrier_options_html=carrier_options(carrier, blank_label="Any carrier"),
        outcome_options_html=outcome_options(outcome, blank_label="Any outcome"),
        result_heading=heading,
        results_html=results,
        tally=tally,
    )
    return page("Claim file", body, nav("claims"), "History and search")


def _revisions_html(letters: list[ClaimLetter]) -> str:
    if not letters:
        return '<p class="empty-set">No revisions yet.</p>'
    rows = "".join(
        "<tr>"
        f'<td data-label="Revision">{letter.revision}</td>'
        f'<td data-label="Written">{letter.created_at.strftime("%Y-%m-%d %H:%M UTC")}</td>'
        f'<td data-label="Source">{html.escape(letter.source)}</td>'
        f'<td data-label="Language check">{html.escape(letter.guard_note or "passed")}</td>'
        "</tr>"
        for letter in letters
    )
    return (
        '<table class="log"><thead><tr><th scope="col">Rev</th><th scope="col">Written</th>'
        '<th scope="col">Written by</th><th scope="col">Language check</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def letter_page(record: ClaimRecord, letter: ClaimLetter, notice_html: str = "") -> str:
    body = render(
        "letter.html",
        claim_id=record.claim_id,
        notice_html=notice_html or (
            f'<div class="note refused"><strong>Language check</strong><br>{html.escape(letter.guard_note)}</div>'
            if letter.guard_note
            else ""
        ),
        subject=letter.subject,
        body=letter.body,
        revision=letter.revision,
        source_label={"bedrock": "drafted on Bedrock", "template": "standard wording", "user": "your wording"}.get(
            letter.source, letter.source
        ),
        revisions_html=_revisions_html(record.letters),
    )
    return page(f"Letter for claim {record.claim_id}", body, nav("letter", record.claim_id), "Covering letter")


def refusal_notice(exc: guard.AccusatoryLanguage) -> str:
    return (
        '<div class="note refused"><strong>That wording was not saved</strong><br>'
        f"{html.escape(guard.findings_summary(exc.findings))}</div>"
    )


def pack_page(record: ClaimRecord, manifest) -> str:
    rows = "".join(
        "<tr>"
        f'<td data-label="File">{html.escape(item.name)}</td>'
        f'<td data-label="Bytes">{item.size}</td>'
        # Grouped in eights, the same as the filed record. A digest is
        # compared out loud, by two people on a phone, and a 64-character run
        # that wraps wherever the column happens to end cannot be read that
        # way. `grouped` is the one formatter; using it in one place and not
        # the other is how two renderings of one digest stop matching.
        f'<td data-label="SHA-256"><code class="hash">{html.escape(grouped(item.digest))}</code></td>'
        f'<td data-label="What it is">{html.escape(item.description)}</td>'
        "</tr>"
        for item in manifest.items
    )
    files_html = (
        '<table class="log"><thead><tr><th scope="col">File</th><th scope="col">Bytes</th>'
        '<th scope="col">SHA-256</th><th scope="col">What it is</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )
    body = render(
        "pack.html",
        claim_id=record.claim_id,
        files_html=files_html,
        pack_digest=grouped(manifest.pack_digest),
        # Through the one formatter, so this line carries the numeric offset
        # every other time in the product carries. A zone abbreviation without
        # an offset is ambiguous, and one page in a product where every other
        # page is exact reads as the page somebody forgot.
        built_at=ts.canonical(manifest.built_at, seconds=True),
    )
    return page(f"Dispute pack {record.claim_id}", body, nav("pack", record.claim_id), "Files and checksums")


def verify_page(report) -> str:
    body = render(
        "verify.html",
        stamp_class="consistent_with_camera" if report.ok else "not_consistent_with_camera",
        stamp_label="Matches its manifest" if report.ok else "Does not match its manifest",
        message=report.message,
        claim_id=report.claim_id or "not stated",
        checked=report.checked,
        mismatched=", ".join(report.mismatched) or "none",
        missing=", ".join(report.missing) or "none",
        unlisted=", ".join(report.unlisted) or "none",
        digest_state="matches its file list" if report.pack_digest_ok else "does not match its file list",
    )
    return page("Pack check", body, nav("claims"), "Manifest verification")


def local_to_utc(value: str, tz_offset_minutes: int) -> dt.datetime:
    """A browser's ``datetime-local`` value plus the browser's offset."""
    naive = dt.datetime.fromisoformat(value)
    return naive.replace(tzinfo=dt.timezone(dt.timedelta(minutes=tz_offset_minutes)))


# ---- when something is refused --------------------------------------------

# One sentence per status, saying what the reader can do next. "Not Found" on
# bare white in Times is the one screen in this app with no design on it, and
# it was reachable from the first button on the first screen: an empty submit
# of READ THE PAGE dropped out of the parchment entirely into
# {"detail":"Paste the tracking page or upload a screenshot of it"}.
_WHAT_NEXT = {
    400: "Go back, change what is named above, and send it again.",
    401: "The signature on that request did not verify against this server's secret.",
    404: "Check the link. A claim id is the one printed at the top of its evidence pack.",
    405: "That address does not take this kind of request.",
    500: "Nothing was written. The detail above is what the server has to say about it.",
}

_HEADINGS = {
    400: "That could not be filed",
    401: "That was not accepted",
    404: "There is nothing filed under that",
    405: "That address does not answer that way",
}


def error_page(status: int, detail: str, path: str = "") -> str:
    """The parchment version of an HTTPException."""
    heading = _HEADINGS.get(status, "Something went wrong")
    next_step = _WHAT_NEXT.get(status, _WHAT_NEXT[500])
    # Starlette's own 404 detail is the two words "Not Found", which tells a
    # reader nothing they did not already know. Name the address instead.
    if status == 404 and detail in ("Not Found", "Not found") and path:
        detail = f"Nothing answers at {path} on this server."
    body = (
        f'<h2>{html.escape(heading)}</h2>'
        f'<p class="lede">{html.escape(detail)}</p>'
        f'<p class="note">{html.escape(next_step)}</p>'
        '<p><a href="/">Start a claim</a> &middot; <a href="/claims">Claim file</a></p>'
    )
    return page(heading, body, nav(""), f"Nothing was filed ({status})")
