"""A tracking number and a carrier name that are different carriers.

`carrier_match.py` argues, at length and correctly, that the right answer to an
uncertain carrier is to decline and ask, "because a wrong carrier sets a wrong
checking window, and a wrong window produces a confident finding about the
wrong hour". The one case it did not check was the loudest one: a number that
identifies one carrier next to a name the user typed for another.

`carrier.py` let the number win and kept the name for display, so the README's
own second example filed a **Royal Mail** claim with **USPS's** 30-minute
window and printed USPS's sentence about walking routes underneath it to
justify the width. After a correction it went further and called 30 minutes
"the width this app uses for Royal Mail". Royal Mail's is 25.
"""

import datetime as dt
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doorstep_receipt.app import app
from doorstep_receipt.carrier import CarrierMismatch, ManualEntryAdapter
from doorstep_receipt.carriers import resolve

USPS_NUMBER = "9400111899223197428490"
ROYAL_MAIL_NUMBER = "RQ123456785GB"
WHEN = dt.datetime(2026, 9, 20, 9, 0, tzinfo=dt.timezone.utc)


def _claim(number, name, **kw):
    return ManualEntryAdapter().fetch_claim(
        tracking_number=number, carrier_name=name, status="delivered", claimed_at=WHEN, **kw
    )


def test_a_usps_number_called_royal_mail_is_refused():
    with pytest.raises(CarrierMismatch) as caught:
        _claim(USPS_NUMBER, "Royal Mail")

    message = str(caught.value)
    assert "Royal Mail" in message
    assert "USPS" in message
    assert "25 minutes to 30" in message


def test_the_refusal_is_a_value_error_so_the_routes_already_turn_it_into_a_400():
    assert issubclass(CarrierMismatch, ValueError)


def test_the_number_still_wins_when_no_carrier_was_named():
    claim = _claim(USPS_NUMBER, "")

    assert claim.carrier_code == "usps"
    assert claim.window_minutes == 30


def test_a_name_this_app_does_not_know_does_not_count_as_a_disagreement():
    claim = _claim(USPS_NUMBER, "Hermes")

    assert claim.carrier_code == "usps"


def test_the_name_still_decides_when_the_number_shape_is_unknown():
    claim = _claim("NOT-A-TRACKING-SHAPE-1", "Royal Mail")

    assert claim.carrier_code == "royal-mail"
    assert claim.window_minutes == 25


def test_agreement_is_not_a_disagreement():
    claim = _claim(ROYAL_MAIL_NUMBER, "Royal Mail")

    assert claim.carrier_code == "royal-mail"
    assert claim.window_minutes == 25
    assert "posties scan on the doorstep" in resolve(claim.carrier_code).window_reason


def test_the_api_refuses_the_mismatch_rather_than_filing_it():
    client = TestClient(app)

    response = client.post(
        "/claims",
        json={
            "tracking_number": USPS_NUMBER,
            "carrier_name": "Royal Mail",
            "status": "delivered",
            "claimed_at": "2026-09-20T09:00:00Z",
        },
    )

    assert response.status_code == 400
    assert "USPS" in response.json()["detail"]


def test_the_readme_second_example_produces_a_royal_mail_claim():
    """It is the path a judge takes, so it has to be one that works."""
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    block = readme.split('"carrier_name": "Royal Mail"')[0]
    number = re.findall(r'"tracking_number": "([^"]+)"', block)[-1]

    claim = _claim(number, "Royal Mail")
    assert claim.carrier_code == "royal-mail"


def test_the_pack_names_the_carrier_the_width_came_from():
    from doorstep_receipt import evidence

    source = Path(evidence.__file__).read_text()
    adjusted = source[source.index("adjusted = ("):source.index("return render(")]

    assert "width_carrier" in adjusted
    assert "claim.carrier_name" not in adjusted
