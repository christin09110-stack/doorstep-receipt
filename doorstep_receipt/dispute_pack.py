"""The dispute pack: the filed record, its exhibits, and a manifest you can run.

A claims desk does not read a web page. It receives an attachment, forwards it,
and somebody three steps away opens it. This builds that attachment.

What the pack contains, and what depends on what:

  doorstep-delivery-record.html   the filed record (filed_record.py), stylesheet
                                  inlined so the pack survives being split up
  E1 camera-event-log.csv         the events inside the checked window
  E2 evidence.json                the same record as structured data
  E3 claim-letter.txt             the covering letter, when one exists
  E4 camera-status-samples.csv    the coverage samples the findings rest on
  MANIFEST.txt                    the human copy, with the instruction
  manifest.sha256                 the machine copy, GNU coreutils format

The record carries the exhibit digests, so it cannot carry its own. It is hashed
after it is rendered and added to ``manifest.sha256``, which is written last.
The record says so on its own face rather than leaving a reader to notice.

The manifest lives in ``manifest.py``, its printable form in
``manifest_text.py``, the exhibits in ``pack_files.py``, and checking somebody
else's pack in ``pack_verify.py``.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import zipfile

from . import guard
from .manifest import (
    MANIFEST_JSON,
    MANIFEST_NAME,
    MANIFEST_SHA,
    RECORD_NAME,
    PackItem,
    PackManifest,
    VerificationReport,
    compute_pack_digest,
    sha256_bytes,
)
from .manifest_text import manifest_text
from .pack_files import event_log_csv, gaps_for, status_csv
from .pack_verify import verify_pack

__all__ = [
    "MANIFEST_NAME",
    "MANIFEST_SHA",
    "PackManifest",
    "VerificationReport",
    "build_pack",
    "event_log_csv",
    "verify_pack",
]


def _letter_origin(letter) -> str:
    """How the letter came to exist, in words an adjuster reads.

    `letter.source` is an internal enum. Printing it put "written by bedrock"
    and "written by user" into the exhibit list of a filed document, which is
    both a second spelling of a name the record gives in full elsewhere, and a
    name drawn from how the system is built rather than from anything the
    reader recognises.
    """
    return {
        "bedrock": "Drafted by software on Amazon Bedrock from the fields in this record, "
                   "and accepted unchanged.",
        "user": "Drafted by software and then edited by the account holder before it was kept.",
        "template": "Written from this app's fixed wording, with this record's own values "
                    "substituted. No model wrote it.",
    }.get(letter.source, "Origin not recorded.")


def build_pack(record, evidence_json: dict, events, version: str = "0.2.0") -> tuple[bytes, PackManifest]:
    """Assemble the zip and its manifest. Returns (zip bytes, manifest)."""
    from .filed_record import build as build_record

    built_at = dt.datetime.now(dt.timezone.utc)
    letter = record.latest_letter

    files: list[tuple[str, bytes, str, str, str]] = [
        ("camera-event-log.csv", event_log_csv(record),
         "Every event in this app's record inside the checked window.", "", "text/csv"),
        ("evidence.json", json.dumps(evidence_json, indent=2, sort_keys=True).encode("utf-8"),
         "The same record as structured data.", "", "application/json"),
    ]
    if letter is not None:
        files.append(
            ("claim-letter.txt", f"Subject: {letter.subject}\n\n{letter.body}\n".encode("utf-8"),
             f"The covering letter, revision {letter.revision}. {_letter_origin(letter)}", "", "text/plain")
        )
    files.append(
        ("camera-status-samples.csv", status_csv(record, events),
         "The camera status samples the coverage findings rest on.", "", "text/csv")
    )

    items = [
        PackItem(f"E{n}", name, len(data), sha256_bytes(data), description, derived, media)
        for n, (name, data, description, derived, media) in enumerate(files, start=1)
    ]
    manifest = PackManifest(
        claim_id=record.claim_id,
        tracking_number=record.claim.tracking_number,
        carrier_name=record.claim.carrier_name,
        built_at=built_at,
        items=items,
        gaps=gaps_for(record),
    )
    manifest.pack_digest = compute_pack_digest(items)

    exhibit_map = {"events": "E1", "json": "E2", "letter": "E3" if letter else "", "status": items[-1].exhibit_id}
    record_html = build_record(record, manifest, version=version, exhibits=exhibit_map)
    record_bytes = record_html.encode("utf-8")

    # The record carries the exhibit digests, so it cannot carry its own. It is
    # hashed after rendering and added to the machine manifest, which the record
    # says on its face is written last.
    record_item = PackItem(
        "R1", RECORD_NAME, len(record_bytes), sha256_bytes(record_bytes),
        "The filed record itself, stylesheet inlined.", "", "text/html",
    )
    all_items = [record_item] + items

    text = manifest_text(manifest, record_item, version)
    sha_file = "".join(f"{i.digest}  {i.name}\n" for i in all_items)

    # The last pass, over everything that leaves in the envelope rather than
    # only over the screen pack. This is the artefact that reaches the carrier
    # and the ombudsman, and the letter inside it is the one file here a model
    # wrote end to end. `build_record` is checked as it renders; the text
    # members are checked here. Every string was guarded on the way in, so
    # this should never fire, which is exactly why it is worth having.
    guard.assert_clean(text, where="dispute pack manifest")
    for name, data, description, *_ in files:
        if name.endswith((".txt", ".csv")):
            guard.assert_clean(data.decode("utf-8", "replace"), where=f"dispute pack: {name}")
        guard.assert_clean(description, where=f"dispute pack file list: {name}")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(RECORD_NAME, record_bytes)
        for name, data, *_ in files:
            archive.writestr(name, data)
        archive.writestr(MANIFEST_NAME, text)
        archive.writestr(MANIFEST_SHA, sha_file)
        archive.writestr(MANIFEST_JSON, json.dumps(manifest.to_json(), indent=2))
    return buffer.getvalue(), manifest
