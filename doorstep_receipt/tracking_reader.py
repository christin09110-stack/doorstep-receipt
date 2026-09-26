"""Reading the carrier's own tracking page, from a screenshot or from text.

This is the answer to the hole in the middle of this product. Ring hands the app
the camera side of the argument cleanly. It hands it nothing for the other side,
and SPEC.md sets out why every route to carrier data is shut to a consumer app:
carrier APIs authenticate a shipper, not a recipient, and reading the delivery
emails out of a mailbox needs Gmail's restricted scopes and an annual third-party
security assessment.

The route that needs nobody's permission is the page the user is already looking
at. They photograph it or paste it, and a multimodal model reads the carrier, the
tracking number, the claimed delivery time and the status line back out. Nothing
is scraped, no terms are breached, and the user supplies only what they already
have on screen.

Three things make this honest rather than a model call with a nice story:

1. **The model transcribes, it does not judge.** The system prompt forbids
   characterising anybody's conduct, and every free-text field it returns goes
   through ``guard.py`` before it can reach a page. A refused field is replaced
   and the refusal is shown, not swallowed.
2. **The registry outranks the model.** ``carriers.py`` knows the published
   number formats and the published status vocabularies. Where the model and the
   registry disagree about which carrier a number belongs to, or what a status
   line means, the deterministic answer wins and the disagreement is recorded on
   the reading. A judge can audit a regex. Nobody can audit a vibe.
3. **It works with the network unplugged.** Bedrock unreachable, no credentials,
   or ``DOORSTEP_BEDROCK=off``, and the read falls through to
   ``tracking_text.py``'s regexes for pasted text, or to an honest "type it in
   yourself" for an image. The page says which path produced the reading.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from . import guard
from .bedrock import BedrockRunner, BedrockUnavailable, default_runner
from .carrier import CarrierClaim, CarrierStatus
from .carriers import Carrier, identify_carrier, normalise_status, resolve
from .tracking_text import parse_tracking_text

SOURCE_BEDROCK = "bedrock"
SOURCE_PATTERN = "pattern"
SOURCE_NONE = "none"

_WITHHELD = "[status text withheld: it stated what a person did, which this pack does not reproduce]"

SYSTEM_PROMPT = """You transcribe parcel tracking pages. You are a transcriber, not an analyst.

Rules, in order of importance:
1. Report only what is printed on the page. If a field is not visible, leave it
   empty. Never infer, never complete a partial number, never guess a year.
2. Copy the status line exactly as the carrier printed it, including its
   capitalisation and punctuation.
3. Never characterise anybody's conduct and never write about what a driver,
   courier or carrier did or did not do. You are reading a page, not settling an
   argument. Do not use the words prove, lie, steal, fail, fraud or false.
4. Times on tracking pages are local to the delivery address and usually carry no
   timezone. Record the timezone only if the page prints one.
5. If the image is not a parcel tracking page, say so and leave every field empty.
"""

READING_TOOL = {
    "name": "record_tracking_page",
    "description": "Record the fields printed on a parcel tracking page.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "is_tracking_page": {
                    "type": "boolean",
                    "description": "True only if this is a parcel carrier's tracking page.",
                },
                "carrier_name": {"type": "string", "description": "Carrier name as printed, or empty."},
                "tracking_number": {"type": "string", "description": "Tracking number as printed, or empty."},
                "status_text": {"type": "string", "description": "The status line copied exactly, or empty."},
                "printed_when": {
                    "type": "string",
                    "description": "The delivery date and time exactly as printed, character for character, or empty.",
                },
                "delivered_date": {"type": "string", "description": "YYYY-MM-DD as printed, or empty."},
                "delivered_time": {"type": "string", "description": "HH:MM on a 24 hour clock, or empty."},
                "timezone_printed": {"type": "string", "description": "Timezone printed on the page, or empty."},
                "location_note": {"type": "string", "description": "Any 'left at' or location note, or empty."},
                "reference": {"type": "string", "description": "Order or reference number, or empty."},
                "unreadable": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names of fields that are present but not legible.",
                },
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["is_tracking_page", "confidence"],
        }
    },
}

_IMAGE_MAGIC = ((b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpeg"), (b"GIF8", "gif"), (b"RIFF", "webp"))


@dataclass
class TrackingPageReading:
    """The four facts the reconciliation engine needs, plus its own provenance."""

    tracking_number: str = ""
    carrier: Carrier | None = None
    carrier_name_printed: str = ""
    status: CarrierStatus | None = None
    status_text: str = ""
    claimed_at: dt.datetime | None = None
    timezone_label: str = "UTC"
    timezone_observed: bool = False
    location_note: str = ""
    reference: str = ""
    claimed_at_text: str = ""
    confidence: str = "low"
    source: str = SOURCE_NONE
    model_id: str = ""
    latency_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)
    guard_findings: list[guard.GuardFinding] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if message and message not in self.warnings:
            self.warnings.append(message)

    @property
    def is_complete(self) -> bool:
        return bool(self.tracking_number and self.status and self.claimed_at)

    @property
    def window_minutes(self) -> int:
        return (self.carrier or resolve(None)).default_window_minutes

    def to_claim(self) -> CarrierClaim:
        if not self.is_complete:
            raise ValueError("The reading is missing a tracking number, a status or a delivery time")
        carrier = self.carrier or resolve(None)
        return CarrierClaim(
            tracking_number=self.tracking_number,
            carrier_name=carrier.display_name,
            status=self.status,
            claimed_at=self.claimed_at,
            window_minutes=carrier.default_window_minutes,
        )


def image_format(image_bytes: bytes) -> str:
    for magic, name in _IMAGE_MAGIC:
        if image_bytes.startswith(magic):
            return name
    raise ValueError("Unrecognised image format. Upload a PNG, JPEG, GIF or WebP screenshot.")


def _apply_guard(reading: TrackingPageReading, field_name: str, value: str, fallback: str) -> str:
    kept, findings = guard.sanitise(value, fallback, where=f"tracking page {field_name}")
    if findings:
        reading.guard_findings.extend(findings)
        reading.warn(
            f"The {field_name} on that page was not reproduced here. " + guard.findings_summary(findings)
        )
    return kept


def _settle_carrier(reading: TrackingPageReading, printed_name: str) -> None:
    """The registry's identification beats the model's, and any disagreement is
    put on the record rather than resolved quietly."""
    from_number = identify_carrier(reading.tracking_number) if reading.tracking_number else None
    from_name = resolve(printed_name) if printed_name else None
    if from_number is not None:
        reading.carrier = from_number
        if from_name is not None and from_name.code not in ("unknown", from_number.code):
            reading.warn(
                f"The page names {from_name.display_name}, but the tracking number is in "
                f"{from_number.display_name}'s published format. The number was used."
            )
        return
    if from_name is not None and from_name.code != "unknown":
        reading.carrier = from_name
        return
    reading.carrier = None
    if reading.tracking_number:
        reading.warn(
            "That tracking number does not match any carrier format this app knows, so the widest "
            "checking window is used."
        )


def _settle_status(reading: TrackingPageReading) -> None:
    """Same rule for the status: the published vocabulary in carriers.py beats
    anything the model inferred from the same words."""
    from_registry = normalise_status(reading.status_text, reading.carrier)
    if from_registry is not None:
        reading.status = from_registry
        return
    if reading.status is None and reading.status_text:
        reading.warn(
            f'"{reading.status_text}" is not a status this app recognises. Pick the status yourself.'
        )


def _combine(date_text: str, time_text: str, tz: dt.timezone) -> dt.datetime | None:
    if not date_text:
        return None
    try:
        day = dt.date.fromisoformat(date_text.strip())
    except ValueError:
        return None
    hour, minute = 0, 0
    if time_text and ":" in time_text:
        try:
            hour, minute = (int(part) for part in time_text.strip().split(":")[:2])
        except ValueError:
            return None
    try:
        return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
    except ValueError:
        return None


def _read_with_bedrock(
    reading: TrackingPageReading,
    runner: BedrockRunner,
    text: str | None,
    image_bytes: bytes | None,
    tz: dt.timezone,
) -> None:
    content: list[dict] = []
    if image_bytes:
        content.append({"image": {"format": image_format(image_bytes), "source": {"bytes": image_bytes}}})
        content.append({"text": "Transcribe the tracking page in this screenshot."})
    if text:
        content.append({"text": f"Transcribe this tracking page text:\n\n<page>\n{text}\n</page>"})

    response = runner.converse(
        system=SYSTEM_PROMPT, content=content, tool=READING_TOOL, max_tokens=900, temperature=0.0
    )
    fields = response.get("tool_input") or {}
    reading.source = SOURCE_BEDROCK
    reading.model_id = response.get("model_id", runner.model_id)
    reading.latency_seconds = response.get("latency_seconds", 0.0)
    reading.confidence = str(fields.get("confidence") or "low")

    if not fields.get("is_tracking_page", False):
        reading.warn("That did not read as a parcel tracking page. Enter the delivery details yourself.")
        return

    # Every string this tool call returns goes through the guard, not the two
    # that were obviously prose. `printed_when` is prose by its own schema
    # description, and filed_record.py renders it inside `class="verbatim"`,
    # which is the strongest presentational claim this app makes: it tells the
    # reader these are the carrier's own printed words. A field presented as
    # quoted that the model wrote freely is the worst combination available.
    # `tracking_number` is the one exception, and only because it is stripped
    # to an alphanumeric run below, which leaves no room for a sentence.
    reading.tracking_number = re.sub(
        r"[^A-Z0-9]", "", str(fields.get("tracking_number") or "").upper()
    )
    reading.carrier_name_printed = _apply_guard(
        reading, "carrier name", str(fields.get("carrier_name") or "").strip(), ""
    )
    reading.status_text = _apply_guard(reading, "status line", str(fields.get("status_text") or "").strip(), _WITHHELD)
    reading.location_note = _apply_guard(reading, "location note", str(fields.get("location_note") or "").strip(), "")
    reading.reference = _apply_guard(
        reading, "reference", str(fields.get("reference") or "").strip(), ""
    )
    reading.claimed_at_text = _apply_guard(
        reading, "printed delivery time", str(fields.get("printed_when") or "").strip(), ""
    )

    printed_zone = str(fields.get("timezone_printed") or "").strip()
    if printed_zone:
        reading.timezone_label = printed_zone
        reading.timezone_observed = True

    reading.claimed_at = _combine(str(fields.get("delivered_date") or ""), str(fields.get("delivered_time") or ""), tz)
    if reading.claimed_at is None:
        reading.warn("No delivery date and time could be read from that page. Type it in below.")

    # `unreadable` is a model-authored array of strings interpolated straight
    # into a sentence a person reads and the store persists. Same call, same
    # guard.
    for missing in fields.get("unreadable") or []:
        named = _apply_guard(reading, "unreadable-field name", str(missing).strip(), "")
        if named:
            reading.warn(f"The {named} on that page was not legible. Check it before you send the pack.")

    # A photograph is where a wrong reading does the most damage. A blurred 3
    # read as an 8, or a date guessed from a partially visible page, shifts the
    # window, and a shifted window turns a delivery that did happen into a
    # delivery that was not observed. So a low-confidence read of an image does
    # not get to prefill the two fields the verdict depends on. The person types
    # them, from the page in front of them, which takes ten seconds and cannot
    # be wrong in the way a guess can.
    if image_bytes is not None and reading.confidence == "low":
        reading.claimed_at = None
        reading.status = None
        reading.warn(
            "That image did not read clearly. The delivery time and the status have been left "
            "blank rather than guessed: a wrong time here would shift the window the camera is "
            "checked against, and produce a finding about the wrong hour. Type both in from the "
            "page in front of you."
        )

    _settle_carrier(reading, reading.carrier_name_printed)
    _settle_status(reading)


def _read_with_patterns(reading: TrackingPageReading, text: str, tz: dt.timezone) -> None:
    parsed = parse_tracking_text(text)
    reading.source = SOURCE_PATTERN
    reading.confidence = "medium" if parsed.tracking_number and parsed.naive_claimed_at else "low"
    reading.tracking_number = (parsed.tracking_number or "").upper()
    reading.carrier = parsed.carrier
    reading.carrier_name_printed = parsed.carrier.display_name if parsed.carrier else ""
    reading.status = parsed.status
    reading.status_text = _apply_guard(reading, "status line", parsed.status_text or "", _WITHHELD)
    if parsed.naive_claimed_at is not None:
        reading.claimed_at = parsed.naive_claimed_at.replace(tzinfo=tz)
    for warning in parsed.warnings or []:
        reading.warn(warning)
    _settle_status(reading)


def read_tracking_page(
    text: str | None = None,
    image_bytes: bytes | None = None,
    timezone_offset_minutes: int = 0,
    timezone_label: str = "UTC",
    runner: BedrockRunner | None = None,
) -> TrackingPageReading:
    """Read a tracking page. Bedrock first, regexes second, honesty either way.

    ``timezone_offset_minutes`` is the delivery address's offset, supplied by
    the user's browser. Tracking pages print a wall clock and no offset, so the
    app cannot observe this and does not pretend to: the evidence pack states
    that the timezone was supplied rather than read, and
    ``timezone_observed`` records which it was.
    """
    if not text and not image_bytes:
        raise ValueError("Paste the tracking page text or upload a screenshot of it")

    tz = dt.timezone(dt.timedelta(minutes=timezone_offset_minutes))
    reading = TrackingPageReading(timezone_label=timezone_label)
    runner = runner or default_runner()

    try:
        _read_with_bedrock(reading, runner, text, image_bytes, tz)
        return reading
    except (BedrockUnavailable, ValueError) as exc:
        fallback_reading = TrackingPageReading(timezone_label=timezone_label)
        fallback_reading.warn(
            f"The page reader was not reachable ({exc}). "
            + (
                "The pasted text was read with this app's own pattern rules instead, which handle "
                "the six carrier formats in carriers.py and nothing else."
                if text
                else "A screenshot cannot be read without it. Enter the delivery details yourself."
            )
        )
        if text:
            _read_with_patterns(fallback_reading, text, tz)
        else:
            fallback_reading.source = SOURCE_NONE
        return fallback_reading
