"""The desk's state and audit ledger in one SQLite file (standard library): each change is one SQL transaction
that appends its events to an append-only, hash-chained ledger and updates the case. Triggers refuse any update
or delete of a ledger row, and `verify` recomputes the chain.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from hipstraw_mm.desk.models import Case, Event

GENESIS = "0" * 64
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, created TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, doc TEXT NOT NULL,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_case ON events (case_id, seq);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
"""


def _canonical(doc: dict[str, Any]) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash: str, doc: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(doc)).encode("utf-8")).hexdigest()


class DeskStore:
    """One connection, shared by the API's request threads and the agent's thread under one lock."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.executescript(_SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def commit(self, case: Case, events: list[dict[str, Any]]) -> list[Event]:
        """Append the events to the ledger and save the case, in one transaction."""
        with self.transaction():
            written = [self._append(e) for e in events]
            self._conn.execute(
                "INSERT INTO cases (id, created, doc) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET doc = excluded.doc",
                (case.id, case.createdAt, case.model_dump_json()),
            )
        return written

    def _append(self, event: dict[str, Any]) -> Event:
        row = self._conn.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prev, seq = (row["hash"], row["seq"] + 1) if row else (GENESIS, 1)
        doc = {**event, "seq": seq}
        digest = chain_hash(prev, doc)
        self._conn.execute("INSERT INTO events (seq, case_id, doc, prev_hash, hash) VALUES (?, ?, ?, ?, ?)",
                           (seq, event["caseId"], _canonical(doc), prev, digest))
        return Event.model_validate({**doc, "prevHash": prev, "hash": digest})

    def next_case_id(self) -> str:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"]
        return f"HS-{1001 + n}"

    def case(self, case_id: str) -> Case | None:
        with self._lock:
            row = self._conn.execute("SELECT doc FROM cases WHERE id = ?", (case_id,)).fetchone()
        return Case.model_validate_json(row["doc"]) if row else None

    def cases(self) -> list[Case]:
        with self._lock:
            rows = self._conn.execute("SELECT doc FROM cases ORDER BY created DESC, id DESC").fetchall()
        return [Case.model_validate_json(r["doc"]) for r in rows]

    def events(self, case_id: str | None = None, after: int = 0) -> list[Event]:
        query = "SELECT doc, prev_hash, hash FROM events WHERE seq > ?"
        args: list[int | str] = [after]
        if case_id is not None:
            query += " AND case_id = ?"
            args.append(case_id)
        with self._lock:
            rows = self._conn.execute(query + " ORDER BY seq", args).fetchall()
        return [Event.model_validate({**json.loads(r["doc"]), "prevHash": r["prev_hash"], "hash": r["hash"]})
                for r in rows]

    def verify(self) -> dict[str, Any]:
        """Recompute the chain from the first event. Any edited, removed or reordered row breaks it."""
        prev, checked = GENESIS, 0
        with self._lock:
            rows = self._conn.execute("SELECT seq, doc, prev_hash, hash FROM events ORDER BY seq").fetchall()
        for r in rows:
            if r["prev_hash"] != prev or chain_hash(prev, json.loads(r["doc"])) != r["hash"]:
                return {"ok": False, "checked": checked, "brokenAt": r["seq"], "head": prev}
            prev, checked = r["hash"], checked + 1
        return {"ok": True, "checked": checked, "brokenAt": None, "head": prev}
