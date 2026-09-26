"""Which carrier is this? Matching a number, and reading a page.

Separated from ``carriers.py`` because these are two different questions that
happened to live in one file. This one answers "which carrier is this", from a
number or from a page. The other answers "what does this carrier's own wording
mean", which is a question about vocabulary rather than identity.

The rule both functions here share is that they decline rather than guess. A
bare 10-digit number is a valid DHL Express number and nothing else in this
registry, but a bare 12-digit number is FedEx and USPS's 20-to-22-digit range
overlaps one FedEx format. Where two carriers claim a number, this returns
nothing and the app asks the user, because a wrong carrier sets a wrong
checking window, and a wrong window produces a confident finding about the
wrong hour.
"""

from __future__ import annotations

import re

from .carrier_registry import CARRIERS, UNKNOWN_CARRIER
from .carrier_shapes import Carrier
from .carrier_names import resolve


def identify_carrier(tracking_number: str) -> Carrier | None:
    """The carrier whose published number format this tracking number fits.

    Returns None rather than guessing when the number is ambiguous across two
    carriers, which genuinely happens: a bare 10-digit number is a valid DHL
    Express number and nothing else here, but a bare 12-digit number is FedEx,
    and USPS's 20-to-22-digit range overlaps one FedEx format. Where two
    carriers claim a number, the app asks instead of picking.
    """
    if not tracking_number:
        return None
    hits = [c for c in CARRIERS if c.matches(tracking_number)]
    if len(hits) == 1:
        return hits[0]
    return None


def carrier_candidates(tracking_number: str) -> list[Carrier]:
    """Every carrier whose format the number fits, for the ambiguous case."""
    return [c for c in CARRIERS if c.matches(tracking_number)]


def identify_from_page(
    tracking_number: str | None, text: str = "", hint: str | None = None
) -> tuple[Carrier | None, str]:
    """Which carrier a pasted tracking page belongs to, and a warning if unsure.

    Three sources, in descending order of how much they are worth trusting:

    1. **The number.** A published format is a fact about the number itself and
       needs nothing else to be true.
    2. **A hint from the caller**, such as a carrier the user already picked.
    3. **A name printed on the page.** Weakest of the three, because a page can
       mention a carrier it is not from, but better than nothing when the number
       is in a shape this app does not know.

    Returns ``(carrier, warning)``. The warning is non-empty only in the case
    worth telling the user about: a number that fits two carriers' published
    formats at once, where guessing would be worse than asking.
    """
    warning = ""
    if tracking_number:
        carrier = identify_carrier(tracking_number)
        if carrier is not None:
            return carrier, warning
        candidates = carrier_candidates(tracking_number)
        if len(candidates) > 1:
            names = " or ".join(c.display_name for c in candidates)
            warning = f"That number fits the published format for {names}. Pick the carrier to continue."

    if hint:
        from_hint = resolve(hint)
        if from_hint.code != UNKNOWN_CARRIER.code:
            return from_hint, warning

    for carrier in CARRIERS:
        if re.search(rf"\b{re.escape(carrier.display_name)}\b", text, re.IGNORECASE):
            return carrier, warning
    return None, warning
