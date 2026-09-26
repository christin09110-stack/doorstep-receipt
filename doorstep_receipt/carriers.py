"""The carrier vocabulary, as one import.

This module is now a façade. The first build put every carrier concern in one
file; it grew two distinct jobs and was split into them:

- ``carrier_shapes.py``   what a carrier is, as a dataclass
- ``carrier_registry.py`` the six carriers, as a table of published values
- ``carrier_match.py``    which carrier is this, from a number or from a page
- ``carrier_names.py``    what this carrier's own wording means

Everything stays importable from here, because "from .carriers import ..." is
what the rest of the app reads well, and which file a name lives in is not
something a route handler should have to know.

Why any of this exists at all: the first build took a tracking number and a
status from a dropdown and treated every carrier identically. That was wrong in
two ways a claims desk notices at once. The number already says who (``1Z`` and
18 characters is UPS and nothing else). And the status words differ, as does
where the scan happens, which is why the checking window is per carrier rather
than a single number for all six.
"""

from __future__ import annotations

from .carrier import CarrierStatus
from .carrier_match import carrier_candidates, identify_carrier, identify_from_page
from .carrier_names import normalise_status, resolve
from .carrier_registry import BY_CODE, CARRIERS, UNKNOWN_CARRIER
from .carrier_shapes import Carrier

__all__ = [
    "BY_CODE",
    "CARRIERS",
    "UNKNOWN_CARRIER",
    "Carrier",
    "CarrierStatus",
    "carrier_candidates",
    "identify_carrier",
    "identify_from_page",
    "normalise_status",
    "resolve",
]
