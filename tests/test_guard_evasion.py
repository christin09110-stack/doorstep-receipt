"""The guard, against text its rules were not written with.

``guard_rules.py`` is a denylist of regexes, and the existing tests feed it the
phrases it already contains. That proves the list contains the words in the
list. It cannot find the failure that matters, which is that the three things
producing text here — a model, a carrier's web page and a person's keyboard —
have no obligation to use the exact characters somebody typed into the rules.

Measured before the fix: ``the driver liеd about it`` with a Cyrillic е, ``the
courier stоle it`` with a Cyrillic о, and ``the driver didn’t deliver it`` with
a curly apostrophe all scanned clean. The first two are deliberate evasion; the
third is what any word processor produces by default, which makes it the one
that would actually have happened.
"""

from __future__ import annotations

import pytest

from doorstep_receipt import guard

CLEAN = "no arrival was recorded at the door during this window"


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("the driver lied about it", "the plain form, which always worked"),
        ("the driver liеd about it", "Cyrillic e"),
        ("the courier stоle it", "Cyrillic o"),
        ("the cоurier stole it", "Cyrillic o in the noun"),
        ("the driver didn’t deliver it", "curly apostrophe"),
        ("the driver didnʼt deliver it", "modifier letter apostrophe"),
        ("the driver did­n't deliver it", "soft hyphen inside the word"),
        ("the driver li​ed about it", "zero-width space inside the word"),
        ("the driver  lied about it", "doubled space"),
        ("the driver lied about it", "non-breaking space"),
    ],
)
def test_a_character_substitution_does_not_walk_past_the_rules(text, why):
    findings = guard.scan(text), why
    assert findings[0], f"nothing was refused: {why}"


def test_the_span_of_a_normal_finding_still_indexes_the_original_string():
    """The fold is one character for one, so a caller can still highlight."""
    text = "The record shows the driver lied about the delivery."
    finding = guard.scan(text)[0]

    assert text[finding.start:finding.end] == finding.phrase


def test_a_lossy_match_reports_a_coarse_span_rather_than_a_wrong_one():
    """Dropping a zero-width character moves every offset after it, so the
    second pass reports the whole string rather than a span that would point
    at the wrong words."""
    text = "the driver li​ed about it"
    findings = guard.scan(text)

    assert findings
    assert all(f.start == 0 and f.end == len(text) for f in findings)


@pytest.mark.parametrize(
    "text",
    [
        CLEAN,
        "Delivered, left with a neighbour at number 12",
        "The camera recorded a button press at 14:11 UTC (UTC+00:00).",
        "No event of type button_press falls inside the checked window.",
        "The tracking page printed no timezone, so this one came from the browser.",
        "The parcel was left in the porch, out of this camera's field of view.",
    ],
)
def test_the_sentences_this_product_exists_to_write_still_pass(text):
    """A guard that refuses everything is a wall, and a wall means the fallback
    is the only path anybody ever exercises."""
    assert guard.scan(text) == []


def test_folding_is_only_for_comparison_and_never_changes_what_is_kept():
    kept, findings = guard.sanitise("Delivered — left at the door", "", where="t")

    assert findings == []
    assert kept == "Delivered — left at the door"  # em dash survives


def test_fold_is_length_preserving():
    """If this stops being true, every finding's span silently becomes wrong."""
    for raw in ["a’b", "a—b", "a b", "аео", "plain"]:
        assert len(guard.fold(raw)) == len(raw)
