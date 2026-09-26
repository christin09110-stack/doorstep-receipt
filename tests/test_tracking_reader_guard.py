"""Every string the reading tool returns goes through the guard.

The defect this pins: two of the tool call's fields were guarded and four were
not, and one of the four, ``printed_when``, is rendered on the filed record
inside ``class="verbatim"``. That class is the strongest presentational claim
this app makes — it tells the reader these are the carrier's own printed words.
A field presented as quoted that a model wrote freely is the worst combination
available, because the frame around it argues for the content inside it.

The guard is a quote-or-refuse design, and such a design only holds if every
field is covered by it. One unconstrained string undoes the whole argument.
"""

from __future__ import annotations

import pytest

from doorstep_receipt import guard
from doorstep_receipt.bedrock import StubRunner
from doorstep_receipt.tracking_reader import read_tracking_page

ACCUSATION = "the driver lied about leaving it at the door"


def _reply(**overrides) -> dict:
    fields = {
        "is_tracking_page": True,
        "confidence": "high",
        "tracking_number": "1Z999AA10123456784",
        "carrier_name": "UPS",
        "status_text": "Delivered",
        "location_note": "Left at front door",
        "reference": "ORD-55120",
        "printed_when": "Friday, September 20, 2026 at 2:11 P.M.",
        "delivered_date": "2026-09-20",
        "delivered_time": "14:11",
        "unreadable": [],
    }
    fields.update(overrides)
    return {"tool_input": fields, "stop_reason": "tool_use"}


def _read(**overrides):
    runner = StubRunner([_reply(**overrides)], model_id="stub-model")
    return read_tracking_page(text="tracking page", runner=runner)


def test_a_clean_page_reads_every_field_through_unchanged():
    reading = _read()

    assert reading.tracking_number == "1Z999AA10123456784"
    assert reading.claimed_at_text == "Friday, September 20, 2026 at 2:11 P.M."
    assert reading.reference == "ORD-55120"
    assert reading.guard_findings == []


@pytest.mark.parametrize(
    "field",
    ["printed_when", "carrier_name", "reference", "status_text", "location_note"],
)
def test_an_accusation_in_any_field_of_the_tool_call_is_refused(field):
    reading = _read(**{field: ACCUSATION})

    assert reading.guard_findings, f"{field} reached the record unguarded"
    assert not any(
        "lied" in str(value)
        for value in (
            reading.claimed_at_text,
            reading.carrier_name_printed,
            reading.reference,
            reading.status_text,
            reading.location_note,
        )
    )
    # And the refusal is visible rather than a silent substitution.
    assert any("not reproduced here" in w for w in reading.warnings)


def test_the_verbatim_field_is_the_one_that_most_needs_this():
    """``printed_when`` renders inside class="verbatim" on the filed record."""
    reading = _read(printed_when=f"Delivered 2:11 PM — {ACCUSATION}")

    assert reading.claimed_at_text == ""
    assert reading.guard_findings


def test_an_accusation_in_the_unreadable_array_never_reaches_a_warning():
    """A model array of strings interpolated into a sentence a person reads
    and the store persists. Same call, same guard."""
    reading = _read(unreadable=[ACCUSATION, "postcode"])

    assert any("postcode on that page was not legible" in w for w in reading.warnings)
    assert not any("lied" in w for w in reading.warnings)


def test_the_tracking_number_cannot_carry_a_sentence_at_all():
    """Not guarded, and does not need to be: it is stripped to an
    alphanumeric run, which leaves nowhere for prose to sit."""
    reading = _read(tracking_number=f'1Z999 " onload=x {ACCUSATION}')

    assert reading.tracking_number.isalnum()
    assert " " not in reading.tracking_number
    assert '"' not in reading.tracking_number


def test_the_guard_still_has_no_opinion_about_a_normal_status_line():
    reading = _read(status_text="Delivered, left with a neighbour at number 12")

    assert reading.guard_findings == []
    assert "neighbour" in reading.status_text
    assert guard.scan(reading.status_text) == []
