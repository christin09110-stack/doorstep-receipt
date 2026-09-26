"""The Amazon Bedrock boundary: one class, one place, always optional.

Two things in this app want a model, and both of them are the hard half of the
product rather than decoration on the easy half:

- ``tracking_reader.py`` reads the carrier's own tracking page, from a
  screenshot or from pasted text, and pulls out the four facts the
  reconciliation engine needs. Ring gives this app the camera side cleanly and
  gives it nothing at all for the carrier side, and every route to carrier data
  is closed to a consumer app (SPEC.md, "What it deliberately does not do").
  A multimodal read of the page the user is already looking at is the route
  that does not require anybody's permission.
- ``letter.py`` drafts the letter the user sends to the retailer.

Three rules this module exists to enforce, from the upgrade brief:

1. **A timeout on every call.** Set on the botocore client, not on a wrapper,
   so a hung socket cannot outlive it.
2. **A fallback when Bedrock is unreachable.** Every failure, including a
   missing boto3, missing credentials, a throttle, a timeout and a model this
   account cannot invoke, arrives at the caller as one exception type:
   ``BedrockUnavailable``. Callers branch once.
3. **Tests that pass with the call stubbed.** ``StubRunner`` below is not a test
   fixture that lives in the test folder. It ships in the package, because
   ``DOORSTEP_BEDROCK=off`` uses it to run the whole app with no AWS account at
   all, which is also how this demo survives a conference wifi network.

Model choice is a **preference chain, not a hard-coded id**, and that is the
result of an hour lost. ``ListFoundationModels`` returns model ids this account
cannot invoke: ``anthropic.claude-sonnet-5`` is listed and ``Converse`` on it
returns ``AccessDeniedException``. A build that names one model and trusts the
listing is a build that dies in front of a judge on a model it never called.

So ``MODEL_PREFERENCE`` is tried in order and the first that answers is kept for
the process. Sonnet before Haiku because reading a photographed tracking page is
the task the whole feature rests on; inference profiles (``us.`` prefixed)
because the bare ids are not invokable here. ``DOORSTEP_BEDROCK_MODEL`` pins one
if you want to.
"""

from __future__ import annotations

import os
import time
from typing import Any

# Tried in order. Each one here has been called successfully from this machine;
# nothing in this list came from a model listing alone.
MODEL_PREFERENCE = (
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
)
DEFAULT_MODEL_ID = os.environ.get("DOORSTEP_BEDROCK_MODEL") or MODEL_PREFERENCE[0]
DEFAULT_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
DEFAULT_READ_TIMEOUT = float(os.environ.get("DOORSTEP_BEDROCK_TIMEOUT", "20"))
DEFAULT_CONNECT_TIMEOUT = 4.0
PROBE_CACHE_SECONDS = 60.0


class BedrockUnavailable(RuntimeError):
    """Bedrock could not be reached, or could not answer.

    Deliberately one type for every cause. A caller's job is to fall back, and
    the fallback is the same whether the credentials were missing or the socket
    timed out. The cause is kept on the instance for the friction log and for
    the line the page shows the user.
    """

    def __init__(self, reason: str, cause: BaseException | None = None):
        self.reason = reason
        self.cause = cause
        super().__init__(reason)


class BedrockRunner:
    """A thin, timeout-bounded wrapper over the Bedrock Converse API."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = DEFAULT_REGION,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        client: Any | None = None,
    ):
        self.model_id = model_id
        self.region = region
        self.read_timeout = read_timeout
        self._client = client
        self._probe: tuple[float, bool, str] | None = None
        # Only fall down the chain when the caller did not pin a model.
        self._chain = (
            list(MODEL_PREFERENCE)
            if not os.environ.get("DOORSTEP_BEDROCK_MODEL") and model_id in MODEL_PREFERENCE
            else [model_id]
        )

    @property
    def name(self) -> str:
        return self.model_id

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - exercised by the offline path
            raise BedrockUnavailable("boto3 is not installed", exc) from exc
        try:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                config=Config(
                    connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                    read_timeout=self.read_timeout,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        except Exception as exc:
            raise BedrockUnavailable(f"could not build a bedrock-runtime client: {exc}", exc) from exc
        return self._client

    def converse(
        self,
        system: str,
        content: list[dict[str, Any]],
        tool: dict[str, Any] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """One Converse call. Returns the response message's content blocks.

        ``tool`` forces structured output: pass a tool spec and the model is
        required to answer by calling it, which is how ``tracking_reader.py``
        gets a typed reading instead of prose it would then have to parse.
        """
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": content}],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }
        if tool is not None:
            kwargs["toolConfig"] = {
                "tools": [{"toolSpec": tool}],
                "toolChoice": {"tool": {"name": tool["name"]}},
            }
        started = time.monotonic()
        response, failures = None, []
        for candidate in self._chain:
            kwargs["modelId"] = candidate
            try:
                response = client.converse(**kwargs)
                self.model_id = candidate
                self._chain = [candidate] + [m for m in self._chain if m != candidate]
                break
            except Exception as exc:
                failures.append(f"{candidate}: {type(exc).__name__}")
                if type(exc).__name__ not in ("AccessDeniedException", "ResourceNotFoundException",
                                              "ValidationException"):
                    raise BedrockUnavailable(f"{type(exc).__name__}: {exc}", exc) from exc
        if response is None:
            raise BedrockUnavailable("no model in the preference chain answered: " + "; ".join(failures))
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        return {
            "blocks": blocks,
            "text": "".join(b.get("text", "") for b in blocks if "text" in b).strip(),
            "tool_input": next((b["toolUse"].get("input") for b in blocks if "toolUse" in b), None),
            "stop_reason": response.get("stopReason"),
            "usage": response.get("usage", {}),
            "latency_seconds": round(time.monotonic() - started, 2),
            "model_id": self.model_id,
        }

    def available(self) -> tuple[bool, str]:
        """Is Bedrock reachable right now? Cached, because the intake page asks
        on every render and the answer does not change every second."""
        now = time.monotonic()
        if self._probe and now - self._probe[0] < PROBE_CACHE_SECONDS:
            return self._probe[1], self._probe[2]
        try:
            self.converse(
                system="Answer with one word.",
                content=[{"text": "Reply with exactly: ok"}],
                max_tokens=8,
            )
            result = (True, f"{self.model_id} answered")
        except BedrockUnavailable as exc:
            result = (False, exc.reason)
        self._probe = (now, result[0], result[1])
        return result


class StubRunner(BedrockRunner):
    """A runner that never calls AWS.

    Selected by ``DOORSTEP_BEDROCK=off``, and used by every test that exercises
    a Bedrock code path. ``replies`` is a queue of canned Converse responses; an
    empty queue raises ``BedrockUnavailable``, which is how the offline
    behaviour is tested without unplugging anything.
    """

    def __init__(self, replies: list[dict[str, Any]] | None = None, model_id: str = "stub-model"):
        super().__init__(model_id=model_id, client=object())
        self.replies = list(replies or [])
        self.calls: list[dict[str, Any]] = []

    def converse(self, system, content, tool=None, max_tokens=1024, temperature=0.0):
        self.calls.append({"system": system, "content": content, "tool": tool})
        if not self.replies:
            raise BedrockUnavailable("stub runner has no reply queued")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return {
            "blocks": reply.get("blocks", []),
            "text": reply.get("text", ""),
            "tool_input": reply.get("tool_input"),
            "stop_reason": reply.get("stop_reason", "end_turn"),
            "usage": reply.get("usage", {}),
            "latency_seconds": 0.0,
            "model_id": self.model_id,
        }

    def available(self):
        return (bool(self.replies), "stub runner")


_DEFAULT: BedrockRunner | None = None


def default_runner() -> BedrockRunner:
    """The process-wide runner. ``DOORSTEP_BEDROCK=off`` gets a stub instead."""
    global _DEFAULT
    if _DEFAULT is None:
        if os.environ.get("DOORSTEP_BEDROCK", "").lower() in ("off", "0", "false", "no"):
            _DEFAULT = StubRunner(model_id="disabled (DOORSTEP_BEDROCK=off)")
        else:
            _DEFAULT = BedrockRunner()
    return _DEFAULT


def set_default_runner(runner: BedrockRunner | None) -> None:
    """Swap the process-wide runner. Used by tests and by app startup."""
    global _DEFAULT
    _DEFAULT = runner
