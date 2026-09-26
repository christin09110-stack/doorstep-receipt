"""What the model is told, and the facts it is told them about.

Split from ``letter.py`` on the same seam as ``guard_rules.py``: the prompt and
the schema are data a reviewer should be able to read without reading the code
around them, and this is the file to open to check what the model was actually
asked to do.

The system prompt is most of the work in this feature. It hands over the facts,
forbids every accusation ``guard.py`` forbids, and tells the model to stop at
what was observed. The guard then checks the answer anyway, because a prompt is
a request and a guard is a rule.
"""

from __future__ import annotations

from .reconcile import ReconciliationResult, Verdict

SYSTEM_PROMPT = """You draft short, formal letters from a customer to a retailer about a parcel
that has not arrived. You are given what a carrier's tracking page claimed and what a doorbell
camera recorded.

Absolute rules. Breaking any of these makes the letter unusable:
1. Never state what a driver, courier or carrier did or did not do. You do not know. A camera
   records the door, not a person's conduct.
2. Never use the words prove, proof, conclusive, lie, steal, theft, fraud, false, fail, negligent
   or blame, in any form.
3. Write only about what the carrier's tracking recorded and what the camera recorded. Where the
   two do not line up, say that they do not line up. Do not explain why.
4. Do not invent an order number, a price, an address, a date or a name. Use only the facts given.
5. Ask the retailer to resolve the order. Do not threaten, and do not cite a law.

Style: plain English, short sentences, no more than 200 words, no greeting placeholders beyond
"Dear Sir or Madam", and no closing name. Sign off with "Yours faithfully," and nothing after it.
"""

LETTER_TOOL = {
    "name": "record_letter",
    "description": "Record the drafted letter.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "A subject line under 80 characters."},
                "body": {"type": "string", "description": "The letter body."},
            },
            "required": ["subject", "body"],
        }
    },
}

_ASK = {
    Verdict.NOT_CONSISTENT: "I am asking you to resend the order or refund it.",
    Verdict.CONSISTENT: (
        "The camera record and the tracking line up, so I am asking you to check where the parcel "
        "was left before we go further."
    ),
    Verdict.INDETERMINATE: "I am asking you to look at this alongside your own record of the delivery.",
}


def _facts(result: ReconciliationResult, device_name: str, claim_id: str) -> str:
    claim = result.claim
    window_start, window_end = claim.window()
    fmt = "%Y-%m-%d %H:%M"
    lines = [
        f"Claim reference: {claim_id}",
        f"Carrier: {claim.carrier_name}",
        f"Tracking number: {claim.tracking_number}",
        f"Status on the carrier's tracking page: {claim.status.value.replace('_', ' ')}",
        f"Time the carrier's tracking gives: {claim.claimed_at.strftime(fmt)} {claim.timezone_label}",
        f"Camera checked: {device_name}",
        f"Window checked: {window_start.strftime(fmt)} to {window_end.strftime(fmt)} {claim.timezone_label}",
        f"Camera events inside that window: {len(result.matched_events)}",
    ]
    for event in result.matched_events:
        kind = "doorbell button press" if event.is_button_press else f"{event.event_type} {event.sub_type or ''}".strip()
        lines.append(f"  - {event.timestamp.strftime(fmt)}: {kind}")
    if claim.status_text:
        lines.append(f"Status line printed by the carrier: {claim.status_text}")
    if claim.location_note:
        lines.append(f"Location note printed by the carrier: {claim.location_note}")
    lines.append(f"Reconciliation sentence produced by the app: {result.summary_sentence}")
    return "\n".join(lines)
