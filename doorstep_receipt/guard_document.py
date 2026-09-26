"""The document-level check: scan the assembled page, not only its inputs.

``guard.py`` checks a string. This checks a rendered page, which is a different
job with a different failure mode. Every string in this app is guarded where it
enters a record, so this should never fire. It is here because "should never
fire" is how things ship broken, and a test doctors a reconciliation result to
make it fire, so the wiring is shown to be live rather than asserted.

The tag stripping is deliberately crude. It does not need to be a parser. It
needs to catch a sentence that reached the page.
"""

from __future__ import annotations

import re

from .guard import assert_clean

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def visible_text(html: str) -> str:
    """The reader-visible text of a rendered page, for the document-level check.

    Deliberately crude: strip tags, collapse whitespace. It does not need to be
    a parser. It needs to catch a sentence that reached the page.
    """
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", _BLOCK_RE.sub(" ", html))).strip()


def assert_document_clean(html: str, where: str = "rendered document") -> str:
    """The last line of defence: scan the assembled page, not only its inputs.

    Every string is guarded where it enters a record, so this should never fire.
    It exists because "should never fire" is how bugs ship. A test doctors a
    reconciliation result to make it fire, so the wiring is shown to be live.
    """
    assert_clean(visible_text(html), where)
    return html
