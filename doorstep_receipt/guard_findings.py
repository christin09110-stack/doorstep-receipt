"""What a refusal is, and how it explains itself to the person who caused it.

Split from the scanner in ``guard.py`` because a finding has a job the scanner
does not: it has to be readable by somebody who just had their sentence refused
and wants to know why. The explanation is not an error message, it is the
product's argument, and it is the thing a judge will read when the refusal
appears on screen.

Two categories, which differ only in the sentence they produce:

- ``accusation`` states what a person did or did not do. A camera record cannot
  support that.
- ``overclaim`` states that the record settles the question. This pack reports
  what was observed and leaves the conclusion to the reader.
"""

from __future__ import annotations

from dataclasses import dataclass

from .guard_rules import ACCUSATION


@dataclass(frozen=True)
class GuardFinding:
    """One phrase the guard refused, and why."""

    category: str
    rule: str
    phrase: str
    start: int
    end: int

    def explain(self) -> str:
        """Why it was refused, for the page. Names the rule, quotes nothing.

        This used to open with the refused phrase in quotation marks, on the
        grounds that a guard which hides its own interventions is one nobody
        can audit. That instinct is right and the refusal still shows; what
        was wrong was the payload. A rejection is model output with a frame
        around it, not metadata, and ``"the driver lied" states what a person
        did or did not do`` delivers the accusation to the reader inside the
        sentence explaining that it was blocked. The phrase stays in
        ``detail()``, which goes to the log and to ``str(AccusatoryLanguage)``,
        where a developer is and a claims adjuster is not.
        """
        if self.category == ACCUSATION:
            return (
                "It states what a person did or did not do. "
                "A camera record cannot support that."
            )
        return (
            "It claims the record settles the question. "
            "This pack reports what was observed and leaves the conclusion to the reader."
        )

    def detail(self) -> str:
        """The developer's version, with the refused text. Never rendered."""
        return f"{self.rule}: {self.phrase!r} at {self.start}-{self.end}"


class AccusatoryLanguage(ValueError):
    """Raised when text that must be non-accusatory is not."""

    def __init__(self, findings: list[GuardFinding], where: str = ""):
        self.findings = findings
        self.where = where
        joined = "; ".join(f.phrase for f in findings)
        location = f" in {where}" if where else ""
        super().__init__(f"Refused language{location}: {joined}")


def findings_summary(findings: list[GuardFinding]) -> str:
    """One sentence a reader can understand, for the page."""
    if not findings:
        return ""
    if len(findings) == 1:
        return findings[0].explain()
    rules = ", ".join(sorted({f.rule for f in findings}))
    return (
        f"{len(findings)} phrases were refused, under these rules: {rules}. This pack "
        "reports what the camera recorded and does not state what a person did."
    )
