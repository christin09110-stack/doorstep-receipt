"""The six carriers: number formats, status words, and window widths.

Data only, split from ``carriers.py`` the way ``guard_rules.py`` is split from
``guard.py``. What is here is the table a reviewer has to read to check that
this app knows what it claims to know about UPS, USPS, FedEx, Royal Mail, DHL
Express and Amazon Logistics. The lookups that use it live next door.

Every value is a published public-facing format, or a phrase a carrier prints
on its own tracking page. Nothing here is invented, and none of it needs a
carrier API key: this is the shape of the page the user is already looking at.

``default_window_minutes`` is the field worth arguing about, and its reason is
written beside each number. A carrier whose handheld scans on the doorstep
produces a timestamp minutes from the camera event. A carrier whose driver
scans a truckload at the kerb can be half an hour out. One window for both
manufactures "not consistent" verdicts for the second, and sweeps in the
neighbour's visitor for the first.

Status phrases are listed longest first, so "delivery attempted" is matched
before "delivered", which is a substring of nothing here by accident.
"""

from __future__ import annotations

from .carrier import CarrierStatus
from .carrier_shapes import Carrier, build_carrier as _c

_DELIVERED = CarrierStatus.DELIVERED
_ATTEMPTED = CarrierStatus.ATTEMPTED_DELIVERY
_OUT = CarrierStatus.OUT_FOR_DELIVERY

CARRIERS: tuple[Carrier, ...] = (
    _c(
        "ups",
        "UPS",
        (r"1Z[0-9A-Z]{16}", r"T\d{10}", r"\d{9}"),
        (
            ("delivery attempted", _ATTEMPTED),
            ("attempted delivery", _ATTEMPTED),
            ("out for delivery today", _OUT),
            ("out for delivery", _OUT),
            ("delivered to a ups access point", _DELIVERED),
            ("left at", _DELIVERED),
            ("delivered", _DELIVERED),
        ),
        40,
        "UPS drivers scan at the vehicle on a multi-stop loop, so the scan time and "
        "the doorstep time can separate by a good part of an hour.",
        "1Z followed by 16 letters or digits",
    ),
    _c(
        "usps",
        "USPS",
        (r"9[2345]\d{18,20}", r"\d{20,22}", r"[A-Z]{2}\d{9}US"),
        (
            ("no access to delivery location", _ATTEMPTED),
            ("notice left", _ATTEMPTED),
            ("delivery attempted", _ATTEMPTED),
            ("out for delivery", _OUT),
            ("delivered, in/at mailbox", _DELIVERED),
            ("delivered, front door/porch", _DELIVERED),
            ("delivered, parcel locker", _DELIVERED),
            ("delivered, individual picked up at", _DELIVERED),
            ("delivered", _DELIVERED),
        ),
        30,
        "USPS carriers scan at the point of delivery on a walking route, so the scan "
        "sits closer to the door than a vehicle-based carrier's does.",
        "20 to 22 digits, usually beginning 9400 or 9205",
    ),
    _c(
        "fedex",
        "FedEx",
        (r"\d{12}", r"\d{15}", r"\d{20}", r"96\d{20}"),
        (
            ("delivery exception", _ATTEMPTED),
            ("customer not available or business closed", _ATTEMPTED),
            ("delivery attempted", _ATTEMPTED),
            ("on fedex vehicle for delivery", _OUT),
            ("out for delivery", _OUT),
            ("left at front door", _DELIVERED),
            ("signature service not requested", _DELIVERED),
            ("delivered", _DELIVERED),
        ),
        40,
        "FedEx Ground stops are scanned at the vehicle, and the delivery scan is "
        "frequently entered after the driver is back in the cab.",
        "12 or 15 digits",
    ),
    _c(
        "royal-mail",
        "Royal Mail",
        (r"[A-Z]{2}\d{9}GB", r"[A-Z]{2}\d{9}[A-Z]{2}"),
        (
            ("we attempted to deliver your item", _ATTEMPTED),
            ("something went wrong", _ATTEMPTED),
            ("we were unable to deliver", _ATTEMPTED),
            ("your item is on its way", _OUT),
            ("out for delivery", _OUT),
            ("delivered to a safeplace", _DELIVERED),
            ("delivered to your neighbour", _DELIVERED),
            ("delivered", _DELIVERED),
        ),
        25,
        "Royal Mail posties scan on the doorstep with a handheld, so the scan time "
        "and the camera event should sit close together.",
        "two letters, nine digits, then GB",
    ),
    _c(
        "dhl",
        "DHL Express",
        (r"\d{10}", r"JJD\d{15,18}", r"JVGL\d{14,18}"),
        (
            ("delivery attempt made", _ATTEMPTED),
            ("recipient not at home", _ATTEMPTED),
            ("with delivery courier", _OUT),
            ("out for delivery", _OUT),
            ("delivered - signed for by", _DELIVERED),
            ("delivered", _DELIVERED),
        ),
        30,
        "DHL Express couriers capture a signature or a photo at the door, which puts "
        "the scan at the doorstep rather than at the vehicle.",
        "10 digits",
    ),
    _c(
        "amazon",
        "Amazon Logistics",
        (r"TBA\d{12,15}", r"TBC\d{12,15}"),
        (
            ("delivery attempted", _ATTEMPTED),
            ("we missed you", _ATTEMPTED),
            ("out for delivery", _OUT),
            ("arriving today", _OUT),
            ("handed to resident", _DELIVERED),
            ("delivered to safe place", _DELIVERED),
            ("left in a safe place", _DELIVERED),
            ("delivered", _DELIVERED),
        ),
        20,
        "Amazon Logistics drivers are prompted to photograph the parcel where they "
        "leave it, which anchors the scan to the doorstep.",
        "TBA followed by 12 to 15 digits",
    ),
)

BY_CODE: dict[str, Carrier] = {c.code: c for c in CARRIERS}

# Fallback for a number this registry does not recognise. Keeps the existing
# 40-minute default, which is the widest of the six and therefore the least
# likely to manufacture a "not consistent" verdict from a scan-time offset.
UNKNOWN_CARRIER = _c(
    "unknown",
    "unspecified carrier",
    (),
    (
        ("attempted delivery", _ATTEMPTED),
        ("delivery attempted", _ATTEMPTED),
        ("out for delivery", _OUT),
        ("delivered", _DELIVERED),
    ),
    40,
    "No carrier was identified from the tracking number, so the widest of the six "
    "known windows is used. A wide window is the cautious choice: it makes a "
    "'not consistent' verdict harder to reach, not easier.",
    "not recognised",
)

BY_CODE: dict[str, Carrier] = {c.code: c for c in CARRIERS}
