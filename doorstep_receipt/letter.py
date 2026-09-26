"""The letter the user actually sends, drafted and then handed over for editing.

The evidence pack is the attachment. The letter is the covering note, and it is
the part people stall on: the research behind this app found that a third of
people with a delivery problem take no action, and "I do not know what to write"
is a cheaper barrier to remove than any of the others.

Two paths produce a letter, and both end at the same guard:

- **Bedrock** drafts it from the facts of the claim. The system prompt below is
  most of the work: it hands the model the facts, forbids it every accusation
  the guard forbids, and tells it to stop at what was observed.
- **A template** produces it when Bedrock is unreachable, when the model's draft
  is refused by the guard, or when the user asks for the plain version. The
  template is fixed text with the claim's own values substituted, so it is
  clean by construction.

The interesting case is the middle one. A model that writes "the driver never
came" does not get quietly corrected: the draft is dropped, the template is used
instead, and the page says the drafted wording was refused and why. A guard that
hides its interventions is a guard nobody can audit, and this app's whole claim
on a reader's trust is that its language rule is real.

The user then edits whatever they were given. Their edit goes through the same
guard on save, and is refused with the same explanation, because a letter with
this app's evidence pack attached is a letter with this app's name on it.
"""

from __future__ import annotations

import datetime as dt

from . import guard
from .bedrock import BedrockRunner, BedrockUnavailable, default_runner
from .letter_prompt import LETTER_TOOL, SYSTEM_PROMPT, _facts
from .letter_template import SOURCE_TEMPLATE, template_letter
from .reconcile import ReconciliationResult
from .records import ClaimLetter, findings_note

SOURCE_BEDROCK = "bedrock"
SOURCE_USER = "user"

__all__ = ["accept_user_edit", "draft_letter", "template_letter"]

def draft_letter(
    result: ReconciliationResult,
    device_name: str,
    claim_id: str,
    runner: BedrockRunner | None = None,
) -> ClaimLetter:
    """Bedrock first, template second, guard over both."""
    fallback = template_letter(result, device_name, claim_id)
    runner = runner or default_runner()
    try:
        response = runner.converse(
            system=SYSTEM_PROMPT,
            content=[{"text": "Draft the letter from these facts.\n\n" + _facts(result, device_name, claim_id)}],
            tool=LETTER_TOOL,
            max_tokens=700,
            temperature=0.2,
        )
    except BedrockUnavailable as exc:
        fallback.created_at = dt.datetime.now(dt.timezone.utc)
        fallback.guard_note = f"The drafting model was not reachable ({exc.reason}). Standard wording used."
        return fallback

    fields = response.get("tool_input") or {}
    body = str(fields.get("body") or "").strip()
    subject = str(fields.get("subject") or "").strip() or fallback.subject
    if not body:
        fallback.guard_note = "The drafting model returned no letter. Standard wording used."
        return fallback

    kept_body, body_findings = guard.sanitise(body, fallback.body, where="drafted letter body")
    kept_subject, subject_findings = guard.sanitise(subject, fallback.subject, where="drafted letter subject")
    findings = body_findings + subject_findings
    if findings:
        return ClaimLetter(
            body=fallback.body,
            subject=fallback.subject,
            source=SOURCE_TEMPLATE,
            guard_note=(
                "The drafted wording was refused by the language check and the standard wording was "
                f"used instead. {guard.findings_summary(findings)} (rules: {findings_note(findings)})"
            ),
        )
    return ClaimLetter(body=kept_body, subject=kept_subject, source=SOURCE_BEDROCK)


def accept_user_edit(body: str, subject: str) -> ClaimLetter:
    """Take the user's edit, or refuse it with a reason they can act on."""
    findings = guard.scan(body) + guard.scan(subject)
    if findings:
        raise guard.AccusatoryLanguage(findings, "your edit")
    return ClaimLetter(body=body.strip(), subject=subject.strip(), source=SOURCE_USER)
