import datetime as dt
import re

from doorstep_receipt import guard
from doorstep_receipt.guard_document import visible_text

from doorstep_receipt.carrier import CarrierClaim, CarrierStatus
from doorstep_receipt.coverage import sample
from doorstep_receipt.evidence import Attachment, render_html, to_dict
from doorstep_receipt.reconcile import reconcile
from doorstep_receipt.ring_client import RingEvent

TZ = dt.timezone.utc


def _consistent_result():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = CarrierClaim("1Z999", "UPS", CarrierStatus.DELIVERED, claimed_at)
    events = [RingEvent("evt-1", "motion", "human", claimed_at + dt.timedelta(minutes=2), "dev-1")]
    return reconcile(claim, events + _covering_samples(claim))


def _covering_samples(claim):
    start, end = claim.window()
    samples, cursor = [], start - dt.timedelta(minutes=5)
    while cursor <= end + dt.timedelta(minutes=5):
        samples.append(sample(cursor))
        cursor += dt.timedelta(minutes=15)
    return samples


def _disputed_result():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = CarrierClaim("1Z999", "UPS", CarrierStatus.DELIVERED, claimed_at)
    return reconcile(claim, _covering_samples(claim))


def test_render_html_includes_tracking_number_and_verdict_stamp():
    result = _consistent_result()
    html = render_html(result, "Front Door", attachments=[])
    assert "1Z999" in html
    assert "Consistent with camera" in html
    assert "#2f4a34" in html  # forest-green stamp colour for a consistent verdict


def test_render_html_uses_seal_red_for_not_consistent():
    result = _disputed_result()
    html = render_html(result, "Front Door", attachments=[])
    assert "Not consistent with camera" in html
    assert "#7a2323" in html


def test_render_html_shows_empty_set_explicitly_not_hidden():
    result = _disputed_result()
    html = render_html(result, "Front Door", attachments=[])
    assert "No events were recorded in this window." in html


def test_render_html_lists_event_log_rows():
    result = _consistent_result()
    html = render_html(result, "Front Door", attachments=[])
    assert "motion.human" in html
    assert "14:13" in html


def test_render_html_includes_no_accusation_language():
    """The original form of this test did a naive substring search, which is how
    it once failed on the word "supplied" (it contains "lied"). Word boundaries
    now, and the full guard underneath it, so the test checks the rule rather
    than the letters."""
    result = _disputed_result()
    html = render_html(result, "Front Door", attachments=[])
    lowered = html.lower()
    for word in ("lied", "stole", "fraud", "did not come", "never came"):
        assert not re.search(rf"\b{word}\b", lowered), word
    assert guard.is_clean(visible_text(html))


def test_to_dict_round_trips_key_fields():
    result = _consistent_result()
    attachments = [Attachment(label="Snapshot", reference="snapshot://x", available=True)]
    data = to_dict(result, "Front Door", attachments)
    assert data["tracking_number"] == "1Z999"
    assert data["verdict"] == "consistent_with_camera"
    assert len(data["events"]) == 1
    assert data["attachments"][0]["label"] == "Snapshot"


def test_render_html_unavailable_attachment_says_so():
    result = _consistent_result()
    html = render_html(
        result,
        "Front Door",
        attachments=[Attachment(label="Video clip", reference="needs a plan", available=False)],
    )
    assert "not available" in html
