"""The claim file: SQLite, because a claim is a thing you come back to.

The first build kept everything in a dict and lost it on restart. That was an
honest scope for a one-screen demo and it is the wrong scope for this product.
A delivery dispute takes weeks. The user opens the pack, sends it, waits,
gets asked for the reference, opens it again. A claim they cannot find next
Tuesday is a claim they will not pursue, which is the exact failure the research
found: Citizens Advice's number is that a third of people with a delivery
problem take no action at all.

So claims persist, and they are searchable. ``search_text`` on each row is
everything a person might type: the tracking number, the carrier, the verdict,
the status line the carrier printed, the sentence, the letter, their own notes.
One LIKE over one column, with structured filters on top of it. Not clever. For
a household's worth of claims it is the right amount of machinery, and the whole
query is legible to anyone who opens this file.

Events are separate from claims and stay separate: an event is a fact about the
door, a claim is an argument about a parcel, and the same event can turn up in
two claims.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path

from .records import (
    ClaimLetter,
    ClaimRecord,
    Correction,
    claim_from_row,
    claim_to_row,
    event_from_json,
    event_to_json,
)
from .reconcile import ReconciliationResult
from .ring_events import RingEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    sub_type TEXT,
    timestamp TEXT NOT NULL,
    device_id TEXT,
    raw_json TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    tracking_number TEXT NOT NULL,
    carrier_code TEXT NOT NULL,
    carrier_name TEXT NOT NULL,
    status TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    claimed_at_text TEXT,
    window_minutes INTEGER NOT NULL,
    default_window_minutes INTEGER,
    status_text TEXT,
    location_note TEXT,
    reference TEXT,
    timezone_label TEXT,
    timezone_observed INTEGER NOT NULL DEFAULT 0,
    verdict TEXT NOT NULL,
    summary_sentence TEXT NOT NULL,
    device_name TEXT NOT NULL,
    reading_source TEXT,
    reading_model TEXT,
    reading_warnings TEXT,
    notes TEXT,
    events_json TEXT NOT NULL,
    coverage_json TEXT,
    indeterminate_reason TEXT,
    device_id TEXT,
    outcome TEXT NOT NULL DEFAULT 'open',
    outcome_note TEXT,
    outcome_at TEXT,
    search_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_created ON claims(created_at DESC);

CREATE TABLE IF NOT EXISTS corrections (
    claim_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT NOT NULL,
    new_value TEXT NOT NULL,
    reason TEXT NOT NULL,
    old_verdict TEXT NOT NULL,
    new_verdict TEXT NOT NULL,
    PRIMARY KEY (claim_id, revision)
);

CREATE TABLE IF NOT EXISTS letters (
    claim_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    guard_note TEXT,
    PRIMARY KEY (claim_id, revision)
);
"""


class ClaimStore:
    """Every claim, every event and every letter revision, in one SQLite file."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---- events -----------------------------------------------------------

    def add_event(self, event: RingEvent) -> None:
        """Idempotent on event_id: Ring can resend, and a resend is not a second
        thing happening at the door."""
        self._conn.execute(
            "INSERT OR REPLACE INTO events VALUES (:event_id, :event_type, :sub_type, :timestamp, "
            ":device_id, :raw_json, :received_at)",
            {
                **event_to_json(event),
                "raw_json": json.dumps(event.raw),
                "received_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        self._conn.commit()

    def events(self) -> list[RingEvent]:
        rows = self._conn.execute("SELECT * FROM events ORDER BY timestamp").fetchall()
        return [
            event_from_json(
                {
                    "event_id": r["event_id"],
                    "event_type": r["event_type"],
                    "sub_type": r["sub_type"],
                    "timestamp": r["timestamp"],
                    "device_id": r["device_id"],
                    "raw": json.loads(r["raw_json"] or "{}"),
                }
            )
            for r in rows
        ]

    # ---- claims -----------------------------------------------------------

    def save_claim(
        self,
        result: ReconciliationResult,
        device_name: str,
        reading_source: str = "manual",
        reading_model: str = "",
        reading_warnings: list[str] | None = None,
        notes: str = "",
        device_id: str = "",
    ) -> str:
        record = ClaimRecord(
            claim_id=str(uuid.uuid4())[:8],
            result=result,
            device_name=device_name,
            reading_source=reading_source,
            reading_model=reading_model,
            reading_warnings=reading_warnings or [],
            notes=notes,
            device_id=device_id,
        )
        row = claim_to_row(record)
        columns = ", ".join(row)
        placeholders = ", ".join(f":{k}" for k in row)
        self._conn.execute(f"INSERT INTO claims ({columns}) VALUES ({placeholders})", row)
        self._conn.commit()
        return record.claim_id

    def get_claim(self, claim_id: str) -> ClaimRecord | None:
        row = self._conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if row is None:
            return None
        record = claim_from_row(row)
        record.letters = self.letters(claim_id)
        record.corrections = self.corrections(claim_id)
        return record

    def list_claims(self, limit: int = 200) -> list[ClaimRecord]:
        rows = self._conn.execute(
            "SELECT * FROM claims ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [claim_from_row(r) for r in rows]

    def search(
        self,
        query: str = "",
        verdict: str | None = None,
        carrier_code: str | None = None,
        since: dt.datetime | None = None,
        until: dt.datetime | None = None,
        outcome: str | None = None,
        limit: int = 200,
    ) -> list[ClaimRecord]:
        """Free text across everything on the claim, plus the structured filters
        a person actually reaches for: which verdict, which carrier, which month."""
        clauses, params = [], []
        for term in [t for t in query.lower().split() if t]:
            clauses.append("search_text LIKE ?")
            params.append(f"%{term}%")
        if verdict:
            clauses.append("verdict = ?")
            params.append(verdict)
        if carrier_code:
            clauses.append("carrier_code = ?")
            params.append(carrier_code)
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        if since:
            clauses.append("claimed_at >= ?")
            params.append(since.isoformat())
        if until:
            clauses.append("claimed_at <= ?")
            params.append(until.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM claims {where} ORDER BY created_at DESC LIMIT ?", params
        ).fetchall()
        return [claim_from_row(r) for r in rows]

    def corrections(self, claim_id: str) -> list[Correction]:
        rows = self._conn.execute(
            "SELECT * FROM corrections WHERE claim_id = ? ORDER BY revision", (claim_id,)
        ).fetchall()
        return [
            Correction(
                revision=r["revision"],
                field=r["field"],
                old_value=r["old_value"],
                new_value=r["new_value"],
                reason=r["reason"],
                old_verdict=r["old_verdict"],
                new_verdict=r["new_verdict"],
                created_at=dt.datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def apply_correction(self, claim_id: str, new_result, correction: Correction) -> Correction:
        """Replace the current finding and append the correction that did it.

        Both halves happen together or neither does. A new verdict with no
        correction row beside it is exactly the silent edit this table exists to
        make impossible.
        """
        revision = len(self.corrections(claim_id)) + 2
        stored = Correction(
            revision=revision,
            field=correction.field,
            old_value=correction.old_value,
            new_value=correction.new_value,
            reason=correction.reason,
            old_verdict=correction.old_verdict,
            new_verdict=correction.new_verdict,
            created_at=correction.created_at,
        )
        existing = self.get_claim(claim_id)
        if existing is None:
            raise KeyError(claim_id)
        existing.result = new_result
        row = claim_to_row(existing)
        assignments = ", ".join(f"{k} = :{k}" for k in row if k != "claim_id")
        with self._conn:
            self._conn.execute(f"UPDATE claims SET {assignments} WHERE claim_id = :claim_id", row)
            self._conn.execute(
                "INSERT INTO corrections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    stored.revision,
                    stored.created_at.isoformat(),
                    stored.field,
                    stored.old_value,
                    stored.new_value,
                    stored.reason,
                    stored.old_verdict,
                    stored.new_verdict,
                ),
            )
        self._reindex(claim_id)
        return stored

    def set_outcome(self, claim_id: str, outcome: str, note: str = "") -> None:
        when = dt.datetime.now(dt.timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE claims SET outcome = ?, outcome_note = ?, outcome_at = ? WHERE claim_id = ?",
            (outcome, note, when, claim_id),
        )
        self._reindex(claim_id)

    def needing_chase(self, now: dt.datetime | None = None) -> list[ClaimRecord]:
        """Sent, no answer, and long enough ago to be worth a second letter."""
        return [r for r in self.list_claims() if r.needs_chasing(now)]

    def set_notes(self, claim_id: str, notes: str) -> None:
        self._conn.execute("UPDATE claims SET notes = ? WHERE claim_id = ?", (notes, claim_id))
        self._reindex(claim_id)

    def counts_by_verdict(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT verdict, COUNT(*) AS n FROM claims GROUP BY verdict").fetchall()
        return {r["verdict"]: r["n"] for r in rows}

    # ---- letters ----------------------------------------------------------

    def letters(self, claim_id: str) -> list[ClaimLetter]:
        rows = self._conn.execute(
            "SELECT * FROM letters WHERE claim_id = ? ORDER BY revision", (claim_id,)
        ).fetchall()
        return [
            ClaimLetter(
                body=r["body"],
                subject=r["subject"],
                revision=r["revision"],
                source=r["source"],
                created_at=dt.datetime.fromisoformat(r["created_at"]),
                guard_note=r["guard_note"] or "",
            )
            for r in rows
        ]

    def save_letter(self, claim_id: str, letter: ClaimLetter) -> ClaimLetter:
        """Append a revision. Revisions are never overwritten: the user needs to
        be able to say which wording they actually sent."""
        next_revision = len(self.letters(claim_id)) + 1
        stored = ClaimLetter(
            body=letter.body,
            subject=letter.subject,
            revision=next_revision,
            source=letter.source,
            created_at=letter.created_at,
            guard_note=letter.guard_note,
        )
        self._conn.execute(
            "INSERT INTO letters VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                claim_id,
                stored.revision,
                stored.created_at.isoformat(),
                stored.source,
                stored.subject,
                stored.body,
                stored.guard_note,
            ),
        )
        self._reindex(claim_id)
        return stored

    def _reindex(self, claim_id: str) -> None:
        record = self.get_claim(claim_id)
        if record is None:
            return
        self._conn.execute(
            "UPDATE claims SET search_text = ? WHERE claim_id = ?",
            (record.search_text().lower(), claim_id),
        )
        self._conn.commit()


# The name the first build used, kept so nothing that imports it has to care
# that the storage behind it changed from a dict to a database.
DemoStore = ClaimStore
