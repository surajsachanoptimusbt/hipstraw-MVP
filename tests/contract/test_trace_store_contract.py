"""T007: Store contract tests for trace collections on both stores."""

from __future__ import annotations

import pytest

from hipstraw_mm.store.base import AlreadyExistsError, InvalidTransitionError
from hipstraw_mm.store.memory import MemoryStore

MARKET_RUN_STAGES = [
    "opened", "deliberated", "defined", "graphed", "validated", "linked",
    "searched", "assessed", "verified", "roled", "decided", "reported",
]


def _make_run(store, run_id: str = "mrun_test", status: str = "opened"):
    store.upsert_market_run({
        "marketRunId": run_id, "status": status, "lastSeq": 0, "counts": {},
    })


def _make_step(store, run_id: str, seq: int, status: str = "running"):
    step_id = f"{run_id}__{seq:06d}"
    store.create_trace_step({
        "stepId": step_id, "marketRunId": run_id, "seq": seq, "status": status,
        "layer": "workers", "actor": "llm_worker", "operation": "test",
        "inputs": {}, "outputs": {}, "decision": None, "right": "call_model",
        "rationale": None, "alternatives": [], "checks": [], "model": None,
        "promptBlobId": None, "responseBlobId": None, "toolCalls": [],
        "cost": {"inputTokens": None, "outputTokens": None, "usd": None},
        "latencyMs": None, "startedAt": None, "endedAt": None, "error": None,
        "parentStepId": None,
    })
    return step_id


@pytest.fixture(params=["memory"])
def store(request):
    if request.param == "memory":
        return MemoryStore()


@pytest.fixture
def emulator_store():
    pytest.importorskip("hipstraw_mm.store.firestore")
    from hipstraw_mm.store.firestore import FirestoreStore
    return FirestoreStore("demo-hipstraw-mvp")


@pytest.mark.emulator
class TestTraceStoreContractEmulator:
    def test_trace_step_seal_once(self, emulator_store) -> None:
        store = emulator_store
        _make_run(store, "mrun_seal_emu")
        step_id = _make_step(store, "mrun_seal_emu", 1)
        store.finish_trace_step(step_id, {"status": "ok", "endedAt": "2026-01-01T00:00:00Z"})
        with pytest.raises(InvalidTransitionError):
            store.finish_trace_step(step_id, {"status": "ok", "endedAt": "2026-01-01T00:00:00Z"})

    def test_trace_blob_create_only(self, emulator_store) -> None:
        store = emulator_store
        blob_id = "mrun_seal_emu__000001__0"
        store.create_trace_blob({
            "blobId": blob_id, "marketRunId": "mrun_seal_emu", "stepId": "mrun_seal_emu__000001",
            "kind": "prompt", "content": '{}', "truncated": False, "bytes": 2,
        })
        with pytest.raises(AlreadyExistsError):
            store.create_trace_blob({
                "blobId": blob_id, "marketRunId": "mrun_seal_emu", "stepId": "mrun_seal_emu__000001",
                "kind": "prompt", "content": '{}', "truncated": False, "bytes": 2,
            })


class TestTraceStoreContractMemory:
    def test_trace_step_seal_once(self, store) -> None:
        _make_run(store)
        step_id = _make_step(store, "mrun_test", 1)
        store.finish_trace_step(step_id, {"status": "ok", "endedAt": "2026-01-01T00:00:00Z"})
        with pytest.raises(InvalidTransitionError):
            store.finish_trace_step(step_id, {"status": "ok", "endedAt": "2026-01-01T00:00:00Z"})

    def test_trace_step_seal_failed(self, store) -> None:
        _make_run(store)
        step_id = _make_step(store, "mrun_test", 1)
        store.finish_trace_step(step_id, {"status": "failed", "error": "boom", "endedAt": "2026-01-01T00:00:00Z"})
        doc = store.get_trace_step(step_id)
        assert doc["status"] == "failed"

    def test_trace_blob_create_only(self, store) -> None:
        blob_id = "mrun_test__000001__0"
        store.create_trace_blob({
            "blobId": blob_id, "marketRunId": "mrun_test", "stepId": "mrun_test__000001",
            "kind": "prompt", "content": '{"test": true}', "truncated": False, "bytes": 15,
        })
        with pytest.raises(AlreadyExistsError):
            store.create_trace_blob({
                "blobId": blob_id, "marketRunId": "mrun_test", "stepId": "mrun_test__000001",
                "kind": "prompt", "content": '{"test": true}', "truncated": False, "bytes": 15,
            })

    def test_list_trace_steps_after_ascending_includes_running(self, store) -> None:
        _make_run(store)
        _make_step(store, "mrun_test", 1, "ok")
        _make_step(store, "mrun_test", 2, "running")
        _make_step(store, "mrun_test", 3, "ok")
        steps = store.list_trace_steps_after("mrun_test", 1)
        assert [s["seq"] for s in steps] == [2, 3]
        assert steps[0]["status"] == "running"

    def test_get_trace_steps_returns_current_state(self, store) -> None:
        _make_run(store)
        _make_step(store, "mrun_test", 1, "running")
        store.finish_trace_step("mrun_test__000001", {"status": "ok", "endedAt": "2026-01-01T00:00:00Z"})
        result = store.get_trace_steps("mrun_test", [1])
        assert result[0]["status"] == "ok"


class TestMarketRunTransitions:
    def test_valid_stage_sequence(self, store) -> None:
        _make_run(store, "mrun_trans")
        for from_s, to_s in zip(MARKET_RUN_STAGES, MARKET_RUN_STAGES[1:]):
            store.transition_market_run("mrun_trans", from_s, to_s)

    def test_any_stage_can_fail(self, store) -> None:
        for stage in MARKET_RUN_STAGES[:-1]:
            run_id = f"mrun_fail_{stage}"
            _make_run(store, run_id, status=stage)
            store.transition_market_run(run_id, stage, "failed")
            doc = store.get_market_run(run_id)
            assert doc["status"] == "failed"

    def test_invalid_transition_raises(self, store) -> None:
        _make_run(store, "mrun_bad")
        with pytest.raises(InvalidTransitionError):
            store.transition_market_run("mrun_bad", "opened", "graphed")

    def test_failed_run_cannot_transition(self, store) -> None:
        _make_run(store, "mrun_stuck", status="failed")
        with pytest.raises(InvalidTransitionError):
            store.transition_market_run("mrun_stuck", "failed", "opened")
