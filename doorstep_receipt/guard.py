"""The language guard: one place every reader-visible string has to pass.

This product has exactly one thing it must never do. A doorbell camera can show
that nothing was recorded at a door during a window of time. It cannot show that
a carrier was dishonest, and it cannot show that a driver stayed away.

Until this module existed that rule was held by careful writing in
``reconcile.py``. That was enough while every sentence in the product was typed
by a person. It stopped being enough the moment two other sources of prose
appeared:

1. **A model.** ``tracking_reader.py`` and ``letter.py`` both put Bedrock output
   in front of a reader. A model asked to summarise a delivery dispute reaches
   for "the driver failed to deliver" without being asked to.
2. **The carrier, and the user.** A pasted tracking page is arbitrary text from
   a third party. An edited letter is arbitrary text from the user. Neither gets
   to put an accusation on a document this app signs.

So the rule is enforced mechanically, in one place, over every string that
reaches a reader, and the enforcement is tested rather than assumed. The rules
live in ``guard_rules.py``, the finding type and its explanations in
``guard_findings.py``, and the whole-page check in ``guard_document.py``.
"""

from __future__ import annotations

import re
import unicodedata

from .guard_findings import AccusatoryLanguage, GuardFinding, findings_summary
from .guard_rules import ACCUSATION, ALLOWED_PHRASES, COMPILED, OVERCLAIM

__all__ = [
    "ACCUSATION",
    "OVERCLAIM",
    "AccusatoryLanguage",
    "GuardFinding",
    "assert_clean",
    "findings_summary",
    "is_clean",
    "sanitise",
    "scan",
]

_MASK = "\u0000"

# Characters that stand in for the ones the rules in `guard_rules.py` are
# written with. Every rule here is a denylist, and a denylist only catches the
# exact bytes it was written with — while the things producing this text are a
# model, a carrier's web page and a person's keyboard, none of which has any
# obligation to use them. `the driver liеd` with a Cyrillic е, and `didn’t`
# with a curly apostrophe, both walked straight through.
#
# The table is strictly one character to one character, because `scan` reports
# the span of each finding back into the original string and a substitution
# that changed the length would move every offset after it.
_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‛": "'", "ʼ": "'", "ʻ": "'",
    "´": "'", "＇": "'", "′": "'",
    "“": '"', "”": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    " ": " ", " ": " ", "\t": " ",
    # Cyrillic and Greek homoglyphs: the deliberate evasion, as opposed to the
    # accidental one a word processor produces.
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "і": "i", "һ": "h", "ѕ": "s",
    "ο": "o", "α": "a", "ε": "e", "ρ": "p", "ν": "v",
})

# Handled in the second pass instead, because removing them changes offsets.
_INVISIBLE = re.compile(r"[​‌‍⁠﻿­]")
_LOOSE_APOSTROPHE = re.compile(r"\s*'\s*")
_SPACE_RUN = re.compile(r"[ ]{2,}")


def fold(text: str) -> str:
    """One character for one, so a finding's span still points at the original."""
    return text.translate(_FOLD)


def _hardened(text: str) -> str:
    """The lossy fold, for a second pass. Offsets are not preserved."""
    folded = unicodedata.normalize("NFKC", fold(text))
    folded = _INVISIBLE.sub("", folded)
    folded = _LOOSE_APOSTROPHE.sub("'", folded)
    return _SPACE_RUN.sub(" ", folded)


def _mask_allowed(text: str) -> str:
    """Blank the sanctioned phrases, preserving offsets so a finding's span
    still points at the right place in the original string."""
    masked = text
    lowered = text.lower()
    for phrase in ALLOWED_PHRASES:
        cursor = 0
        while True:
            idx = lowered.find(phrase, cursor)
            if idx == -1:
                break
            masked = masked[:idx] + (_MASK * len(phrase)) + masked[idx + len(phrase):]
            cursor = idx + len(phrase)
    return masked


def scan(text: str) -> list[GuardFinding]:
    """Every refused phrase in ``text``, in the order it appears.

    Two passes. The first runs over a one-to-one fold, so every finding carries
    a span that indexes the caller's own string. The second runs over a fold
    that also drops zero-width characters and closes up spaced apostrophes,
    which cannot preserve offsets; anything it finds that the first pass missed
    is reported against the whole string. That is coarse, and it is the right
    trade: a span is a convenience, and a phrase that reaches a filed document
    because somebody put a soft hyphen in the middle of it is not.
    """
    if not text:
        return []
    masked = _mask_allowed(fold(text))
    findings = [
        GuardFinding(category, rule, text[m.start():m.end()], m.start(), m.end())
        for category, rule, pattern in COMPILED
        for m in pattern.finditer(masked)
    ]

    hardened = _mask_allowed(_hardened(text))
    if hardened != masked:
        seen = {f.rule for f in findings}
        findings += [
            GuardFinding(category, rule, m.group(0), 0, len(text))
            for category, rule, pattern in COMPILED
            for m in pattern.finditer(hardened)
            if rule not in seen
        ]

    findings.sort(key=lambda f: (f.start, f.rule))
    return findings


def is_clean(text: str) -> bool:
    return not scan(text)


def assert_clean(text: str, where: str = "") -> str:
    """Return ``text`` unchanged, or raise AccusatoryLanguage.

    For the cases where a failure is a bug in this app rather than bad input:
    the deterministic sentences, and the fully assembled document.
    """
    findings = scan(text)
    if findings:
        raise AccusatoryLanguage(findings, where)
    return text


def sanitise(text: str, fallback: str, where: str = "") -> tuple[str, list[GuardFinding]]:
    """Return ``(text, [])`` when clean, else ``(fallback, findings)``.

    The path for anything a model, a carrier or the user wrote. The caller keeps
    the findings so the refusal can be shown on the page rather than swapped in
    silently. A guard that hides its own interventions is a guard nobody can
    audit, and this one is the product's central promise.
    """
    findings = scan(text)
    return (fallback, findings) if findings else (text, [])
