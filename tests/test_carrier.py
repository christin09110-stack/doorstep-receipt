import datetime as dt

import pytest

from doorstep_receipt.carrier import CarrierStatus, ManualEntryAdapter

TZ = dt.timezone.utc


def test_manual_entry_builds_claim_from_status_string():
    adapter = ManualEntryAdapter()
    claim = adapter.fetch_claim(
        tracking_number=" 1Z999AA10123456784 ",
        carrier_name="UPS",
        status="delivered",
        claimed_at=dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ),
    )
    assert claim.tracking_number == "1Z999AA10123456784"
    assert claim.status == CarrierStatus.DELIVERED
    assert claim.carrier_name == "UPS"


def test_manual_entry_rejects_blank_tracking_number():
    adapter = ManualEntryAdapter()
    with pytest.raises(ValueError):
        adapter.fetch_claim(
            tracking_number="   ",
            carrier_name="UPS",
            status="delivered",
            claimed_at=dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ),
        )


def test_manual_entry_rejects_unknown_status():
    adapter = ManualEntryAdapter()
    with pytest.raises(ValueError):
        adapter.fetch_claim(
            tracking_number="1Z999",
            carrier_name="UPS",
            status="definitely_not_a_real_status",
            claimed_at=dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ),
        )


def test_manual_entry_defaults_carrier_name_when_blank():
    adapter = ManualEntryAdapter()
    claim = adapter.fetch_claim(
        tracking_number="1Z999",
        carrier_name="   ",
        status=CarrierStatus.OUT_FOR_DELIVERY,
        claimed_at=dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ),
    )
    assert claim.carrier_name == "unspecified carrier"


def test_claim_window_defaults_to_forty_minutes():
    adapter = ManualEntryAdapter()
    claim = adapter.fetch_claim(
        tracking_number="1Z999",
        carrier_name="UPS",
        status="delivered",
        claimed_at=dt.datetime(2026, 9, 20, 14, 11, tzinfo=TZ),
    )
    start, end = claim.window()
    assert (end - start) == dt.timedelta(minutes=80)
