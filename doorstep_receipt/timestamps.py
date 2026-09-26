"""One way of writing a time, used everywhere, from DOCUMENT-CRAFT.md section 4.

The rules this implements, and why each one is not a style preference:

- **Never a local time without an offset.** A bare "14:11" in an evidence pack is
  a note to self. Every rendered time carries the zone label the reader knows
  and the numeric offset in brackets, because the label alone is ambiguous: BST
  is British Summer Time in London and Bangladesh Standard Time in Dhaka.
- **A true minus sign** (U+2212) in a negative offset, so a hyphen in a fax of a
  fax is not read as a dash.
- **Do not invent precision.** A carrier page that said "2:11 P.M." did not say
  14:11:00. Claim times are rendered to the minute, camera events to the second,
  because that is the precision each source actually gave.
- **A window is two endpoints and a duration**, never one of the three.
- **Prose spells the month**; tables use the ISO order. Never 14/03/2026, which
  is a different day on two continents.
- Machine records carry the RFC 3339 string alongside, with an upper-case T and Z
  per section 5.6.
"""

from __future__ import annotations

import datetime as dt
import re

MINUS = "−"
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def offset_text(ts: dt.datetime) -> str:
    """The bracketed numeric offset, with a true minus sign."""
    offset = ts.utcoffset()
    if offset is None:
        # RFC 3339 section 4.3: the offset to local time is not known. This is
        # not the same as Z, which would assert that UTC is the right reference
        # frame, and that is a claim we are not in a position to make.
        return "UTC" + MINUS + "00:00"
    total = int(offset.total_seconds() // 60)
    sign = MINUS if total < 0 else "+"
    hours, minutes = divmod(abs(total), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


# A timezone label is one of two things: an IANA name (`America/New_York`) or a
# short abbreviation (`BST`, `UTC+1`). Both are closed, small shapes, so this is
# an allowlist rather than a filter -- GUARD-STANDARD.md §1, rung S5.
#
# It is not decoration. `timezone_printed` is a free-text field a multimodal
# model fills in from a photograph somebody took of a carrier's web page, and
# the page it lands on renders it into HTML. A label of
# `UTC" onfocus=alert(1) x="<img src=x onerror=alert(1)>` reached the evidence
# pack with the tag intact, because `_event_table_html` interpolated the
# formatted time without escaping it. Escaping that one call site is the last
# line; refusing to carry a label that is not a label is the argument.
_LABEL_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[ _/+−-][A-Za-z0-9]+)*$")
_LABEL_MAX = 40


def safe_label(label: str, fallback: str = "UTC") -> str:
    """The label if it is shaped like one, else the fallback.

    Refuse, do not repair. A label with a quote in it is not a timezone with a
    typo; it is somebody else's idea of what should be on this document.
    """
    candidate = (label or "").strip()
    if 0 < len(candidate) <= _LABEL_MAX and _LABEL_SHAPE.match(candidate):
        return candidate
    return fallback


def zone_label(ts: dt.datetime, fallback: str = "UTC") -> str:
    """The zone name a reader recognises.

    A claim's times carry a fixed-offset tzinfo, because a tracking page prints
    a wall clock and this app is told the offset rather than the zone. Python
    names such a zone "UTC-04:00", which is the offset again and not a label, so
    whatever the user's browser reported ("America/New_York") is preferred
    whenever one was supplied.
    """
    name = ts.tzname() if ts.tzinfo else None
    if name is None or name.startswith(("UTC+", "UTC-", "UTC−")):
        return safe_label(fallback)
    return safe_label(name)


def canonical(ts: dt.datetime, seconds: bool = False, label: str = "UTC") -> str:
    """``2026-09-20 14:11 UTC (UTC+00:00)``, the one form used everywhere."""
    pattern = "%Y-%m-%d %H:%M:%S" if seconds else "%Y-%m-%d %H:%M"
    return f"{ts.strftime(pattern)} {zone_label(ts, label)} ({offset_text(ts)})"


def short(ts: dt.datetime, seconds: bool = False) -> str:
    """The same date and time without the zone, for a column that states its
    zone once in the header rather than on every row."""
    return ts.strftime("%Y-%m-%d %H:%M:%S" if seconds else "%Y-%m-%d %H:%M")


def prose(ts: dt.datetime, label: str = "UTC") -> str:
    """``14:11 on 20 September 2026 (UTC+00:00)``, for a sentence."""
    return (
        f"{ts.strftime('%H:%M')} on {ts.day} {_MONTHS[ts.month - 1]} {ts.year} "
        f"{zone_label(ts, label)} ({offset_text(ts)})"
    )


def rfc3339(ts: dt.datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


def window_text(start: dt.datetime, end: dt.datetime, label: str = "UTC") -> str:
    """Two endpoints and a duration, which is what a window is."""
    total = int((end - start).total_seconds() // 60)
    hours, minutes = divmod(total, 60)
    duration = f"{hours} h {minutes:02d} m" if hours else f"{minutes} m"
    same_day = start.date() == end.date()
    tail = short(end)[11:] if same_day else short(end)
    return f"{short(start)} to {tail} {zone_label(start, label)} ({offset_text(start)}), {duration}"
