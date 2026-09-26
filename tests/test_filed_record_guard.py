"""The document-level check covers what leaves in the envelope.

``assert_document_clean`` scans the assembled page rather than its inputs. It
was wired to the evidence pack only — the parchment screen the claimant looks
at — and not to the filed record, which is the rendering that goes into the zip
and on to the carrier and the ombudsman. The screen was guarded and the
attachment was not, which is the wrong way round.

Every string is guarded where it enters a record, so none of this should ever
fire. That is exactly the reason to test that the wiring is live: "should never
fire" is how things ship broken, and a guard nobody has seen fire is a guard
nobody knows is connected.
"""

from __future__ import annotations

import datetime as dt

import pytest

from doorstep_receipt import dispute_pack, filed_record
from doorstep_receipt.carrier import CarrierClaim, CarrierStatus
from doorstep_receipt.coverage import sample
from doorstep_receipt.guard_findings import AccusatoryLanguage
from doorstep_receipt.reconcile import reconcile
from doorstep_receipt.records import ClaimLetter, ClaimRecord
from doorstep_receipt.ring_client import RingEvent

TZ = dt.timezone.utc


def _record() -> ClaimRecord:
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = CarrierClaim("1Z999AA10123456784", "UPS", CarrierStatus.DELIVERED, claimed_at)
    events = [RingEvent("evt-1", "motion", "human", claimed_at + dt.timedelta(minutes=2), "dev-1")]
    start, end = claim.window()
    samples, cursor = [], start - dt.timedelta(minutes=5)
    while cursor <= end + dt.timedelta(minutes=5):
        samples.append(sample(cursor))
        cursor += dt.timedelta(minutes=15)
    return ClaimRecord(claim_id="testrec1", result=reconcile(claim, events + samples),
                       device_name="Front Door")


def _pack(record):
    return dispute_pack.build_pack(record, {"claim_id": record.claim_id}, [])


def test_a_clean_record_renders_and_packs():
    record = _record()
    zip_bytes, manifest = _pack(record)

    assert zip_bytes[:2] == b"PK"
    assert manifest.pack_digest


def test_the_filed_record_is_document_checked_not_only_the_evidence_pack():
    """Doctored so the check has something to catch, which is the only way to
    show the call site is real rather than imported and forgotten."""
    record = _record()
    record.device_name = "Front Door, where the driver lied about delivering it"

    with pytest.raises(AccusatoryLanguage) as excinfo:
        filed_record.build(record, _pack(_record())[1])

    assert "filed record" in str(excinfo.value)


def test_the_dispute_pack_is_checked_before_it_is_written():
    """claim-letter.txt is the one file in the pack a model writes end to end,
    and the pack is the artefact that reaches the carrier and the ombudsman."""
    record = _record()
    record.letters.append(
        ClaimLetter(body="Your driver lied about delivering it.", subject="Claim",
                    source="bedrock")
    )

    with pytest.raises(AccusatoryLanguage) as excinfo:
        _pack(record)

    assert "dispute pack" in str(excinfo.value)


def test_the_refusal_names_the_rule_and_does_not_reprint_the_phrase():
    """A rejection is model output with a frame around it, not metadata. What
    reaches a page is the rule that fired, never the text that fired it."""
    record = _record()
    record.device_name = "Front Door, where the driver lied about delivering it"

    with pytest.raises(AccusatoryLanguage) as excinfo:
        filed_record.build(record, _pack(_record())[1])

    shown = "; ".join(f.explain() for f in excinfo.value.findings)
    assert "lied" not in shown
    assert "states what a person did or did not do" in shown
    # And still legible to whoever has to debug it.
    assert "lied" in "; ".join(f.detail() for f in excinfo.value.findings)
