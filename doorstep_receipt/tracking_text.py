"""The deterministic tracking-page parser: the floor under the model.

``tracking_reader.py`` prefers Bedrock, because a carrier's tracking page is a
screenshot as often as it is text and because the six carriers in
``carriers.py`` lay the same four facts out six different ways. But a demo that
stops working when a network call fails is not a demo, so everything Bedrock is
asked to do here can also be done by these regexes, less well, with no network
at all.

That is the honest framing of the split. The model reads a photograph and reads
prose. This file reads the formats we could enumerate. When Bedrock is
unreachable the app degrades to this and says on the page that it did.

Date handling, which is the part that matters for an evidentiary document:

- Tracking pages print local time and almost never print an offset. This parser
  never invents one. It returns a naive datetime plus a flag, and the caller
  attaches the timezone the user told us about and records that it was told,
  not observed.
- Date reading lives in ``tracking_dates.py``, because a wrong date does not
  produce a visible error: it shifts the window and produces a confident
  finding about the wrong hour.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from .carriers import Carrier, CarrierStatus, identify_from_page, normalise_status
from .tracking_dates import find_datetime
from .tracking_patterns import _BARE_NUMBER, _TRACKING_HINT

@dataclass
class ParsedTrackingText:
    """What the regexes could get out of a pasted tracking page."""

    tracking_number: str | None = None
    carrier: Carrier | None = None
    status: CarrierStatus | None = None
    status_text: str | None = None
    naive_claimed_at: dt.datetime | None = None
    claimed_at_text: str | None = None
    warnings: list[str] | None = None

    def warn(self, message: str) -> None:
        if self.warnings is None:
            self.warnings = []
        if message not in self.warnings:
            self.warnings.append(message)


def _looks_like_a_tracking_number(compact: str) -> bool:
    """Four digits is the bar. It keeps the label out of the answer.

    The labelled-number regex is greedy enough to swallow a second label:
    a page reading "UPS Tracking / Tracking Number: 1Z999..." once returned
    "TrackingNumber" as the tracking number, because that string is eight
    characters of A-Z and the pattern did not care whether any of them were
    digits. Every format in carriers.py has at least nine digits.
    """
    return len(compact) >= 8 and len(re.findall(r"\d", compact)) >= 4


def find_tracking_number(text: str) -> str | None:
    """The tracking number, preferring one that is labelled as such."""
    for hinted in _TRACKING_HINT.finditer(text):
        compact = hinted.group(1).strip().rstrip(".,;").replace(" ", "").replace("-", "").upper()
        if _BARE_NUMBER.fullmatch(compact) or _looks_like_a_tracking_number(compact):
            return compact
    bare = _BARE_NUMBER.search(text.upper())
    return bare.group(1) if bare else None


def find_status_line(text: str, carrier: Carrier | None) -> tuple[CarrierStatus | None, str | None]:
    """The line of the page that carries a recognised status, and its meaning."""
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        status = normalise_status(line, carrier)
        if status is not None:
            return status, line
    status = normalise_status(text, carrier)
    return status, None


def parse_tracking_text(text: str, carrier_hint: str | None = None) -> ParsedTrackingText:
    """Everything the regexes can get from a pasted tracking page."""
    parsed = ParsedTrackingText()
    if not text or not text.strip():
        parsed.warn("Nothing was pasted, so there was nothing to read.")
        return parsed

    parsed.tracking_number = find_tracking_number(text)

    carrier, carrier_warning = identify_from_page(parsed.tracking_number, text, carrier_hint)
    parsed.carrier = carrier
    if carrier_warning:
        parsed.warn(carrier_warning)

    parsed.status, parsed.status_text = find_status_line(text, carrier)
    if parsed.status is None:
        parsed.warn("No delivery status was recognised on that page. Pick the status yourself.")

    when, when_text, warning = find_datetime(text, carrier)
    parsed.naive_claimed_at = when
    parsed.claimed_at_text = when_text
    if warning:
        parsed.warn(warning)
    elif when is None:
        parsed.warn("No delivery date and time was recognised on that page. Enter it yourself.")
    return parsed
