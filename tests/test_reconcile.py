import datetime as dt

from doorstep_receipt.carrier import CarrierClaim, CarrierStatus
from doorstep_receipt.coverage import sample
from doorstep_receipt.reconcile import Verdict, reconcile
from doorstep_receipt.ring_client import RingEvent

TZ = dt.timezone.utc


def _claim(status: CarrierStatus, claimed_at: dt.datetime, window_minutes: int = 40) -> CarrierClaim:
    return CarrierClaim(
        tracking_number="1Z999AA10123456784",
        carrier_name="Test Carrier",
        status=status,
        claimed_at=claimed_at,
        window_minutes=window_minutes,
    )


def _event(event_type: str, sub_type, timestamp: dt.datetime, event_id: str = "evt-1") -> RingEvent:
    return RingEvent(event_id=event_id, event_type=event_type, sub_type=sub_type, timestamp=timestamp, device_id="dev-1")


def _covered(claim: CarrierClaim, *events: RingEvent) -> list[RingEvent]:
    """The events, plus camera status samples spanning the claim's whole window.

    Every test below needs these. A window this app cannot show the camera was
    watching can no longer produce a "not consistent" verdict at all (rule 3 in
    reconcile.reconcile), so a test that omits coverage is testing the coverage
    rule rather than the rule it meant to test.
    """
    start, end = claim.window()
    samples, cursor = [], start - dt.timedelta(minutes=5)
    while cursor <= end + dt.timedelta(minutes=5):
        samples.append(sample(cursor))
        cursor += dt.timedelta(minutes=15)
    return list(events) + samples


def test_delivered_with_human_motion_in_window_is_consistent():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = _claim(CarrierStatus.DELIVERED, claimed_at)
    events = _covered(claim, _event("motion", "human", claimed_at + dt.timedelta(minutes=2)))

    result = reconcile(claim, events)

    assert result.verdict == Verdict.CONSISTENT
    assert "14:13" in result.summary_sentence
    assert "person" in result.summary_sentence


def test_delivered_with_button_press_in_window_is_consistent():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = _claim(CarrierStatus.DELIVERED, claimed_at)
    events = _covered(claim, _event("ding", None, claimed_at))

    result = reconcile(claim, events)

    assert result.verdict == Verdict.CONSISTENT
    assert "button press" in result.summary_sentence


def test_delivered_with_no_events_is_not_consistent():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = _claim(CarrierStatus.DELIVERED, claimed_at)

    result = reconcile(claim, _covered(claim))

    assert result.verdict == Verdict.NOT_CONSISTENT
    assert "no arrival was recorded" in result.summary_sentence
    # Must never accuse the carrier directly.
    assert "lied" not in result.summary_sentence.lower()
    assert "did not come" not in result.summary_sentence.lower()


def test_delivered_ignores_events_outside_window():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = _claim(CarrierStatus.DELIVERED, claimed_at, window_minutes=10)
    far_event = _event("motion", "human", claimed_at + dt.timedelta(hours=3))

    result = reconcile(claim, _covered(claim, far_event))

    assert result.verdict == Verdict.NOT_CONSISTENT
    assert result.matched_events == []


def test_delivered_ignores_vehicle_motion_not_human_or_ding():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = _claim(CarrierStatus.DELIVERED, claimed_at)
    vehicle_event = _event("motion", "vehicle", claimed_at + dt.timedelta(minutes=1))

    result = reconcile(claim, _covered(claim, vehicle_event))

    # A vehicle passing is not evidence a delivery happened.
    assert result.verdict == Verdict.NOT_CONSISTENT
    assert result.matched_events[0].sub_type == "vehicle"  # shown, not hidden


def test_attempted_delivery_with_no_events_is_consistent():
    claimed_at = dt.datetime(2026, 9, 20, 10, 5, tzinfo=TZ)
    claim = _claim(CarrierStatus.ATTEMPTED_DELIVERY, claimed_at)

    result = reconcile(claim, _covered(claim))

    assert result.verdict == Verdict.CONSISTENT


def test_attempted_delivery_with_arrival_event_is_indeterminate_not_accusatory():
    claimed_at = dt.datetime(2026, 9, 20, 10, 5, tzinfo=TZ)
    claim = _claim(CarrierStatus.ATTEMPTED_DELIVERY, claimed_at)
    events = _covered(claim, _event("ding", None, claimed_at + dt.timedelta(minutes=1)))

    result = reconcile(claim, events)

    assert result.verdict == Verdict.INDETERMINATE
    assert "does not establish who that was" in result.summary_sentence


def test_matched_events_are_sorted_by_timestamp():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = _claim(CarrierStatus.DELIVERED, claimed_at, window_minutes=60)
    later = _event("motion", "human", claimed_at + dt.timedelta(minutes=20), event_id="evt-later")
    earlier = _event("ding", None, claimed_at + dt.timedelta(minutes=1), event_id="evt-earlier")

    result = reconcile(claim, [later, earlier])

    assert [e.event_id for e in result.matched_events if not e.event_id.startswith("status")] == [
        "evt-earlier",
        "evt-later",
    ]


def test_window_is_symmetric_around_claimed_time():
    claimed_at = dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ)
    claim = _claim(CarrierStatus.DELIVERED, claimed_at, window_minutes=40)
    start, end = claim.window()
    assert start == claimed_at - dt.timedelta(minutes=40)
    assert end == claimed_at + dt.timedelta(minutes=40)
