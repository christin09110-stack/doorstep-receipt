"""Three bases: RECORDED, REPORTED, INFERRED. Printed beside every assertion.

This is the observed-versus-inferred rule that the language guard already
enforces in words, made structural, and it is not this app's invention. CPR
Practice Direction 32 paragraph 18.2 has required a witness statement in England
and Wales to indicate which of its statements are made from the witness's own
knowledge and which are matters of information or belief, and to give the source
for the latter, since 1999. Marking every row is compliance with a filing
convention a claims handler will recognise, not a scruple this product invented.

| Marker     | Meaning                                    | Obligation it carries           |
|------------|--------------------------------------------|---------------------------------|
| RECORDED   | Came from the device, with a timestamp     | Must trace to an event or file  |
| REPORTED   | A person or a third-party system asserted  | Must name the source and when   |
| INFERRED   | This software computed it from the others  | Must name the rule and window   |

The marker prints as a word, never as a colour, because the document will be
photocopied in greyscale and read by somebody who may not see colour at all.

The one that decides this product's honesty is section 7.5 of DOCUMENT-CRAFT.md:
**a device classification is REPORTED, by the device, never RECORDED.** Ring's
classifier has been documented labelling a motorised wheelchair a package. That
an event exists at 14:13 is recorded. That the thing in it was a person is the
manufacturer's automatic classification, unchecked by anybody, and this document
prints it as the manufacturer's assertion.
"""

from __future__ import annotations

from dataclasses import dataclass

RECORDED = "RECORDED"
REPORTED = "REPORTED"
INFERRED = "INFERRED"

OBLIGATIONS = {
    RECORDED: "Traceable to an event identifier or a file digest listed in the manifest.",
    REPORTED: "Asserted by the named source at the stated time. Not checked by this app.",
    INFERRED: "Computed by this app from the rule, window and coverage stated beside it.",
}


@dataclass(frozen=True)
class Basis:
    """One marked assertion: the marker, its source, and the exhibit it cites."""

    marker: str
    source: str = ""
    exhibit: str = ""

    def __post_init__(self) -> None:
        if self.marker not in OBLIGATIONS:
            raise ValueError(f"Unknown basis marker: {self.marker}")
        if self.marker == REPORTED and not self.source:
            raise ValueError("A REPORTED assertion must name its source. An unattributed report "
                             "reads to a claims handler exactly like a fabrication.")

    @property
    def obligation(self) -> str:
        return OBLIGATIONS[self.marker]


def recorded(exhibit: str = "") -> Basis:
    return Basis(RECORDED, exhibit=exhibit)


def reported(source: str, exhibit: str = "") -> Basis:
    return Basis(REPORTED, source=source, exhibit=exhibit)


def inferred(rule: str, exhibit: str = "") -> Basis:
    return Basis(INFERRED, source=rule, exhibit=exhibit)


DEVICE_CLASSIFICATION_NOTE = (
    "This is the manufacturer's automatic classification of the event. It has not been "
    "checked by a person and it is not a statement that a person was present. Ring's "
    "classifier has been documented labelling a motorised wheelchair a package."
)
