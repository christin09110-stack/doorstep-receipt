"""The exhibit list and integrity manifest, and the digests behind it.

Written to DOCUMENT-CRAFT.md section 5, whose central point is that a hash
manifest's failure mode is reading as noise: the reader's eye slides off it and
it contributes nothing. Four rules turn it back into something a reader can act
on, and each one is implemented here.

- **The whole digest, 64 characters, grouped in eights.** A truncated hash is a
  screen-width affordance, not a record. The real use of a digest is two people
  reading it to each other on a telephone, which is what the grouping is for.
- **A literal command.** ``sha256sum -c manifest.sha256`` -- the manifest behind
  it is written in the format that command already parses, because an adjuster
  checking a claim against a carrier shouldn't also have to debug a homemade
  manifest format on top of the claim itself.
- **Never the word "verified" beside a digest this app computed itself**, five
  minutes ago, over a file it also wrote. That is a checksum. Writing "verified"
  next to it is the quickest way an evidence pack loses its reader, and an
  adjuster who handles digital evidence will spot it at once.
- **Gaps are entries.** A clip that could not be retrieved is a row with a
  reason, not a silence. A manifest with no gaps in it reads as synthesised,
  because real ones have gaps.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
from dataclasses import dataclass, field

from . import timestamps as ts

MANIFEST_NAME = "MANIFEST.txt"
MANIFEST_JSON = "manifest.json"
MANIFEST_SHA = "manifest.sha256"
RECORD_NAME = "doorstep-delivery-record.html"

SCOPE_SENTENCE = (
    "Each SHA-256 below is taken over the bytes of the file exactly as written into this pack. "
    "It shows whether that file has changed since Doorstep Receipt computed it at {built}. It is "
    "not a signature by any third party, it does not establish who assembled this pack, and it "
    "does not establish that what the pack says is accurate."
)

VERIFY_INSTRUCTION = """Don't take this pack's word for itself. Put every file in one directory
together with the supplied manifest.sha256 and run:

    sha256sum -c manifest.sha256

That is the same check a carrier's own claims-integrity tooling already runs.
OK against a file means it still matches what was recorded when this pack was
built; anything else means that file should not be relied on without asking
the sender about it. manifest.sha256 holds one line per file -- a 64 character
digest, two spaces, the file name -- because that is the layout sha256sum
itself requires, not a format invented for this claim."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def grouped(digest: str) -> str:
    """64 characters in eights, with a wider gap every 32, on two lines.

    Grouping is for reading aloud. Two people comparing a digest over the phone
    is the use this format exists for.
    """
    eights = [digest[i:i + 8] for i in range(0, 64, 8)]
    return "  ".join(eights[:2]) + "  " + "  ".join(eights[2:4]) + "\n" + \
           "  ".join(eights[4:6]) + "  " + "  ".join(eights[6:8])


@dataclass
class PackItem:
    exhibit_id: str
    name: str
    size: int
    digest: str
    description: str = ""
    derived_from: str = ""
    media_type: str = "text/plain"


@dataclass
class PackGap:
    """Something the pack should contain and does not, with the reason."""

    exhibit_id: str
    label: str
    reason: str


@dataclass
class PackManifest:
    claim_id: str
    tracking_number: str
    carrier_name: str
    built_at: dt.datetime
    items: list[PackItem] = field(default_factory=list)
    gaps: list[PackGap] = field(default_factory=list)
    pack_digest: str = ""

    @property
    def scope_sentence(self) -> str:
        return SCOPE_SENTENCE.format(built=ts.canonical(self.built_at, seconds=True))

    def to_json(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "tracking_number": self.tracking_number,
            "carrier_name": self.carrier_name,
            "built_at": ts.rfc3339(self.built_at),
            "algorithm": "sha256",
            "scope": self.scope_sentence,
            "files": [
                {
                    "exhibit": i.exhibit_id,
                    "name": i.name,
                    "bytes": i.size,
                    "media_type": i.media_type,
                    "sha256": i.digest,
                    "description": i.description,
                    "derived_from": i.derived_from,
                }
                for i in self.items
            ],
            "gaps": [{"exhibit": g.exhibit_id, "label": g.label, "reason": g.reason} for g in self.gaps],
            "pack_digest": self.pack_digest,
        }

    def sha256_file(self) -> str:
        """One line per file in the layout `sha256sum -c` already parses.
        An adjuster comparing my numbers against a carrier's shouldn't also
        have to trust that I built my own verification tool correctly."""
        return "".join(f"{i.digest}  {i.name}\n" for i in self.items)

    def html_table(self) -> str:
        rows = []
        for item in self.items:
            derived = (
                f"<br>Derived from {html.escape(item.derived_from)} by Doorstep Receipt. "
                "Not independently captured."
                if item.derived_from
                else ""
            )
            rows.append(
                "<tr>"
                f'<td class="id">{html.escape(item.exhibit_id)}</td>'
                f"<td>{html.escape(item.name)}<br>{html.escape(item.description)}{derived}"
                f'<div class="hash">{html.escape(grouped(item.digest))}</div></td>'
                f"<td>{item.size:,} bytes<br>{html.escape(item.media_type)}</td>"
                "</tr>"
            )
        for gap in self.gaps:
            rows.append(
                "<tr>"
                f'<td class="id">{html.escape(gap.exhibit_id)}</td>'
                f"<td>{html.escape(gap.label)}<br>Not in this pack. {html.escape(gap.reason)}</td>"
                "<td>no file</td>"
                "</tr>"
            )
        return (
            '<table class="manifest"><thead><tr><th>Exhibit</th><th>File, description and SHA-256</th>'
            f"<th>Size and type</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )


@dataclass
class VerificationReport:
    ok: bool
    claim_id: str = ""
    checked: int = 0
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unlisted: list[str] = field(default_factory=list)
    pack_digest_ok: bool = False
    message: str = ""


def compute_pack_digest(items: list[PackItem]) -> str:
    return sha256_bytes("".join(f"{i.digest}  {i.name}\n" for i in items).encode("utf-8"))
