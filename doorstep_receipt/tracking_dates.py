"""Reading a date off a tracking page without inventing one.

The hardest 60 lines in the deterministic parser, and the ones most worth
keeping separate, because getting a date wrong here does not produce a visible
error. It shifts the window the camera is checked against and produces a
confident finding about the wrong hour.

``09/10/2026`` is the 9th of October in London and the 10th of September in
Ohio. Where the day is above 12 the order is settled by arithmetic. Where it is
not, the carrier settles it: Royal Mail and DHL Express pages are day-first, the
US carriers are month-first. Where the carrier is unknown the parse is refused
and the user is asked, because a missing date costs ten seconds and a wrong one
costs the claim.

No timezone is attached here, ever. Tracking pages print a wall clock and almost
never an offset, so this returns a naive datetime and the caller records that
the offset was supplied rather than observed.
"""

from __future__ import annotations

import datetime as dt
import re

from .carrier_shapes import Carrier
from .tracking_patterns import (
    DAY_FIRST_CARRIERS,
    _ISO_DATE,
    _MONTHS,
    _MONTH_NAME_DATE,
    _SLASH_DATE,
)


def _to_24h(hour: int, meridiem: str | None) -> int:
    if not meridiem:
        return hour
    flat = meridiem.replace(".", "").replace(" ", "").lower()
    if flat.startswith("p") and hour != 12:
        return hour + 12
    if flat.startswith("a") and hour == 12:
        return 0
    return hour


def _time_parts(match: re.Match[str]) -> tuple[int, int]:
    groups = match.groupdict()
    if not groups.get("hour"):
        return 0, 0
    return _to_24h(int(groups["hour"]), groups.get("meridiem")), int(groups["minute"])


def find_datetime(text: str, carrier: Carrier | None) -> tuple[dt.datetime | None, str | None, str | None]:
    """Return (naive datetime, the matched text, a warning) from the first date
    this parser recognises. No timezone is attached here: see the module
    docstring for why that is deliberate."""
    iso = _ISO_DATE.search(text)
    if iso:
        hour, minute = _time_parts(iso)
        return (
            dt.datetime(int(iso["year"]), int(iso["month"]), int(iso["day"]), hour, minute),
            iso.group(0).strip(),
            None,
        )

    named = _MONTH_NAME_DATE.search(text)
    if named:
        month_name = (named["month1"] or named["month2"] or "").lower()
        day = int(named["day1"] or named["day2"])
        hour, minute = _time_parts(named)
        return (
            dt.datetime(int(named["year"]), _MONTHS[month_name], day, hour, minute),
            named.group(0).strip(),
            None,
        )

    slash = _SLASH_DATE.search(text)
    if slash:
        first, second = int(slash["first"]), int(slash["second"])
        year = int(slash["year"])
        year += 2000 if year < 100 else 0
        hour, minute = _time_parts(slash)
        day_first = None
        if first > 12:
            day_first = True
        elif second > 12:
            day_first = False
        elif carrier is not None and carrier.code != "unknown":
            day_first = carrier.code in DAY_FIRST_CARRIERS
        if day_first is None:
            return (
                None,
                slash.group(0).strip(),
                f"The page shows the date as {slash['first']}/{slash['second']}/{slash['year']}, which is "
                "the same string for two different days and no carrier was identified to settle the order. "
                "Enter the delivery date directly.",
            )
        day, month = (first, second) if day_first else (second, first)
        return dt.datetime(year, month, day, hour, minute), slash.group(0).strip(), None

    return None, None, None
