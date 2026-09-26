"""Re-read a pack and re-run every digest in its own ``manifest.sha256``.

Separate from the module that builds a pack, because checking somebody else's
archive is a different job from assembling your own, and because this one is
reachable as an endpoint: a recipient can drop a pack they were sent onto the
page and get the answer without installing anything.

It exists at all so that this app's claim about its own manifests is something
the app can be tested on, rather than something the README asserts.

Note what the report is careful not to say. It reports whether the files in an
archive match the digests recorded in that same archive. It does not say the
pack is authentic, because the pack's own sender wrote both the files and the
digests, and nothing here can tell you otherwise.
"""

from __future__ import annotations

import io
import json
import zipfile

from .manifest import (
    MANIFEST_JSON,
    MANIFEST_NAME,
    MANIFEST_SHA,
    PackItem,
    VerificationReport,
    compute_pack_digest,
    sha256_bytes,
)


def verify_pack(zip_bytes: bytes) -> VerificationReport:
    """Re-read a pack and re-run every digest in its own manifest.sha256.

    Exposed as an endpoint so a recipient can check a pack they were sent without
    installing anything, and so this app's claim about its own manifests is
    something the app can be tested on rather than something the README asserts.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return VerificationReport(ok=False, message="That file is not a readable zip archive.")

    names = set(archive.namelist())
    if MANIFEST_SHA not in names:
        return VerificationReport(
            ok=False, message=f"No {MANIFEST_SHA} in the archive, so there is nothing to check against."
        )

    listed: dict[str, str] = {}
    for line in archive.read(MANIFEST_SHA).decode("utf-8").splitlines():
        if "  " in line:
            digest, name = line.split("  ", 1)
            listed[name.strip()] = digest.strip()

    report = VerificationReport(ok=True)
    if MANIFEST_JSON in names:
        report.claim_id = json.loads(archive.read(MANIFEST_JSON)).get("claim_id", "")

    for name, digest in listed.items():
        if name not in names:
            report.missing.append(name)
            continue
        report.checked += 1
        if sha256_bytes(archive.read(name)) != digest:
            report.mismatched.append(name)

    report.unlisted = sorted(names - set(listed) - {MANIFEST_NAME, MANIFEST_SHA, MANIFEST_JSON})
    report.pack_digest_ok = True
    if MANIFEST_JSON in names:
        manifest = json.loads(archive.read(MANIFEST_JSON))
        recomputed = compute_pack_digest(
            [PackItem(f["exhibit"], f["name"], f["bytes"], f["sha256"]) for f in manifest.get("files", [])]
        )
        report.pack_digest_ok = recomputed == manifest.get("pack_digest")

    report.ok = not report.mismatched and not report.missing and report.pack_digest_ok
    if report.ok:
        report.message = (
            f"All {report.checked} files in this archive match the digests recorded in its own "
            f"manifest, and the manifest matches its own file list."
        )
    else:
        problems = []
        if report.mismatched:
            problems.append(f"{len(report.mismatched)} file(s) differ from the digest recorded for them")
        if report.missing:
            problems.append(f"{len(report.missing)} listed file(s) are not in the archive")
        if not report.pack_digest_ok:
            problems.append("the manifest's own digest does not match its file list")
        report.message = "This archive does not match its manifest: " + "; ".join(problems) + "."
    return report
