"""What a carrier is, as a shape: the dataclass and its one constructor.

Kept apart from both the table (``carrier_registry.py``) and the lookups
(``carriers.py``) so the registry can be read as a table of values rather than
as code, and so neither of those two has to import the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .carrier import CarrierStatus

@dataclass(frozen=True)
class Carrier:
    code: str
    display_name: str
    number_patterns: tuple[str, ...]
    # Lowercase fragments as printed on that carrier's own tracking page,
    # longest first so "delivery attempted" wins over "delivered".
    status_phrases: tuple[tuple[str, CarrierStatus], ...]
    default_window_minutes: int
    window_reason: str
    number_shape: str
    compiled: tuple[re.Pattern[str], ...] = field(default=(), repr=False, compare=False)

    def matches(self, tracking_number: str) -> bool:
        candidate = tracking_number.replace(" ", "").upper()
        return any(p.fullmatch(candidate) for p in self.compiled)


def build_carrier(code, display_name, number_patterns, status_phrases, window, reason, shape) -> Carrier:
    return Carrier(
        code=code,
        display_name=display_name,
        number_patterns=number_patterns,
        status_phrases=status_phrases,
        default_window_minutes=window,
        window_reason=reason,
        number_shape=shape,
        compiled=tuple(re.compile(p) for p in number_patterns),
    )
