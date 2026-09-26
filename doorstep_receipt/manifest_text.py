"""The manifest as a plain text file, for the reader who prints the pack.

``manifest.py`` owns the digests and the exhibit list as data, and renders the
HTML table that goes inside the filed record. This renders the same list as
``MANIFEST.txt``, which is the copy somebody reads on paper or in a mail client
that will not show them a table.

It is a separate file because the two renderings have different jobs. The HTML
one sits inside a document. This one has to stand alone: it repeats the record
number, names the tool and its version, prints the gaps, and ends with the
literal command that checks the files, because a manifest nobody can act on is
decoration.
"""

from __future__ import annotations

from . import timestamps as ts
from .manifest import VERIFY_INSTRUCTION, PackItem, PackManifest, grouped


def manifest_text(manifest: PackManifest, record_item: PackItem, version: str) -> str:
    lines = [
        "DOORSTEP RECEIPT: EXHIBIT LIST AND INTEGRITY MANIFEST",
        "=" * 53,
        "",
        f"Record no.      {manifest.claim_id}",
        f"Tracking number {manifest.tracking_number}",
        f"Carrier         {manifest.carrier_name}",
        f"Built           {ts.canonical(manifest.built_at, seconds=True)}",
        f"Built by        Doorstep Receipt {version}",
        "",
        manifest.scope_sentence,
        "",
        "EXHIBITS",
        "",
    ]
    for item in [record_item] + manifest.items:
        lines.append(f"{item.exhibit_id}  {item.name}   {item.size:,} bytes  {item.media_type}")
        lines.append(f"    {item.description}")
        if item.derived_from:
            lines.append(f"    Derived from {item.derived_from} by Doorstep Receipt. Not independently captured.")
        first, second = grouped(item.digest).splitlines()
        lines.append(f"    SHA-256  {first}")
        lines.append(f"             {second}")
        lines.append("")
    if manifest.gaps:
        lines += ["GAPS", "", ]
        for gap in manifest.gaps:
            lines.append(f"{gap.exhibit_id}  {gap.label}")
            lines.append(f"    Not in this pack. {gap.reason}")
            lines.append("")
    lines += ["HOW TO CHECK THESE FILES", "", VERIFY_INSTRUCTION, "", ""]
    lines += [
        "This pack states what one doorbell camera recorded at one door during one stated",
        "window of time. It does not identify any person and it does not state what",
        "anybody did.",
        "",
    ]
    return "\n".join(lines)
