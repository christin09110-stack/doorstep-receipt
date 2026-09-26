"""Base HTTP plumbing for the Ring Partner API client.

Split out of ring_client.py: this module owns only "how do we make an
authenticated request and turn a non-2xx response into the right typed
exception". RingClient (in ring_client.py) adds the documented endpoints on
top of this.
"""

from __future__ import annotations

from typing import Any

import requests

from .ring_errors import ClipNotAvailable, RingAPIError, TIMESTAMP_NOT_FOUND

API_BASE = "https://api.amazonvision.com"


class RingHTTPBase:
    def __init__(self, token: str, session: requests.Session | None = None, base_url: str = API_BASE):
        self._token = token
        self._session = session or requests.Session()
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        response = self._session.get(url, headers=self._headers(), params=params, timeout=15)
        if not response.ok:
            self._raise_for_status(response)
        return response.json()

    def _post(self, path: str, json_body: dict[str, Any] | None = None) -> requests.Response:
        url = f"{self._base_url}{path}"
        response = self._session.post(url, headers=self._headers(), json=json_body, timeout=30)
        if not response.ok:
            self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        error_code = None
        message = response.text
        try:
            body = response.json()
            error_code = body.get("errors", [{}])[0].get("code")
            message = body.get("errors", [{}])[0].get("detail", message)
        except (ValueError, KeyError, IndexError):
            pass
        if response.status_code == 416 or error_code == TIMESTAMP_NOT_FOUND:
            raise ClipNotAvailable(response.status_code, error_code, message)
        raise RingAPIError(response.status_code, error_code, message)
