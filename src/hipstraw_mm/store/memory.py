"""In-memory store used by the hermetic test suite. Same contract as FirestoreStore."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from hipstraw_mm.store.base import (
    CANDIDATES,
    COMPANY_RECORDS,
    DEMO_REPORTS,
    EVIDENCE,
    POSITION_BASELINES,
    PROGRAMS,
    REVIEW_DECISIONS,
    RUNS,
    AlreadyExistsError,
    Doc,
    NotFoundError,
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
