"""The campaign SQL store (research R1): one SQLite database, JSON documents in per-record tables.

Immutable records can be inserted once and never saved again. A Position snapshot is inserted only as
the intake proposal; every later version goes through `commit_position`, which checks the pinned base
against the head and writes in one transaction (HA C3). `trace_sink()` gives the market tracer the five
methods it calls, so model calls are traced the same way in both products (research R3).
"""

from __future__ import annotations

import copy
import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from hipstraw_mm.campaign.models import (
    AuditEvent,
    Correction,
    Delta,
    Deviation,
    Escalation,
    EvidenceRecord,
    EvidenceRequest,
    Launch,
    LineRun,
    Mandate,
    MoveExecution,
    PositionSnapshot,
    ReportRecord,
    ReviewRun,
    TestPlan,
)
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.store.base import InvalidTransitionError

R = TypeVar("R", bound=BaseModel)
Doc = dict[str, Any]

DEFAULT_DB = Path(".runs") / "campaign.db"


@dataclass(frozen=True)
class _Table:
    name: str
    record_id: Callable[[Any], str]
    mutable: bool


_TABLES: dict[type[BaseModel], _Table] = {
    Launch: _Table("launches", lambda r: r.launchId, False),
    Mandate: _Table("mandates", lambda r: f"{r.launchId}:v{r.version}", False),
    EvidenceRecord: _Table("evidence", lambda r: r.evidenceId, False),
    PositionSnapshot: _Table("positions", lambda r: r.positionId, False),
    LineRun: _Table("line_runs", lambda r: r.lineRunId, True),
    MoveExecution: _Table("move_executions", lambda r: r.executionId, False),
    Deviation: _Table("deviations", lambda r: r.deviationId, False),
    ReviewRun: _Table("reviews", lambda r: r.reviewId, True),
    Correction: _Table("corrections", lambda r: r.correctionId, False),
    AuditEvent: _Table("audit_events", lambda r: r.eventId, False),
    TestPlan: _Table("test_plans", lambda r: r.testPlanId, True),
    EvidenceRequest: _Table("evidence_requests", lambda r: r.requestId, True),
    Escalation: _Table("escalations", lambda r: r.escalationId, False),
    Delta: _Table("deltas", lambda r: r.deltaId, False),
    ReportRecord: _Table("reports", lambda r: r.reportId, False),
}
_TRACE_TABLES = ("trace_runs", "trace_steps", "trace_blobs")


def default_db_path() -> str:
    return os.environ.get("HIPSTRAW_CAMPAIGN_DB") or str(DEFAULT_DB)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CampaignStore(Protocol):
    """What the campaign module needs from storage; SqliteCampaignStore is the implementation."""

    def record_id(self, record: BaseModel) -> str: ...
    def insert(self, record: BaseModel) -> None: ...
    def save(self, record: BaseModel) -> None: ...
    def get(self, model: type[R], record_id: str) -> R | None: ...
    def list_for_launch(self, model: type[R], launch_id: str) -> list[R]: ...
    def list_all(self, model: type[R]) -> list[R]: ...
    def latest_mandate(self, launch_id: str) -> Mandate | None: ...
    def head_position(self, launch_id: str) -> PositionSnapshot | None: ...
    def commit_position(self, launch_id: str, base_version: int, successor: PositionSnapshot) -> None: ...
    def open_trace_run(self, run_id: str) -> None: ...
    def trace_sink(self) -> CampaignTraceSink: ...
    def list_trace_steps(self, run_id: str) -> list[Doc]: ...


class SqliteCampaignStore:
    def __init__(self, path: str | None = None) -> None:
        target = path if path is not None else default_db_path()
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: transactions are opened explicitly in `_tx`.
        self._conn = sqlite3.connect(target, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    @classmethod
    def read_only(cls, path: str) -> SqliteCampaignStore:
        """For the viewer (Constitution XIII): SQLite refuses every write on this connection. The viewer's
        server thread is not the one that opened it, which is safe because nothing on it ever writes."""
        store = cls.__new__(cls)
        store._conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, isolation_level=None,
                                      check_same_thread=False)
        store._conn.row_factory = sqlite3.Row
        return store

    def _create_schema(self) -> None:
        for table in _TABLES.values():
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table.name} ("
                "id TEXT PRIMARY KEY, launch_id TEXT, state TEXT, version INTEGER, "
                "created_at TEXT NOT NULL, doc TEXT NOT NULL)"
            )
            self._conn.execute(f"CREATE INDEX IF NOT EXISTS {table.name}_launch ON {table.name}(launch_id)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS trace_runs (id TEXT PRIMARY KEY, doc TEXT NOT NULL)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS trace_steps (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, "
            "seq INTEGER NOT NULL, doc TEXT NOT NULL)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS trace_steps_run ON trace_steps(run_id, seq)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS trace_blobs (id TEXT PRIMARY KEY, doc TEXT NOT NULL)")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    # -- records -----------------------------------------------------------------------------------

    @staticmethod
    def _table(model: type[BaseModel]) -> _Table:
        table = _TABLES.get(model)
        if table is None:
            raise TypeError(f"{model.__name__} is not a stored campaign record")
        return table

    def record_id(self, record: BaseModel) -> str:
        return self._table(type(record)).record_id(record)

    @staticmethod
    def _columns(record: BaseModel) -> tuple[str | None, str | None, int | None]:
        return (
            getattr(record, "launchId", None),
            getattr(record, "state", None),
            getattr(record, "version", None),
        )

    def insert(self, record: BaseModel) -> None:
        if isinstance(record, PositionSnapshot) and record.state != "proposed":
            raise PreconditionError(
                f"{record.positionId}: only a proposed snapshot is inserted directly; use commit_position"
            )
        table = self._table(type(record))
        record_id = table.record_id(record)
        launch_id, state, version = self._columns(record)
        with self._tx() as conn:
            if conn.execute(f"SELECT 1 FROM {table.name} WHERE id = ?", (record_id,)).fetchone():
                raise PreconditionError(f"{table.name}/{record_id} already exists")
            conn.execute(
                f"INSERT INTO {table.name} (id, launch_id, state, version, created_at, doc) VALUES (?, ?, ?, ?, ?, ?)",
                (record_id, launch_id, state, version, _utc_now(), record.model_dump_json()),
            )

    def save(self, record: BaseModel) -> None:
        table = self._table(type(record))
        record_id = table.record_id(record)
        if not table.mutable:
            raise PreconditionError(f"{table.name}/{record_id} is immutable")
        _, state, version = self._columns(record)
        with self._tx() as conn:
            updated = conn.execute(
                f"UPDATE {table.name} SET state = ?, version = ?, doc = ? WHERE id = ?",
                (state, version, record.model_dump_json(), record_id),
            ).rowcount
            if not updated:
                raise PreconditionError(f"{table.name}/{record_id} not found")

    def get(self, model: type[R], record_id: str) -> R | None:
        table = self._table(model)
        row = self._conn.execute(f"SELECT doc FROM {table.name} WHERE id = ?", (record_id,)).fetchone()
        return model.model_validate_json(row["doc"]) if row else None

    def list_for_launch(self, model: type[R], launch_id: str) -> list[R]:
        table = self._table(model)
        rows = self._conn.execute(
            f"SELECT doc FROM {table.name} WHERE launch_id = ? ORDER BY rowid", (launch_id,)
        ).fetchall()
        return [model.model_validate_json(r["doc"]) for r in rows]

    def list_all(self, model: type[R]) -> list[R]:
        table = self._table(model)
        rows = self._conn.execute(f"SELECT doc FROM {table.name} ORDER BY rowid").fetchall()
        return [model.model_validate_json(r["doc"]) for r in rows]

    def latest_mandate(self, launch_id: str) -> Mandate | None:
        row = self._conn.execute(
            "SELECT doc FROM mandates WHERE launch_id = ? ORDER BY version DESC LIMIT 1", (launch_id,)
        ).fetchone()
        return Mandate.model_validate_json(row["doc"]) if row else None

    # -- Position snapshots (C3) ---------------------------------------------------------------------

    def _head_row(self, conn: sqlite3.Connection, launch_id: str) -> sqlite3.Row | None:
        row = conn.execute(
            "SELECT id, doc, version FROM positions WHERE launch_id = ? AND state = 'accepted' "
            "ORDER BY version DESC LIMIT 1", (launch_id,)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id, doc, version FROM positions WHERE launch_id = ? AND state = 'proposed' AND version = 1",
                (launch_id,),
            ).fetchone()
        return row  # type: ignore[no-any-return]

    def head_position(self, launch_id: str) -> PositionSnapshot | None:
        """The latest accepted snapshot, or the intake proposal (v1) while none is accepted."""
        row = self._head_row(self._conn, launch_id)
        return PositionSnapshot.model_validate_json(row["doc"]) if row else None

    def commit_position(self, launch_id: str, base_version: int, successor: PositionSnapshot) -> None:
        if successor.state != "accepted" or successor.baseVersion != base_version:
            raise PreconditionError(
                f"{successor.positionId}: a committed successor must be accepted and pin base v{base_version}"
            )
        with self._tx() as conn:
            head = self._head_row(conn, launch_id)
            if head is None:
                raise PreconditionError(f"{launch_id}: no Position to commit against")
            if head["version"] != base_version:
                raise PreconditionError(
                    f"stale: base v{base_version} is no longer the head (v{head['version']}); re-run the Review"
                )
            top = conn.execute("SELECT MAX(version) AS v FROM positions WHERE launch_id = ?", (launch_id,)).fetchone()
            if successor.version != int(top["v"]) + 1:
                raise PreconditionError(f"{successor.positionId}: the next version is v{int(top['v']) + 1}")
            conn.execute(
                "INSERT INTO positions (id, launch_id, state, version, created_at, doc) VALUES (?, ?, ?, ?, ?, ?)",
                (successor.positionId, launch_id, "accepted", successor.version, _utc_now(),
                 successor.model_dump_json()),
            )
            old = PositionSnapshot.model_validate_json(head["doc"]).model_copy(update={"state": "superseded"})
            conn.execute("UPDATE positions SET state = 'superseded', doc = ? WHERE id = ?",
                         (old.model_dump_json(), head["id"]))

    # -- traces ----------------------------------------------------------------------------------------

    def open_trace_run(self, run_id: str) -> None:
        """The tracer only updates an existing run document, so each launch opens one first."""
        self._conn.execute(
            "INSERT OR IGNORE INTO trace_runs (id, doc) VALUES (?, ?)",
            (run_id, json.dumps({"marketRunId": run_id, "lastSeq": 0, "counts": {}})),
        )

    def trace_sink(self) -> CampaignTraceSink:
        return CampaignTraceSink(self._conn)

    def list_trace_steps(self, run_id: str) -> list[Doc]:
        rows = self._conn.execute(
            "SELECT doc FROM trace_steps WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
        return [json.loads(r["doc"]) for r in rows]


class CampaignTraceSink:
    """The store methods `market.trace.Tracer` calls, backed by the campaign trace tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_market_run(self, run_id: str) -> Doc | None:
        row = self._conn.execute("SELECT doc FROM trace_runs WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row["doc"]) if row else None

    def upsert_market_run(self, data: Doc) -> None:
        self._conn.execute(
            "INSERT INTO trace_runs (id, doc) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET doc = excluded.doc",
            (data["marketRunId"], json.dumps(data, ensure_ascii=False)),
        )

    def create_trace_step(self, data: Doc) -> None:
        doc = {**copy.deepcopy(data), "createdAt": _utc_now()}
        self._conn.execute(
            "INSERT INTO trace_steps (id, run_id, seq, doc) VALUES (?, ?, ?, ?)",
            (data["stepId"], data["marketRunId"], data["seq"], json.dumps(doc, ensure_ascii=False)),
        )

    def finish_trace_step(self, step_id: str, fields: Doc) -> None:
        row = self._conn.execute("SELECT doc FROM trace_steps WHERE id = ?", (step_id,)).fetchone()
        if row is None:
            raise InvalidTransitionError(f"traceSteps/{step_id} not found")
        doc = json.loads(row["doc"])
        if doc.get("status") != "running":
            raise InvalidTransitionError(f"traceSteps/{step_id} is '{doc.get('status')}', cannot seal again")
        doc.update(copy.deepcopy(fields))
        self._conn.execute(
            "UPDATE trace_steps SET doc = ? WHERE id = ?", (json.dumps(doc, ensure_ascii=False), step_id)
        )

    def create_trace_blob(self, data: Doc) -> None:
        self._conn.execute(
            "INSERT INTO trace_blobs (id, doc) VALUES (?, ?)", (data["blobId"], json.dumps(data, ensure_ascii=False))
        )

    def get_trace_blob(self, blob_id: str) -> Doc | None:
        row = self._conn.execute("SELECT doc FROM trace_blobs WHERE id = ?", (blob_id,)).fetchone()
        return json.loads(row["doc"]) if row else None
