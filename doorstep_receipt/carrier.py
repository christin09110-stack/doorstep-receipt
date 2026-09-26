"""Carrier claim intake: the "least bad route".

Every route to real carrier tracking data is bad, in a different way, and this
file has to commit to exactly one and be honest about the cost (see
SPEC.md, "What it deliberately does not do"):

- Carrier APIs (UPS, FedEx, Royal Mail, USPS) authenticate a shipper account, not
  a recipient. A consumer app cannot get one.
- Reading dispatch/delivery emails needs Gmail's restricted scopes and an annual
  third-party security assessment: a heavier compliance burden than Ring
  certification itself.
- Manual entry always works and is the floor. ``ManualEntryAdapter`` is what
  the user falls back to when everything else is unavailable.
- Reading the carrier's own tracking page, which the user is already looking at,
  needs nobody's permission and breaches nobody's terms. That is
  ``TrackingPageAdapter``, backed by a multimodal model in
  ``tracking_reader.py``: the user photographs or pastes the page and the four
  facts come back out of it. This is the adapter the product leads with now.
  It is not a carrier integration and does not pretend to be one; it is an
  easier way for a person to hand over what they already have.

Statuses are deliberately restricted to the vocabulary a tracking page actually
shows a recipient, not an internal carrier state machine we would be guessing at.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from . import timestamps as ts


class CarrierMismatch(ValueError):
    """The tracking number and the carrier the user named are different carriers.

    A ``ValueError`` because that is what the route handlers already catch and
    turn into a 400, and because it is exactly what it is: two arguments that
    cannot both be right. It carries its own sentence, so nothing above it has
    to compose one.
    """


class CarrierStatus(str, Enum):
    DELIVERED = "delivered"
    ATTEMPTED_DELIVERY = "attempted_delivery"
    OUT_FOR_DELIVERY = "out_for_delivery"


@dataclass(frozen=True)
class CarrierClaim:
    """What the carrier's own tracking page told the recipient."""

    tracking_number: str
    carrier_name: str
    status: CarrierStatus
    claimed_at: dt.datetime
    # How much slack to allow around the claimed timestamp before deciding no
    # matching camera event exists. Carriers scan a status at the vehicle, not
    # at the door, so a tight window produces wrong "not consistent" verdicts;
    # too wide a window matches unrelated traffic. 40 minutes is the widest of
    # the six carrier windows in carriers.py and the default when the carrier is
    # unknown; carriers.py sets a narrower one per carrier, with its reason.
    window_minutes: int = 40

    # Provenance, all optional, all defaulted so a claim can still be built from
    # four typed fields. These are filled in when the claim came from a read of
    # the carrier's own page (tracking_reader.py) and they appear on the
    # evidence pack so a claims desk can see where each fact came from.
    carrier_code: str = "unknown"
    status_text: str = ""
    location_note: str = ""
    reference: str = ""
    timezone_label: str = "UTC"
    # False means the timezone was supplied by the user's browser rather than
    # printed on the tracking page. Tracking pages print a wall clock and no
    # offset, so this is usually False, and the pack says so rather than
    # implying the carrier stamped a zone it did not stamp.
    timezone_observed: bool = False
    # The delivery time exactly as the carrier printed it, before this app
    # normalised it. DOCUMENT-CRAFT rule 4.2.6: reformatting somebody else's
    # assertion looks like tampering even when it is not, so the original string
    # is kept and shown next to the normalised one.
    claimed_at_text: str = ""
    # The carrier's own default window, so the pack can say when the window in
    # force is not the one the carrier's scanning behaviour implies.
    default_window_minutes: int = 40

    def __post_init__(self) -> None:
        """Hold a timezone label only if it is shaped like one.

        `timezone_label` arrives from `timezone_printed`, a free-text field a
        multimodal model fills in off a photographed carrier page, or from the
        browser. Both are outside this app. A claim is the record every document
        is rendered from, so the label is settled here, once, rather than at each
        of the nine places that print a time. GUARD-STANDARD.md §1, rung S5.
        """
        object.__setattr__(self, "timezone_label", ts.safe_label(self.timezone_label))

    @property
    def window_adjusted(self) -> bool:
        return self.window_minutes != self.default_window_minutes

    def window_duration_text(self) -> str:
        """A window is two endpoints and a duration, never one of the three."""
        total = self.window_minutes * 2
        hours, minutes = divmod(total, 60)
        if hours and minutes:
            return f"{hours} h {minutes:02d} m"
        return f"{hours} h 00 m" if hours else f"{minutes} m"

    def window(self) -> tuple[dt.datetime, dt.datetime]:
        half = dt.timedelta(minutes=self.window_minutes)
        return self.claimed_at - half, self.claimed_at + half


class CarrierAdapter(ABC):
    """Interface a future carrier-data source would implement.

    Only one concrete adapter exists in this submission: ManualEntryAdapter.
    """

    @abstractmethod
    def fetch_claim(self, tracking_number: str) -> CarrierClaim:
        raise NotImplementedError


class ManualEntryAdapter(CarrierAdapter):
    """The floor: the person types what their own tracking page shows them.

    No network call, no scraping, no scope grant. This is what a third party can
    get without a merchant relationship or a restricted OAuth scope, and it is
    what the app falls back to when Bedrock is unreachable or a screenshot will
    not read.

    When ``window_minutes`` is left alone, the carrier registry sets it from the
    tracking number: a Royal Mail postie scans on the doorstep and an American
    ground carrier scans at the vehicle, so the same 40-minute window is too
    tight for one and too loose for the other. See ``carriers.py``.
    """

    def fetch_claim(
        self,
        tracking_number: str,
        carrier_name: str,
        status: CarrierStatus | str,
        claimed_at: dt.datetime,
        window_minutes: int | None = None,
        status_text: str = "",
        location_note: str = "",
        reference: str = "",
        timezone_label: str = "UTC",
        timezone_observed: bool = False,
        claimed_at_text: str = "",
    ) -> CarrierClaim:
        from .carriers import identify_carrier, resolve  # local: carriers.py imports this module

        if not tracking_number.strip():
            raise ValueError("Tracking number is required")
        if isinstance(status, str):
            status = CarrierStatus(status)
        number = tracking_number.strip()
        from .carrier_registry import UNKNOWN_CARRIER

        from_number = identify_carrier(number)
        from_name = resolve(carrier_name)
        named = from_name if from_name.code != UNKNOWN_CARRIER.code else None
        if from_number is not None and named is not None and from_number.code != named.code:
            # The number used to win silently while the user's name was kept for
            # display, so a Royal Mail claim was filed with USPS's 30-minute
            # window and printed USPS's sentence about walking routes to justify
            # it. `carrier_match.py` argues at length that the right answer to an
            # uncertain carrier is to decline and ask, "because a wrong carrier
            # sets a wrong checking window, and a wrong window produces a
            # confident finding about the wrong hour". This is that case, and it
            # was the one case it did not check.
            raise CarrierMismatch(
                f"You entered {named.display_name}, but {number} is "
                f"{from_number.display_name}'s published format "
                f"({from_number.number_shape}). One of the two is wrong, and "
                f"which one changes the checking window from "
                f"{named.default_window_minutes} minutes to "
                f"{from_number.default_window_minutes}. Correct the carrier or "
                f"the tracking number and send it again."
            )
        carrier = from_number or from_name
        return CarrierClaim(
            tracking_number=number,
            carrier_name=carrier_name.strip() or carrier.display_name,
            status=status,
            claimed_at=claimed_at,
            window_minutes=window_minutes if window_minutes is not None else carrier.default_window_minutes,
            carrier_code=carrier.code,
            status_text=status_text.strip(),
            location_note=location_note.strip(),
            reference=reference.strip(),
            timezone_label=timezone_label,
            timezone_observed=timezone_observed,
            claimed_at_text=claimed_at_text.strip(),
            default_window_minutes=carrier.default_window_minutes,
        )


class TrackingPageAdapter(CarrierAdapter):
    """The adapter the product leads with: read the carrier's own page.

    Deliberately thin. All the work is in ``tracking_reader.py``; this exists so
    that the page reader sits behind the same interface as manual entry and a
    hypothetical future carrier API, and so ``reconcile.py`` never learns where
    a claim came from.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def fetch_claim(
        self,
        tracking_number: str = "",
        *,
        text: str | None = None,
        image_bytes: bytes | None = None,
        timezone_offset_minutes: int = 0,
        timezone_label: str = "UTC",
    ) -> CarrierClaim:
        return self.read(
            text=text,
            image_bytes=image_bytes,
            timezone_offset_minutes=timezone_offset_minutes,
            timezone_label=timezone_label,
        ).to_claim()

    def read(self, **kwargs):
        """The reading itself, warnings and provenance included.

        Callers that want to show the user what was read before committing to a
        claim use this; ``fetch_claim`` is the interface-shaped path that throws
        away everything but the claim.
        """
        from .tracking_reader import read_tracking_page  # local: avoids an import cycle

        return read_tracking_page(runner=self._runner, **kwargs)
