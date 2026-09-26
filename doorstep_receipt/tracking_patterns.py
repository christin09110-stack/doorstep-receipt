"""The formats the deterministic parser knows, as patterns.

Data for ``tracking_text.py``, kept separate so the list of shapes this app can
read without a model is a file you can scan in one go.

The date handling is the part that matters for an evidentiary document.
``09/10/2026`` is the 9th of October in London and the 10th of September in
Ohio. Where the day is above 12 the order is settled by arithmetic. Where it is
not, the carrier decides: Royal Mail and DHL Express pages are day-first, the
US carriers are month-first. If the carrier is unknown the parse is refused
rather than guessed, because a wrong date on a claim document is worse than a
missing one.
"""

from __future__ import annotations

import re

DAY_FIRST_CARRIERS = frozenset({"royal-mail", "dhl"})

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"],
        start=1,
    )
}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})

_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_TIME = r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})(?::\d{2})?\s*(?P<meridiem>[ap]\.?\s?m\.?)?"

# "September 20, 2026 at 2:11 P.M." and "20 September 2026 at 14:11"
_MONTH_NAME_DATE = re.compile(
    rf"(?:(?P<day1>\d{{1,2}})\s+(?P<month1>{_MONTH_ALT})|(?P<month2>{_MONTH_ALT})\s+(?P<day2>\d{{1,2}}))"
    rf"(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}})"
    rf"(?:,?\s*(?:at\s+)?{_TIME})?",
    re.IGNORECASE,
)
# "2026-09-20 14:11" / "2026-09-20T14:11:00Z"
_ISO_DATE = re.compile(rf"(?P<year>\d{{4}})-(?P<month>\d{{2}})-(?P<day>\d{{2}})[T ]\s*{_TIME}", re.IGNORECASE)
# "09/20/2026 2:11 pm" / "20/09/2026 14:11"
_SLASH_DATE = re.compile(
    rf"(?P<first>\d{{1,2}})[/.](?P<second>\d{{1,2}})[/.](?P<year>\d{{2,4}})(?:,?\s*(?:at\s+)?{_TIME})?",
    re.IGNORECASE,
)

_TRACKING_HINT = re.compile(
    r"(?:tracking(?:\s+|-)?(?:number|no\.?|id|#)?|consignment|reference)\s*[:#]?\s*([0-9A-Z][0-9A-Z \-]{7,30})",
    re.IGNORECASE,
)
_BARE_NUMBER = re.compile(r"\b(1Z[0-9A-Z]{16}|TB[AC]\d{12,15}|[A-Z]{2}\d{9}[A-Z]{2}|\d{10,22})\b")
