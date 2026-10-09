"""In-memory store used by the hermetic test suite. Same contract as FirestoreStore."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from hipstraw_mm.store.base import (
    CANDIDATES,
    COMPANY_RECORDS,
    DEMO_REPORTS,
    EVIDENCE,
    MARKET_RUNS,
    POSITION_BASELINES,
    PROGRAMS,
    REVIEW_DECISIONS,
    RUNS,
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Doc]] = {
            name: {}
            for name in (
                PROGRAMS,
                CANDIDATES,
                RUNS,
                COMPANY_RECORDS,
                EVIDENCE,
                REVIEW_DECISIONS,
                POSITION_BASELINES,
                DEMO_REPORTS,
                MARKET_RUNS,
                TRACE_STEPS,
                TRACE_BLOBS,
            )
        }

    # -- generic helpers ---------------------------------------------------

    def _get(self, collection: str, doc_id: str) -> Doc | None:
        doc = self._data[collection].get(doc_id)
        return copy.deepcopy(doc) if doc is not None else None

    def _upsert(self, collection: str, doc_id: str, data: Doc) -> None:
        existing = self._data[collection].get(doc_id)
        merged = {**existing, **copy.deepcopy(data)} if existing else {**copy.deepcopy(data), "createdAt": _now()}
        self._data[collection][doc_id] = merged

    def _create(self, collection: str, doc_id: str, data: Doc) -> None:
        if doc_id in self._data[collection]:
            raise AlreadyExistsError(f"{collection}/{doc_id} already exists")
        self._data[collection][doc_id] = {**copy.deepcopy(data), "createdAt": _now()}

    def _list(self, collection: str, field: str, value: str) -> list[Doc]:
        return [copy.deepcopy(doc) for _, doc in sorted(self._data[collection].items()) if doc.get(field) == value]

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
        check_run_upsert(self._data[RUNS].get(run_id), data)
        self._upsert(RUNS, run_id, data)

    def get_run(self, run_id: str) -> Doc | None:
        return self._get(RUNS, run_id)

    def transition_run(self, run_id: str, from_status: str, to_status: str, extra: Doc | None = None) -> None:
        run = self._data[RUNS].get(run_id)
        if run is None:
            raise NotFoundError(f"runs/{run_id} not found")
        check_transition(run.get("status", ""), from_status, to_status)
        run.update(copy.deepcopy(extra or {}))
        run["status"] = to_status

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
        return [
            copy.deepcopy(doc)
            for _, doc in sorted(self._data[REVIEW_DECISIONS].items())
            if str(doc.get("companyRecordId", "")).startswith(prefix)
        ]

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
        run_id = data["marketRunId"]
        self._upsert(MARKET_RUNS, run_id, data)

    def get_market_run(self, run_id: str) -> Doc | None:
        return self._get(MARKET_RUNS, run_id)

    def list_market_runs(self) -> list[Doc]:
        runs = [copy.deepcopy(doc) for doc in self._data[MARKET_RUNS].values()]
        runs.sort(key=lambda r: r.get("marketRunId", ""), reverse=True)
        return runs

    def transition_market_run(
        self, run_id: str, from_status: str, to_status: str, extra: Doc | None = None
    ) -> None:
        run = self._data[MARKET_RUNS].get(run_id)
        if run is None:
            raise NotFoundError(f"marketRuns/{run_id} not found")
        check_market_transition(run.get("status", ""), from_status, to_status)
        run.update(copy.deepcopy(extra or {}))
        run["status"] = to_status

    # -- trace steps (seal-once) ---------------------------------------------

    def create_trace_step(self, data: Doc) -> None:
        step_id = data["stepId"]
        if step_id in self._data[TRACE_STEPS]:
            raise AlreadyExistsError(f"traceSteps/{step_id} already exists")
        self._data[TRACE_STEPS][step_id] = {**copy.deepcopy(data), "createdAt": _now()}

    def get_trace_step(self, step_id: str) -> Doc | None:
        return self._get(TRACE_STEPS, step_id)

    def list_trace_steps_after(self, run_id: str, after_seq: int) -> list[Doc]:
        results = [
            copy.deepcopy(doc)
            for doc in self._data[TRACE_STEPS].values()
            if doc.get("marketRunId") == run_id and doc.get("seq", 0) > after_seq
        ]
        results.sort(key=lambda d: d.get("seq", 0))
        return results

    def get_trace_steps(self, run_id: str, seqs: list[int]) -> list[Doc]:
        seq_set = set(seqs)
        return [
            copy.deepcopy(doc)
            for doc in self._data[TRACE_STEPS].values()
            if doc.get("marketRunId") == run_id and doc.get("seq", 0) in seq_set
        ]

    def finish_trace_step(self, step_id: str, fields: Doc) -> None:
        doc = self._data[TRACE_STEPS].get(step_id)
        if doc is None:
            raise NotFoundError(f"traceSteps/{step_id} not found")
        if doc.get("status") != "running":
            raise InvalidTransitionError(
                f"traceSteps/{step_id} is '{doc.get('status')}', cannot seal again"
            )
        doc.update(copy.deepcopy(fields))

    # -- trace blobs (create-only) -------------------------------------------

    def create_trace_blob(self, data: Doc) -> None:
        self._create(TRACE_BLOBS, data["blobId"], data)

    def get_trace_blob(self, blob_id: str) -> Doc | None:
        return self._get(TRACE_BLOBS, blob_id)
