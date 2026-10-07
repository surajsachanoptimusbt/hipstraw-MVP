"""Store protocol shared by the in-memory and Firestore stores (data-model.md).

`programs`, `marketCandidates`, `runs`, `companyRecords`, and `demoReports` are upserted.
`evidence`, `reviewDecisions`, and `positionBaselines` are create-only: there is deliberately no
method that updates them, and a second create raises AlreadyExistsError.
"""

from __future__ import annotations

from typing import Any, Protocol

Doc = dict[str, Any]

PROGRAMS = "programs"
CANDIDATES = "marketCandidates"
RUNS = "runs"
COMPANY_RECORDS = "companyRecords"
EVIDENCE = "evidence"
REVIEW_DECISIONS = "reviewDecisions"
POSITION_BASELINES = "positionBaselines"
DEMO_REPORTS = "demoReports"

# created -> discovered -> verified -> reviewed -> reported; any step may fail.
_NEXT_STATUS = {
    "created": "discovered",
    "discovered": "verified",
    "verified": "reviewed",
    "reviewed": "reported",
}


class StoreError(Exception):
    pass


class AlreadyExistsError(StoreError):
    pass


class NotFoundError(StoreError):
    pass


class InvalidTransitionError(StoreError):
    pass


def check_transition(current: str, from_status: str, to_status: str) -> None:
    if current != from_status:
        raise InvalidTransitionError(f"run is '{current}', expected '{from_status}'")
    if to_status == "failed":
        if current in ("failed", "reported"):
            raise InvalidTransitionError(f"a '{current}' run cannot be marked failed")
        return
    if _NEXT_STATUS.get(from_status) != to_status:
        raise InvalidTransitionError(f"cannot move a run from '{from_status}' to '{to_status}'")


def check_run_upsert(existing: Doc | None, data: Doc) -> None:
    """New runs start as `created`; afterwards status only changes through transition_run."""
    if existing is None:
        if data.get("status", "created") != "created":
            raise InvalidTransitionError("a new run must start with status 'created'")
    elif "status" in data and data["status"] != existing.get("status"):
        raise InvalidTransitionError("run status changes only through transition_run")


class Store(Protocol):
    def upsert_program(self, data: Doc) -> None: ...
    def get_program(self, program_id: str) -> Doc | None: ...

    def upsert_candidate(self, data: Doc) -> None: ...
    def get_candidate(self, candidate_id: str) -> Doc | None: ...
    def list_candidates(self, program_id: str) -> list[Doc]: ...

    def upsert_run(self, data: Doc) -> None: ...
    def get_run(self, run_id: str) -> Doc | None: ...
    def transition_run(self, run_id: str, from_status: str, to_status: str, extra: Doc | None = None) -> None: ...

    def upsert_company_record(self, record_id: str, data: Doc) -> None: ...
    def get_company_record(self, record_id: str) -> Doc | None: ...
    def list_company_records(self, run_id: str) -> list[Doc]: ...

    def create_evidence(self, data: Doc) -> None: ...
    def get_evidence(self, evidence_id: str) -> Doc | None: ...
    def list_evidence(self, run_id: str) -> list[Doc]: ...

    def create_review_decision(self, decision_id: str, data: Doc) -> None: ...
    def get_review_decision(self, decision_id: str) -> Doc | None: ...
    def list_review_decisions(self, run_id: str) -> list[Doc]: ...

    def create_position_baseline(self, run_id: str, data: Doc) -> None: ...
    def get_position_baseline(self, run_id: str) -> Doc | None: ...

    def upsert_demo_report(self, run_id: str, data: Doc) -> None: ...
    def get_demo_report(self, run_id: str) -> Doc | None: ...
