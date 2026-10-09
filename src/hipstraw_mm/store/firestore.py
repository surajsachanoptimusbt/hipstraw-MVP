"""Firestore store, emulator only (research R10). Same contract as MemoryStore."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.store.base import (
    BEAM_LEVELS,
    BUYER_ROLES,
    CANDIDATES,
    COMPANY_RECORDS,
    DELIBERATIONS,
    DEMO_REPORTS,
    EVIDENCE,
    GRAPH_MEANINGS,
    LINK_CHECKS,
    MARKET_COMPANIES,
    MARKET_RUNS,
    OBJECTIVE_DOCUMENTS,
    PATH_DECISIONS,
    PATHS,
    POSITION_BASELINES,
    PROGRAMS,
    REVIEW_DECISIONS,
    RUNS,
    SEED_GRAPHS,
    TRACE_BLOBS,
    TRACE_STEPS,
    AlreadyExistsError,
    Doc,
    InvalidTransitionError,
    NotFoundError,
    check_market_transition,
    check_run_upsert,
    check_transition,
)


def check_emulator_preconditions(project_id: str) -> None:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise PreconditionError(
            "FIRESTORE_EMULATOR_HOST is not set; this tool only runs against the local Firestore emulator"
        )
    if not project_id.startswith("demo-"):
        raise PreconditionError(f"project ID '{project_id}' must start with 'demo-'")


def check_emulator_reachable() -> None:
    """Fail in two seconds with a clear message instead of retrying for five minutes."""
    import socket

    host_port = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    host, _, port = host_port.rpartition(":")
    try:
        socket.create_connection((host or "localhost", int(port or 8080)), timeout=2).close()
    except OSError as exc:
        raise PreconditionError(
            f"the Firestore emulator is not reachable at {host_port} ({exc.__class__.__name__}). "
            "Start it first, or add --memory to run without it."
        ) from exc


def _plain(value: Any) -> Any:
    """Firestore timestamps become ISO strings, so both stores return the same shapes."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class FirestoreStore:
    def __init__(self, project_id: str, client: Any | None = None) -> None:
        check_emulator_preconditions(project_id)
        from google.api_core import exceptions as gexc
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        self._firestore = firestore
        self._conflict = gexc.Conflict
        self._field_filter = FieldFilter
        self._db = client or firestore.Client(project=project_id)

    # -- generic helpers ---------------------------------------------------

    def _ref(self, collection: str, doc_id: str) -> Any:
        return self._db.collection(collection).document(doc_id)

    def _raw(self, collection: str, doc_id: str) -> Doc | None:
        snap = self._ref(collection, doc_id).get()
        return snap.to_dict() if snap.exists else None

    def _get(self, collection: str, doc_id: str) -> Doc | None:
        raw = self._raw(collection, doc_id)
        return _plain(raw) if raw is not None else None

    def _upsert(self, collection: str, doc_id: str, data: Doc) -> None:
        # Shallow merge, matching MemoryStore, so nested maps are replaced rather than deep-merged.
        existing = self._raw(collection, doc_id)
        merged = {**existing, **data} if existing else {**data, "createdAt": self._firestore.SERVER_TIMESTAMP}
        self._ref(collection, doc_id).set(merged)

    def _create(self, collection: str, doc_id: str, data: Doc) -> None:
        try:
            self._ref(collection, doc_id).create({**data, "createdAt": self._firestore.SERVER_TIMESTAMP})
        except self._conflict as exc:
            raise AlreadyExistsError(f"{collection}/{doc_id} already exists") from exc

    def _list(self, collection: str, field: str, value: str) -> list[Doc]:
        query = self._db.collection(collection).where(filter=self._field_filter(field, "==", value))
        docs = sorted(query.stream(), key=lambda snap: snap.id)
        return [_plain(snap.to_dict()) for snap in docs]

    # -- programs and candidates ------------------------------------------

    def upsert_program(self, data: Doc) -> None:
        self._upsert(PROGRAMS, data["programId"], data)

    def get_program(self, program_id: str) -> Doc | None:
        return self._get(PROGRAMS, program_id)

    def upsert_candidate(self, data: Doc) -> None:
        self._upsert(CANDIDATES, data["candidateId"], data)

    def get_candidate(self, candidate_id: str) -> Doc | None:
        return self._get(CANDIDATES, candidate_id)

    def list_candidates(self, program_id: str) -> list[Doc]:
        return self._list(CANDIDATES, "programId", program_id)

    # -- runs ----------------------------------------------------------------

    def upsert_run(self, data: Doc) -> None:
        run_id = data["runId"]
        check_run_upsert(self._raw(RUNS, run_id), data)
        self._upsert(RUNS, run_id, data)

    def get_run(self, run_id: str) -> Doc | None:
        return self._get(RUNS, run_id)

    def transition_run(self, run_id: str, from_status: str, to_status: str, extra: Doc | None = None) -> None:
        ref = self._ref(RUNS, run_id)

        @self._firestore.transactional
        def _apply(transaction: Any) -> None:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                raise NotFoundError(f"runs/{run_id} not found")
            check_transition(snap.get("status"), from_status, to_status)
            transaction.update(ref, {**(extra or {}), "status": to_status})

        _apply(self._db.transaction())

    # -- company records -----------------------------------------------------

    def upsert_company_record(self, record_id: str, data: Doc) -> None:
        self._upsert(COMPANY_RECORDS, record_id, data)

    def get_company_record(self, record_id: str) -> Doc | None:
        return self._get(COMPANY_RECORDS, record_id)

    def list_company_records(self, run_id: str) -> list[Doc]:
        return self._list(COMPANY_RECORDS, "runId", run_id)

    # -- create-only collections --------------------------------------------

    def create_evidence(self, data: Doc) -> None:
        self._create(EVIDENCE, data["evidenceId"], data)

    def get_evidence(self, evidence_id: str) -> Doc | None:
        return self._get(EVIDENCE, evidence_id)

    def list_evidence(self, run_id: str) -> list[Doc]:
        return self._list(EVIDENCE, "runId", run_id)

    def create_review_decision(self, decision_id: str, data: Doc) -> None:
        self._create(REVIEW_DECISIONS, decision_id, data)

    def get_review_decision(self, decision_id: str) -> Doc | None:
        return self._get(REVIEW_DECISIONS, decision_id)

    def list_review_decisions(self, run_id: str) -> list[Doc]:
        # Decisions carry no runId field; their companyRecordId is `<runId>__<key>`.
        prefix = f"{run_id}__"
        query = (
            self._db.collection(REVIEW_DECISIONS)
            .where(filter=self._field_filter("companyRecordId", ">=", prefix))
            .where(filter=self._field_filter("companyRecordId", "<", prefix + ""))
        )
        docs = sorted(query.stream(), key=lambda snap: snap.id)
        return [_plain(snap.to_dict()) for snap in docs]

    def create_position_baseline(self, run_id: str, data: Doc) -> None:
        self._create(POSITION_BASELINES, run_id, data)

    def get_position_baseline(self, run_id: str) -> Doc | None:
        return self._get(POSITION_BASELINES, run_id)

    # -- demo reports ----------------------------------------------------------

    def upsert_demo_report(self, run_id: str, data: Doc) -> None:
        self._upsert(DEMO_REPORTS, run_id, data)

    def get_demo_report(self, run_id: str) -> Doc | None:
        return self._get(DEMO_REPORTS, run_id)

    # -- market runs (feature 003) -------------------------------------------

    def upsert_market_run(self, data: Doc) -> None:
        self._upsert(MARKET_RUNS, data["marketRunId"], data)

    def get_market_run(self, run_id: str) -> Doc | None:
        return self._get(MARKET_RUNS, run_id)

    def list_market_runs(self) -> list[Doc]:
        runs = [_plain(snap.to_dict()) for snap in self._db.collection(MARKET_RUNS).stream()]
        runs.sort(key=lambda r: r.get("marketRunId", ""), reverse=True)
        return runs

    def transition_market_run(
        self, run_id: str, from_status: str, to_status: str, extra: Doc | None = None
    ) -> None:
        ref = self._ref(MARKET_RUNS, run_id)

        @self._firestore.transactional
        def _apply(transaction: Any) -> None:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                raise NotFoundError(f"marketRuns/{run_id} not found")
            check_market_transition(snap.get("status"), from_status, to_status)
            transaction.update(ref, {**(extra or {}), "status": to_status})

        _apply(self._db.transaction())

    # -- trace steps (seal-once) and blobs (create-only) -----------------------

    def create_trace_step(self, data: Doc) -> None:
        self._create(TRACE_STEPS, data["stepId"], data)

    def get_trace_step(self, step_id: str) -> Doc | None:
        return self._get(TRACE_STEPS, step_id)

    def list_trace_steps_after(self, run_id: str, after_seq: int) -> list[Doc]:
        steps = [s for s in self._list(TRACE_STEPS, "marketRunId", run_id) if s.get("seq", 0) > after_seq]
        steps.sort(key=lambda d: d.get("seq", 0))
        return steps

    def get_trace_steps(self, run_id: str, seqs: list[int]) -> list[Doc]:
        wanted = set(seqs)
        return [s for s in self._list(TRACE_STEPS, "marketRunId", run_id) if s.get("seq", 0) in wanted]

    def finish_trace_step(self, step_id: str, fields: Doc) -> None:
        ref = self._ref(TRACE_STEPS, step_id)

        @self._firestore.transactional
        def _apply(transaction: Any) -> None:
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                raise NotFoundError(f"traceSteps/{step_id} not found")
            if snap.get("status") != "running":
                raise InvalidTransitionError(f"traceSteps/{step_id} is '{snap.get('status')}', cannot seal again")
            transaction.update(ref, fields)

        _apply(self._db.transaction())

    def create_trace_blob(self, data: Doc) -> None:
        self._create(TRACE_BLOBS, data["blobId"], data)

    def get_trace_blob(self, blob_id: str) -> Doc | None:
        return self._get(TRACE_BLOBS, blob_id)

    # -- pipeline artifacts ----------------------------------------------------------

    def create_deliberation(self, data: Doc) -> None:
        self._create(DELIBERATIONS, data["deliberationId"], data)

    def list_deliberations(self, run_id: str) -> list[Doc]:
        return self._list(DELIBERATIONS, "marketRunId", run_id)

    def create_graph_meaning(self, run_id: str, data: Doc) -> None:
        self._create(GRAPH_MEANINGS, run_id, data)

    def get_graph_meaning(self, run_id: str) -> Doc | None:
        return self._get(GRAPH_MEANINGS, run_id)

    def create_seed_graph(self, data: Doc) -> None:
        self._create(SEED_GRAPHS, data["graphId"], data)

    def list_seed_graphs(self, run_id: str) -> list[Doc]:
        graphs = self._list(SEED_GRAPHS, "marketRunId", run_id)
        graphs.sort(key=lambda g: g.get("version", 0))
        return graphs

    def get_seed_graph(self, graph_id: str) -> Doc | None:
        return self._get(SEED_GRAPHS, graph_id)

    def create_beam_level(self, run_id: str, level_no: int, data: Doc) -> None:
        self._create(BEAM_LEVELS, f"{run_id}__L{level_no}", {**data, "marketRunId": run_id})

    def list_beam_levels(self, run_id: str) -> list[Doc]:
        return self._list(BEAM_LEVELS, "marketRunId", run_id)

    def upsert_market_company(self, data: Doc) -> None:
        self._upsert(MARKET_COMPANIES, f"{data['marketRunId']}__{data['domainKey']}", data)

    def list_market_companies(self, run_id: str) -> list[Doc]:
        return self._list(MARKET_COMPANIES, "marketRunId", run_id)

    def create_buyer_roles(self, data: Doc) -> None:
        self._create(BUYER_ROLES, f"{data['marketRunId']}__{data['pathId']}__{data['domainKey']}", data)

    def list_buyer_roles(self, run_id: str) -> list[Doc]:
        return self._list(BUYER_ROLES, "marketRunId", run_id)

    def create_path_decision(self, data: Doc) -> None:
        self._create(PATH_DECISIONS, f"{data['marketRunId']}__{data['pathId']}", data)

    def list_path_decisions(self, run_id: str) -> list[Doc]:
        return self._list(PATH_DECISIONS, "marketRunId", run_id)

    def create_link_check(self, data: Doc) -> None:
        self._create(LINK_CHECKS, data["linkCheckId"], data)

    def list_link_checks(self, run_id: str) -> list[Doc]:
        return self._list(LINK_CHECKS, "marketRunId", run_id)

    def upsert_path(self, data: Doc) -> None:
        self._upsert(PATHS, data["pathId"], data)

    def get_path(self, path_id: str) -> Doc | None:
        return self._get(PATHS, path_id)

    def list_paths(self, run_id: str) -> list[Doc]:
        return self._list(PATHS, "marketRunId", run_id)

    # -- objective documents (create-only) -----------------------------------------

    def create_objective_document(self, data: Doc) -> None:
        self._create(OBJECTIVE_DOCUMENTS, data["documentId"], data)

    def list_objective_documents(self, run_id: str) -> list[Doc]:
        return self._list(OBJECTIVE_DOCUMENTS, "marketRunId", run_id)
