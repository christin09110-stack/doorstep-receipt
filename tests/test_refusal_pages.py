"""Refusals that stay on the paper, and refusals a person can act on.

Three defects, one family: the app is careful about every sentence it prints
except the ones it prints when something goes wrong.

- An empty submit of READ THE PAGE — the first button on the first screen —
  dropped out of the parchment into `{"detail":"Paste the tracking page or
  upload a screenshot of it"}` on bare white in Times. So did every 404.
- `POST /claims` answered `Invalid isoformat string: 'nope'` and `'teleported'
  is not a valid CarrierStatus`: correct, and useless to whoever typed it.
"""

from fastapi.testclient import TestClient

from doorstep_receipt.app import app

HTML = {"accept": "text/html"}
GOOD = {
    "tracking_number": "1Z999AA10123456784",
    "carrier_name": "UPS",
    "status": "delivered",
    "claimed_at": "2026-09-20T14:11:00Z",
}


def _client():
    return TestClient(app)


def test_an_unknown_page_stays_on_the_paper():
    response = _client().get("/nope-not-a-page", headers=HTML)

    assert response.status_code == 404
    assert 'class="sheet"' in response.text
    assert "Doorstep Receipt" in response.text
    assert "There is nothing filed under that" in response.text


def test_the_404_names_the_address_rather_than_saying_not_found():
    response = _client().get("/nope-not-a-page", headers=HTML)

    assert "/nope-not-a-page" in response.text


def test_an_unknown_claim_stays_on_the_paper_too():
    response = _client().get("/claims/nope-123/evidence", headers=HTML)

    assert response.status_code == 404
    assert 'class="sheet"' in response.text
    assert "Claim not found" in response.text


def test_an_empty_read_submit_stays_on_the_paper():
    response = _client().post("/read", data={"pasted": ""}, headers=HTML)

    assert response.status_code == 400
    assert 'class="sheet"' in response.text
    assert "Paste the tracking page" in response.text
    assert not response.text.lstrip().startswith("{")


def test_a_json_client_still_gets_json():
    response = _client().get("/claims/nope-123/evidence", headers={"accept": "application/json"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Claim not found"}


def test_a_curl_with_no_accept_header_still_gets_json():
    response = _client().get("/claims/nope-123/evidence")

    assert response.status_code == 404
    assert response.json()["detail"] == "Claim not found"


def test_an_unreadable_date_says_what_a_readable_one_looks_like():
    response = _client().post("/claims", json={**GOOD, "claimed_at": "nope"})

    detail = response.json()["detail"]
    assert response.status_code == 400
    assert "isoformat" not in detail
    assert "2026-09-20T14:11:00Z" in detail


def test_an_unknown_status_lists_the_ones_that_exist():
    response = _client().post("/claims", json={**GOOD, "status": "teleported"})

    detail = response.json()["detail"]
    assert "not a valid CarrierStatus" not in detail
    assert "delivered" in detail
    assert "attempted_delivery" in detail
    assert "out_for_delivery" in detail


def test_a_missing_field_is_named_along_with_the_ones_that_are_needed():
    body = {k: v for k, v in GOOD.items() if k != "claimed_at"}

    detail = _client().post("/claims", json=body).json()["detail"]

    assert "claimed_at" in detail
    assert "tracking_number" in detail
    assert detail != "'claimed_at'"
