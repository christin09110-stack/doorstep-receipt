"""A timezone label the model read off a photograph, and where it ended up.

Reproduced by running it, not by reading the code. `timezone_printed` is a free
text field on the tracking-page reading tool: a multimodal model fills it in
from a screenshot somebody took of a carrier's web page, so its contents come
from outside this app entirely. It becomes `claim.timezone_label`, and
`evidence._event_table_html` interpolated the formatted time -- label included
-- straight into the page with no escaping. This came out of `render_html`
with the tag intact:

    <td class="nowrap" ...>2026-09-20 14:12:00 UTC" onfocus=alert(1) x="<img
    src=x onerror=alert(1)> (UTC+01:00)</td>

Two fixes, and the order matters. `timestamps.safe_label` refuses a label that
is not shaped like a label, which is the argument; `html.escape` at the call
site is the last line, for the next value somebody forgets. GUARD-STANDARD.md
§4: escaping is the last line, never the argument.
"""

from __future__ import annotations

import datetime as dt

import pytest

from doorstep_receipt import carrier, evidence, reconcile
from doorstep_receipt import timestamps as ts
from doorstep_receipt.ring_events import RingEvent

# One string, pushed at every destination, per GUARD-STANDARD.md §4.
HOSTILE = 'UTC" onfocus=alert(1) x="<img src=x onerror=alert(1)>'

# A fixed-offset zone, which is what a real claim carries: the tracking page
# prints a wall clock and the browser supplies the offset. `tzname()` returns
# "UTC+01:00" for one of these, which is the offset again and not a label, so
# the supplied label is what gets rendered. With `dt.timezone.utc` the label is
# never reached at all, and a test written with it proves nothing.
TZ = dt.timezone(dt.timedelta(minutes=60))


def _page(label: str) -> str:
    claim = carrier.CarrierClaim(
        tracking_number="1Z999AA10123456784",
        carrier_name="UPS",
        status=carrier.CarrierStatus.DELIVERED,
        claimed_at=dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ),
        window_minutes=30,
        timezone_label=label,
    )
    event = RingEvent(
        event_id="e1",
        event_type="motion",
        sub_type="human",
        timestamp=dt.datetime(2026, 9, 20, 14, 12, tzinfo=TZ),
        device_id="d1",
    )
    return evidence.render_html(reconcile.reconcile(claim, [event]), "Front door", [], claim_id="c1")


def test_a_hostile_timezone_label_does_not_reach_the_evidence_pack():
    page = _page(HOSTILE)
    assert HOSTILE not in page
    assert "<img src=x" not in page
    assert "onerror=" not in page
    assert "onfocus=" not in page


def test_the_event_row_is_actually_on_the_page_that_was_searched():
    """Non-vacuity. "the string is absent" is satisfied by an empty page, so the
    row that used to carry it has to be shown to be there."""
    page = _page("Europe/London")
    assert "2026-09-20 14:12:00" in page
    assert "Europe/London" in page


@pytest.mark.parametrize(
    "label",
    [
        HOSTILE,
        '"><script>alert(1)</script>',
        "UTC' onmouseover='alert(1)",
        "A" * 200,
        "Europe/London​<img src=x>",
        "\u001b[31mUTC",
        "",
        "   ",
    ],
)
def test_a_label_that_is_not_a_label_is_refused_rather_than_repaired(label):
    assert ts.safe_label(label) == "UTC"


@pytest.mark.parametrize(
    "label",
    ["UTC", "BST", "GMT", "Europe/London", "America/New_York", "UTC+1", "Asia/Ho_Chi_Minh"],
)
def test_a_real_timezone_label_still_prints(label):
    """The paired false positive. A guard that refused every label would make
    every time on the document read UTC, which is a different wrong answer."""
    assert ts.safe_label(label) == label
    assert label in _page(label)
