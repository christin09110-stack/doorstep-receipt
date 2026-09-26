"""Tests for the Ring client, mocked at the HTTP boundary: never against a live
Ring account (none is available). Response
bodies are shaped exactly like the documented JSON:API envelope."""

import datetime as dt
from unittest.mock import MagicMock

import pytest

from doorstep_receipt.ring_client import ClipNotAvailable, RingAPIError, RingClient, parse_timestamp


def _mock_response(status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


def test_list_devices_parses_data_array():
    session = MagicMock()
    session.get.return_value = _mock_response(
        json_body={"data": [{"id": "dev-1", "type": "device", "attributes": {"name": "Front Door"}}]}
    )
    client = RingClient(token="tok", session=session)

    devices = client.list_devices()

    assert devices == [{"id": "dev-1", "type": "device", "attributes": {"name": "Front Door"}}]
    session.get.assert_called_once()
    called_url = session.get.call_args.args[0]
    assert called_url == "https://api.amazonvision.com/v1/devices"
    headers = session.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok"


def test_get_event_history_parses_events_with_dotted_subtype():
    session = MagicMock()
    session.get.return_value = _mock_response(
        json_body={
            "data": [
                {
                    "id": "evt-1",
                    "type": "event",
                    "attributes": {"event_type": "motion.human", "start": "2026-09-20T14:11:00Z"},
                }
            ]
        }
    )
    client = RingClient(token="tok", session=session)

    events = client.get_event_history("dev-1")

    assert len(events) == 1
    assert events[0].event_type == "motion"
    assert events[0].sub_type == "human"
    assert events[0].is_human_motion is True


def test_get_event_history_passes_event_types_filter():
    session = MagicMock()
    session.get.return_value = _mock_response(json_body={"data": []})
    client = RingClient(token="tok", session=session)

    client.get_event_history("dev-1", event_types="ding,motion.human")

    params = session.get.call_args.kwargs["params"]
    assert params["event_types"] == "ding,motion.human"


def test_download_video_clip_raises_clip_not_available_on_416():
    session = MagicMock()
    session.post.return_value = _mock_response(
        status_code=416,
        json_body={"errors": [{"code": "TIMESTAMP_NOT_FOUND", "detail": "No recording at that time"}]},
    )
    client = RingClient(token="tok", session=session)

    with pytest.raises(ClipNotAvailable):
        client.download_video_clip("dev-1", dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc))


def test_download_video_clip_rejects_duration_over_fifteen_minutes():
    client = RingClient(token="tok", session=MagicMock())
    with pytest.raises(ValueError):
        client.download_video_clip(
            "dev-1", dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc), duration_seconds=16 * 60
        )


def test_generic_error_raises_ring_api_error_not_clip_not_available():
    session = MagicMock()
    session.get.return_value = _mock_response(status_code=401, json_body={"errors": [{"code": "UNAUTHORIZED", "detail": "bad token"}]})
    client = RingClient(token="bad-tok", session=session)

    with pytest.raises(RingAPIError) as exc_info:
        client.list_devices()
    assert not isinstance(exc_info.value, ClipNotAvailable)


def test_parse_timestamp_handles_epoch_millis_and_iso_strings():
    from_millis = parse_timestamp(1758376263000)
    from_iso = parse_timestamp("2026-09-20T14:11:03Z")
    assert from_millis.year == 2025 or from_millis.year == 2026  # sanity: does not crash / wildly wrong
    assert from_iso.hour == 14 and from_iso.minute == 11


def test_parse_timestamp_rejects_unrecognized_shape():
    with pytest.raises(ValueError):
        parse_timestamp(object())
