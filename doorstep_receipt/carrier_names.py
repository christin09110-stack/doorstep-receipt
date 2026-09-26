"""What a carrier's own wording means: its name, and its status line.

The vocabulary half of the old ``carriers.py``. ``resolve`` turns whatever
string the app is holding (a code, a display name, something close to either)
into a carrier. ``normalise_status`` turns a carrier's own printed status line
into one of this app's three statuses.

Both are deliberately conservative. ``resolve`` will not substring-match a
needle under three characters, because a two-character needle matches most of
the six display names by accident and an empty one matches all of them, which
is how a blank carrier field once came back as UPS. ``normalise_status`` checks
the carrier's own vocabulary before the shared fallback, so "Delivery
attempted" is never read as "delivered" merely because the shorter word is a
substring of the longer line.
"""

from __future__ import annotations

from .carrier import CarrierStatus
from .carrier_registry import BY_CODE, CARRIERS, UNKNOWN_CARRIER
from .carrier_shapes import Carrier


def resolve(code_or_name: str | None) -> Carrier:
    """A carrier from a code, a display name, or something close to either."""
    needle = (code_or_name or "").strip().lower().replace("_", "-")
    if not needle:
        return UNKNOWN_CARRIER
    if needle in BY_CODE:
        return BY_CODE[needle]
    for carrier in CARRIERS:
        if carrier.display_name.lower() == needle or carrier.code.replace("-", " ") == needle.replace("-", " "):
            return carrier
    # Substring matching only once the needle is long enough to mean something.
    # A two-character needle matches most of the six display names by accident,
    # and an empty one matches all of them.
    if len(needle) >= 3:
        for carrier in CARRIERS:
            if needle in carrier.display_name.lower() or carrier.code in needle:
                return carrier
    return UNKNOWN_CARRIER


def normalise_status(status_text: str, carrier: Carrier | None = None) -> CarrierStatus | None:
    """Map a carrier's own printed status line onto this app's three statuses.

    Checks the carrier's own vocabulary first, then the shared fallback
    vocabulary, so "Delivery attempted" is never read as "delivered" just
    because the shorter word is a substring of the longer line.
    """
    if not status_text:
        return None
    lowered = status_text.lower()
    vocabularies = []
    if carrier is not None:
        vocabularies.append(carrier.status_phrases)
    vocabularies.append(UNKNOWN_CARRIER.status_phrases)
    for phrases in vocabularies:
        for phrase, status in phrases:
            if phrase in lowered:
                return status
    return None
