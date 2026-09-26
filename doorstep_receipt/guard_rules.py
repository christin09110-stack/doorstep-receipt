"""The refused-language rules themselves, and the phrases exempted from them.

Split from guard.py following this package's existing convention (ring_client /
ring_http / ring_events / ring_errors): one module owns the data, another owns
the behaviour. Keeping the rules in a file of their own means the list a
reviewer has to read to audit the product's central promise is 60 lines of
patterns with nothing else in it.

Two categories:

- ``ACCUSATION``: asserts what a person did or did not do, or names them as
  dishonest. This is the rule from SPEC.md and from PLATFORM-FACTS.md's Ring
  section, where Ring's own classifier is documented labelling a motorised
  wheelchair a "package". If the classification is not safe to accuse on,
  neither is the absence of one.
- ``OVERCLAIM``: asserts that the record settles a question it cannot settle.
  "Proves", "conclusively", "must have". A weaker rule with the same failure
  mode: a sentence the evidence does not support.
"""

from __future__ import annotations

import re

ACCUSATION = "accusation"
OVERCLAIM = "overclaim"

# Phrases that trip a rule below but are the product's own deliberate wording.
# Masked out before scanning rather than weakening a pattern, so every rule
# stays exactly as strict for every other sentence in the app.
#
#   "not conclusive"     the INDETERMINATE stamp reads "On record, not
#                        conclusive". It says the opposite of an overclaim and
#                        contains the word anyway.
#   "proof of delivery"  a carrier's own name for the artefact. Quoted as their
#                        term, never asserted as ours.
ALLOWED_PHRASES: tuple[str, ...] = (
    "not conclusive",
    "proof of delivery",
)

RULES: tuple[tuple[str, str, str], ...] = (
    # (category, rule name, pattern)
    (ACCUSATION, "dishonesty", r"\b(lie|lied|lies|lying|liar|untruthful|dishonest\w*|deceit\w*|deceptive|deceived)\b"),
    (ACCUSATION, "theft", r"\b(stole|stolen|steal|stealing|theft|thief|thieves|pilfer\w*)\b"),
    (ACCUSATION, "fraud", r"\b(fraud\w*|scam\w*|fabricat\w*|falsif\w*|forged|misrepresent\w*|bogus)\b"),
    (ACCUSATION, "fault", r"\b(guilty|culpab\w*|negligen\w*|at fault|to blame|blamed|blaming|liable)\b"),
    (ACCUSATION, "false-claim", r"\bfalse(ly)?\b(?!\s*positive)"),
    (
        ACCUSATION,
        "asserted-omission",
        r"\b(?:did\s*n[o']t|didn'?t|never|failed\s+to|neglected\s+to|refused\s+to)\s+"
        r"(?:actually\s+|ever\s+|even\s+)?"
        r"(?:come|came|arrive[ds]?|deliver(?:ed)?|attempt(?:ed)?|knock(?:ed)?|ring|rang"
        r"|show(?:ed)?\s*up|turn(?:ed)?\s*up|visit(?:ed)?)\b",
    ),
    (
        ACCUSATION,
        "asserted-absence-of-person",
        r"\b(?:no\s*-?\s*one|nobody|no\s+driver|no\s+courier|no\s+carrier|no\s+person)\s+"
        r"(?:ever\s+)?(?:came|arrived|delivered|knocked|rang|attempted|showed|turned)\b",
    ),
    (
        ACCUSATION,
        "named-actor-verdict",
        r"\b(?:the\s+)?(?:driver|courier|carrier|delivery\s+(?:driver|person|man|agent)|postman|postal\s+worker)\s+"
        r"(?:\w+\s+){0,2}?(?:lied|stole|invented|faked|skipped|ignored|bypassed)\b",
    ),
    (ACCUSATION, "faked-scan", r"\b(fake[ds]?|faking)\b"),
    (OVERCLAIM, "proof", r"\b(prove[sdn]?|proving|proof)\b"),
    (
        OVERCLAIM,
        "certainty",
        r"\b(conclusive\w*|definitiv\w*|indisputab\w*|irrefutab\w*|beyond\s+doubt|without\s+doubt)\b",
    ),
    (OVERCLAIM, "inference", r"\b(must\s+have\s+(?:been|come|gone|happened)|clearly\s+shows|demonstrates\s+that)\b"),
)

COMPILED: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (category, name, re.compile(pattern, re.IGNORECASE)) for category, name, pattern in RULES
)
