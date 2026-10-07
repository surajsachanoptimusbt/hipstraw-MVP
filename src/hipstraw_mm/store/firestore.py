"""Firestore store, emulator only (research R10). Same contract as MemoryStore."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from hipstraw_mm.errors import PreconditionError
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


def check_emulator_preconditions(project_id: str) -> None:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise PreconditionError(
            "FIRESTORE_EMULATOR_HOST is not set; this tool only runs against the local Firestore emulator"
        )
    if not project_id.startswith("demo-"):
        raise PreconditionError(f"project ID '{project_id}' must start with 'demo-'")


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
