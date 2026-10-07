"""T011: Store contract tests, parametrized over MemoryStore and FirestoreStore.

The Firestore variant is marked `emulator` and runs only with `--emulator`. Every test uses fresh
IDs, so emulator runs never collide with each other or with demo data.
"""

import uuid

import pytest

from hipstraw_mm.store.base import AlreadyExistsError, InvalidTransitionError
from hipstraw_mm.store.memory import MemoryStore


@pytest.fixture(params=["memory", pytest.param("firestore", marks=pytest.mark.emulator)])
def store(request):
    if request.param == "memory":
        return MemoryStore()
    from hipstraw_mm.store.firestore import FirestoreStore

    return FirestoreStore(project_id="demo-hipstraw-mvp")


@pytest.fixture
def ids():
    uid = uuid.uuid4().hex[:8]
    run_id = f"run_test{uid}"
    return {
        "program": f"prog_{uid}",
        "candidate": f"prog_{uid}__ctx1",
        "run": run_id,
        "record": f"{run_id}__acme-test",
        "evidence": f"ev_{run_id}_1",
    }


def _program(ids):
    return {
        "programId": ids["program"],
        "name": "Test",
        "objective": "Test objective",
        "sourceUrl": "https://example.test",
        "experimentContexts": [{"id": "ctx1", "label": "Context 1"}],
        "primaryInterests": [{"id": "int1", "label": "Interest 1"}],
        "defaultConstraints": {"maxEmployees": 500, "maxRevenueUsd": 100000000, "metroIds": []},
    }


def _run(ids):
    return {
        "runId": ids["run"],
        "programId": ids["program"],
        "candidateId": ids["candidate"],
        "position": {
            "segment": "test",
            "companyArchetype": "test",
            "buyer": "test",
            "problem": "test",
            "trigger": "test",
            "primaryInterestIds": ["int1"],
            "searchHints": [],
        },
        "constraintsInForce": {"maxEmployees": 500, "maxRevenueUsd": 100000000, "metros": []},
        "budgets": {},
        "model": "test-model",
        "status": "created",
    }


def _evidence(ids):
    return {
        "evidenceId": ids["evidence"],
        "runId": ids["run"],
        "companyRecordId": None,
        "claimField": "origin",
        "claimValue": "Acme Test",
        "url": "https://list.example.test",
        "sourceType": "directory",
        "reliability": "low",
        "publishedAt": None,
        "fetchedAt": "2026-10-07T10:00:00Z",
        "excerpt": "Acme Test makes tests",
        "contentSha256": "abc123",
        "check": {"status": "pass", "reason": None},
    }


def _decision(ids):
    return {
        "companyRecordId": ids["record"],
        "disposition": "needs_verification",
        "reason": "No interest signal",
        "ruleResults": [],
        "judgement": None,
        "reviewer": "market-manager/rules-v1+test-model",
        "reviewedAt": "2026-10-07T10:00:00Z",
    }


def _baseline(ids):
    return {
        "runId": ids["run"],
        "programId": ids["program"],
        "candidateId": ids["candidate"],
        "position": {},
        "constraintsInForce": {},
        "companies": [],
        "baselineAt": "2026-10-07T10:00:00Z",
    }


class TestReadBack:
    def test_program(self, store, ids):
        store.upsert_program(_program(ids))
        assert store.get_program(ids["program"])["programId"] == ids["program"]

    def test_candidate(self, store, ids):
        store.upsert_candidate(
            {
                "candidateId": ids["candidate"],
                "programId": ids["program"],
                "experimentContextId": "ctx1",
                "label": "Context 1",
                "origin": "program_experiment_context",
            }
        )
        assert store.get_candidate(ids["candidate"]) is not None
        assert [c["candidateId"] for c in store.list_candidates(ids["program"])] == [ids["candidate"]]

    def test_run(self, store, ids):
        store.upsert_run(_run(ids))
        got = store.get_run(ids["run"])
        assert got["status"] == "created"
        assert "createdAt" in got

    def test_company_record(self, store, ids):
        store.upsert_company_record(
            ids["record"], {"runId": ids["run"], "name": "Acme Test", "domain": "acme.test", "status": "finding"}
        )
        assert store.get_company_record(ids["record"])["name"] == "Acme Test"
        assert len(store.list_company_records(ids["run"])) == 1

    def test_evidence(self, store, ids):
        store.create_evidence(_evidence(ids))
        assert store.get_evidence(ids["evidence"])["excerpt"] == "Acme Test makes tests"
        assert len(store.list_evidence(ids["run"])) == 1

    def test_review_decision(self, store, ids):
        store.create_review_decision(ids["record"], _decision(ids))
        assert store.get_review_decision(ids["record"])["disposition"] == "needs_verification"

    def test_position_baseline(self, store, ids):
        store.create_position_baseline(ids["run"], _baseline(ids))
        assert store.get_position_baseline(ids["run"])["runId"] == ids["run"]

    def test_demo_report(self, store, ids):
        store.upsert_demo_report(ids["run"], {"runId": ids["run"], "path": "reports/x.md", "sha256": "abc"})
        assert store.get_demo_report(ids["run"])["sha256"] == "abc"

    def test_missing_returns_none(self, store, ids):
        assert store.get_run(ids["run"]) is None


class TestCreateOnly:
    def test_evidence_twice_raises(self, store, ids):
        store.create_evidence(_evidence(ids))
        with pytest.raises(AlreadyExistsError):
            store.create_evidence(_evidence(ids))

    def test_review_decision_twice_raises(self, store, ids):
        store.create_review_decision(ids["record"], _decision(ids))
        with pytest.raises(AlreadyExistsError):
            store.create_review_decision(ids["record"], _decision(ids))

    def test_baseline_twice_raises(self, store, ids):
        store.create_position_baseline(ids["run"], _baseline(ids))
        with pytest.raises(AlreadyExistsError):
            store.create_position_baseline(ids["run"], _baseline(ids))

    def test_baseline_unchanged_after_failed_second_create(self, store, ids):
        store.create_position_baseline(ids["run"], _baseline(ids))
        changed = {**_baseline(ids), "companies": [{"name": "Other"}]}
        with pytest.raises(AlreadyExistsError):
            store.create_position_baseline(ids["run"], changed)
        assert store.get_position_baseline(ids["run"])["companies"] == []

    def test_no_update_methods_for_create_only_collections(self, store):
        for name in dir(store):
            if name.startswith(("update_", "upsert_", "set_", "delete_")):
                assert not name.endswith(("evidence", "review_decision", "position_baseline")), name


class TestRunStateMachine:
    def test_happy_path(self, store, ids):
        store.upsert_run(_run(ids))
        for frm, to in [
            ("created", "discovered"),
            ("discovered", "verified"),
            ("verified", "reviewed"),
            ("reviewed", "reported"),
        ]:
            store.transition_run(ids["run"], frm, to)
            assert store.get_run(ids["run"])["status"] == to

    def test_skipping_a_step_raises(self, store, ids):
        store.upsert_run(_run(ids))
        with pytest.raises(InvalidTransitionError):
            store.transition_run(ids["run"], "created", "verified")

    def test_wrong_from_status_raises(self, store, ids):
        store.upsert_run(_run(ids))
        with pytest.raises(InvalidTransitionError):
            store.transition_run(ids["run"], "discovered", "verified")

    def test_failed_from_any_step(self, store, ids):
        store.upsert_run(_run(ids))
        store.transition_run(ids["run"], "created", "discovered")
        store.transition_run(ids["run"], "discovered", "failed", {"errorStep": "verify", "errorMessage": "boom"})
        got = store.get_run(ids["run"])
        assert got["status"] == "failed"
        assert got["errorStep"] == "verify"

    def test_failed_run_cannot_move_on(self, store, ids):
        store.upsert_run(_run(ids))
        store.transition_run(ids["run"], "created", "failed")
        with pytest.raises(InvalidTransitionError):
            store.transition_run(ids["run"], "failed", "discovered")

    def test_upsert_cannot_change_status(self, store, ids):
        store.upsert_run(_run(ids))
        with pytest.raises(InvalidTransitionError):
            store.upsert_run({**_run(ids), "status": "reported"})

    def test_upsert_keeps_status_and_merges_fields(self, store, ids):
        store.upsert_run(_run(ids))
        store.transition_run(ids["run"], "created", "discovered")
        store.upsert_run({"runId": ids["run"], "counts": {"searches": 3}})
        got = store.get_run(ids["run"])
        assert got["status"] == "discovered"
        assert got["counts"] == {"searches": 3}
        assert got["candidateId"] == ids["candidate"]
