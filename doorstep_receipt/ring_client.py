"""Ring Partner API client.

Built against the documented Ring Partner API endpoint shapes and the official
starter (AmazonAppDev/ring-api-helloworld, scripts/ folder): the same base
URL, JSON:API envelope, and Authorization: Bearer header.

No Ring simulator is documented anywhere in Ring's own docs. This client is
exercised in tests with a mocked HTTP layer and fixtures shaped exactly like
the documented responses; it is never run against a live Ring account in this
submission. See README.md for the mock-at-the-boundary policy this follows.

HTTP plumbing lives in ring_http.py; the event model and errors live in
ring_events.py and ring_errors.py; commonly used names are re-exported here.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .ring_errors import ClipNotAvailable, RingAPIError, TIMESTAMP_NOT_FOUND
from .ring_events import RingEvent, event_from_jsonapi, parse_timestamp
from .ring_http import API_BASE, RingHTTPBase

__all__ = [
    "API_BASE",
    "RingClient",
    "RingEvent",
    "RingAPIError",
    "ClipNotAvailable",
    "TIMESTAMP_NOT_FOUND",
    "parse_timestamp",
]


class RingClient(RingHTTPBase):
    """The documented Ring read endpoints this product needs. Ring's only
    write endpoint (chime audio playback) has no use here and is omitted."""

    def list_devices(self) -> list[dict[str, Any]]:
        """GET /v1/devices"""
        data = self._get("/v1/devices")
        return data.get("data", [])

    def get_device_status(self, device_id: str) -> dict[str, Any]:
        """GET /v1/devices/{id}/status"""
        return self._get(f"/v1/devices/{device_id}/status").get("data", {})

    def get_event_history(
        self,
        device_id: str,
        event_types: str | None = None,
        since: dt.datetime | None = None,
        until: dt.datetime | None = None,
    ) -> list[RingEvent]:
        """GET /v1/history/devices/{id}/events

        Per PLATFORM-FACTS.md, results are time-gated to the moment consent was
        granted; there is no backfill. Callers should not expect events before that
        date regardless of the since/until window requested here.
        """
        params: dict[str, Any] = {}
        if event_types:
            params["event_types"] = event_types
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()
        data = self._get(f"/v1/history/devices/{device_id}/events", params=params)
        return [event_from_jsonapi(entry) for entry in data.get("data", [])]

    def download_image_snapshot(self, device_id: str, timestamp: dt.datetime) -> dict[str, Any]:
        """POST /v1/devices/{id}/media/image/download

        Snapshots are watermarked by Ring and the watermark cannot be turned off;
        that is a feature for this product (provenance), not a defect to work
        around.
        """
        body = {"timestamp": timestamp.isoformat()}
        response = self._post(f"/v1/devices/{device_id}/media/image/download", json_body=body)
        return response.json()

    def download_video_clip(
        self, device_id: str, timestamp: dt.datetime, duration_seconds: int = 60
    ) -> dict[str, Any]:
        """POST /v1/devices/{id}/media/video/download

        Raises ClipNotAvailable (416 TIMESTAMP_NOT_FOUND) when the account has no
        continuous-recording plan, or when the camera simply was not recording at
        that timestamp. Callers must catch this and render an honest "no clip"
        state; never suppress it.
        """
        if duration_seconds > 15 * 60:
            raise ValueError("Ring clip downloads are documented as capped at 15 minutes")
        body = {"timestamp": timestamp.isoformat(), "duration_seconds": duration_seconds}
        response = self._post(f"/v1/devices/{device_id}/media/video/download", json_body=body)
        return response.json()
