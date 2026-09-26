"""The fixed wording: what the user gets when nothing else works.

Clean by construction, because it is fixed text with the claim's own values
substituted, and it is the fallback for every path that fails: Bedrock
unreachable, a draft the guard refused, or a user who wants the plain version.

It is written to be sendable exactly as it stands. A fallback that reads as a
stub is a fallback nobody uses, and the whole point of having one is that the
demo still works with the network unplugged.
"""

from __future__ import annotations

from . import guard
from .letter_prompt import _ASK
from .reconcile import ReconciliationResult
from .records import ClaimLetter

SOURCE_TEMPLATE = "template"


def template_letter(result: ReconciliationResult, device_name: str, claim_id: str) -> ClaimLetter:
    """The fixed wording. Clean by construction, and the fallback for every
    path that fails. Written to be sendable as it stands, not as a stub."""
    claim = result.claim
    window_start, window_end = claim.window()
    fmt = "%Y-%m-%d at %H:%M"
    body = "\n\n".join(
        [
            "Dear Sir or Madam,",
            (
                f"I am writing about tracking number {claim.tracking_number} "
                f"({claim.carrier_name}), which your carrier's tracking page records as "
                f"'{claim.status.value.replace('_', ' ')}' on "
                f"{claim.claimed_at.strftime(fmt)} {claim.timezone_label}."
            ),
            (
                f"I have a doorbell camera at the address, on the {device_name}. "
                f"{result.summary_sentence}"
            ),
            (
                f"I have attached an evidence pack setting out the camera's record for the window "
                f"{window_start.strftime(fmt)} to {window_end.strftime(fmt)} {claim.timezone_label}, "
                f"including the event log and a file manifest with a checksum for each item."
            ),
            _ASK[result.verdict],
            f"My claim reference for this is {claim_id}.",
            "Yours faithfully,",
        ]
    )
    subject = f"Order not received: tracking {claim.tracking_number} ({claim.carrier_name})"
    return ClaimLetter(body=guard.assert_clean(body, "template letter"), subject=subject, source=SOURCE_TEMPLATE)
