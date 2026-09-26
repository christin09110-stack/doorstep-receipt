"""Ring Partner API error types.

Split out of ring_client.py to keep each file focused: this module owns only
the typed exceptions a caller needs to branch on, nothing else.
"""

from __future__ import annotations

# Ring's own documentation is explicit that clip retrieval without a continuous
# recording plan returns this exact error code. We surface it as a typed
# exception so callers (and the evidence pack) can render an honest "no clip
# available" state instead of crashing or silently showing nothing.
TIMESTAMP_NOT_FOUND = "TIMESTAMP_NOT_FOUND"


class RingAPIError(Exception):
    """Raised for any non-2xx response from the Ring Partner API."""

    def __init__(self, status_code: int, error_code: str | None, message: str):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(f"Ring API error {status_code} ({error_code}): {message}")


class ClipNotAvailable(RingAPIError):
    """Raised for the documented 416 TIMESTAMP_NOT_FOUND case.

    Per PLATFORM-FACTS.md: "Clip retrieval ... needs a paid continuous-recording
    plan. Without one it returns 416 TIMESTAMP_NOT_FOUND." This is not a bug in
    the caller; it is a plan limitation the evidence pack has to represent
    honestly.
    """
