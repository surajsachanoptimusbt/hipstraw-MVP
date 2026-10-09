"""T005: Unit tests for src/hipstraw_mm/market/trace.py (the Tracer)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hipstraw_mm.market.layers import load_layers
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer
from hipstraw_mm.store.base import InvalidTransitionError
from hipstraw_mm.store.memory import MemoryStore

FR023_FIELDS = [
    "marketRunId", "seq", "stepId", "parentStepId", "layer", "actor", "operation",
    "status", "inputs", "outputs", "decision", "right", "rationale", "alternatives",
    "checks", "model", "promptBlobId", "responseBlobId", "toolCalls", "cost",
    "latencyMs", "startedAt", "endedAt", "error",
]


def _clock(start: float = 1696761600.0):
    ts = [start]
    def tick():
        ts[0] += 1.0
        return datetime.fromtimestamp(ts[0], tz=timezone.utc)
    return tick


@pytest.fixture
def setup():
    store = MemoryStore()
    layers = load_layers()
    settings = load_pipeline_settings()
    run_id = "mrun_test"
    store.upsert_market_run({"marketRunId": run_id, "status": "opened", "lastSeq": 0, "counts": {}})
    clock = _clock()
    tracer = Tracer(store=store, layers=layers, settings=settings, run_id=run_id, clock=clock)
    return store, tracer, run_id


class TestTracerStep:
    def test_opening_writes_running_record(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "test_op", right="open_run"):
            doc = store.get_trace_step(f"{run_id}__000001")
            assert doc is not None
            assert doc["status"] == "running"

    def test_all_fr023_fields_present_and_empty_when_not_set(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "test_op", right="open_run"):
            pass
        doc = store.get_trace_step(f"{run_id}__000001")
        for field in FR023_FIELDS:
            assert field in doc, f"FR-023 field {field!r} missing"

    def test_leaving_block_seals_ok(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "test_op", right="open_run") as step:
            step.set_outputs({"result": "done"})
        doc = store.get_trace_step(f"{run_id}__000001")
        assert doc["status"] == "ok"
        assert doc["endedAt"] is not None

    def test_exception_seals_failed_and_reraises(self, setup) -> None:
        store, tracer, run_id = setup
        with pytest.raises(ValueError, match="boom"), tracer.step(
            "market_manager", "market_manager", "test_op", right="open_run",
        ):
            raise ValueError("boom")
        doc = store.get_trace_step(f"{run_id}__000001")
        assert doc["status"] == "failed"
        assert doc["error"] is not None

    def test_sealing_twice_raises(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "test_op", right="open_run"):
            pass
        with pytest.raises(InvalidTransitionError):
            store.finish_trace_step(f"{run_id}__000001", {"status": "ok"})

    def test_seq_increases_and_lastseq_follows(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "op1", right="open_run"):
            pass
        with tracer.step("market_manager", "market_manager", "op2", right="open_run"):
            pass
        run_doc = store.get_market_run(run_id)
        assert run_doc["lastSeq"] == 2
        assert store.get_trace_step(f"{run_id}__000001") is not None
        assert store.get_trace_step(f"{run_id}__000002") is not None

    def test_parent_step_id_set_for_nested_steps(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "parent_op", right="open_run"):  # noqa: SIM117
            with tracer.step("workers", "llm_worker", "child_op", right="call_model"):
                pass
        child_doc = store.get_trace_step(f"{run_id}__000002")
        assert child_doc["parentStepId"] == f"{run_id}__000001"

    def test_undeclared_layer_raises(self, setup) -> None:
        store, tracer, run_id = setup
        with pytest.raises(ValueError, match="layer"), tracer.step(
            "bad_layer", "market_manager", "op", right="open_run",
        ):
            pass

    def test_undeclared_actor_raises(self, setup) -> None:
        store, tracer, run_id = setup
        with pytest.raises(ValueError, match="actor"), tracer.step(
            "market_manager", "bad_actor", "op", right="open_run",
        ):
            pass

    def test_undeclared_right_raises(self, setup) -> None:
        store, tracer, run_id = setup
        with pytest.raises(ValueError, match="right"), tracer.step(
            "market_manager", "market_manager", "op", right="bad_right",
        ):
            pass


class TestTracerObserver:
    def test_observer_events_become_tool_calls(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("workers", "llm_worker", "model_op", right="call_model"):
            tracer.observe_tool_call(kind="model", target="gpt-4o", status="ok", detail="test")
        doc = store.get_trace_step(f"{run_id}__000001")
        assert len(doc["toolCalls"]) == 1
        assert doc["toolCalls"][0]["kind"] == "model"

    def test_model_call_stores_blob_ids(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("workers", "llm_worker", "model_op", right="call_model") as step:
            step.record_model_call(
                name="gpt-4o", prompt_version="v1", schema="TestSchema", attempt=1,
                prompt_content='{"test": true}', response_content='{"result": true}',
                usage={"inputTokens": 100, "outputTokens": 50},
            )
        doc = store.get_trace_step(f"{run_id}__000001")
        assert doc["promptBlobId"] is not None
        assert doc["responseBlobId"] is not None


class TestTracerLatencyAndCost:
    def test_latency_measured_from_clock(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "op", right="open_run"):
            pass
        doc = store.get_trace_step(f"{run_id}__000001")
        assert doc["latencyMs"] is not None
        assert isinstance(doc["latencyMs"], int)
        assert doc["latencyMs"] > 0

    def test_cost_null_for_unknown(self, setup) -> None:
        store, tracer, run_id = setup
        with tracer.step("market_manager", "market_manager", "op", right="open_run"):
            pass
        doc = store.get_trace_step(f"{run_id}__000001")
        assert doc["cost"]["usd"] is None


class TestTracerBlobTruncation:
    def test_blob_over_limit_is_truncated(self, setup) -> None:
        store, tracer, run_id = setup
        big_content = "x" * 1_000_000
        with tracer.step("workers", "llm_worker", "model_op", right="call_model") as step:
            step.record_model_call(
                name="gpt-4o", prompt_version="v1", schema="TestSchema", attempt=1,
                prompt_content=big_content, response_content="ok",
                usage=None,
            )
        blob_id = f"{run_id}__000001__0"
        blob = store.get_trace_blob(blob_id)
        assert blob is not None
        assert blob["truncated"] is True
        assert blob["bytes"] == 1_000_000


class TestTracerModelCallCeiling:
    def test_exceeding_ceiling_raises(self, setup) -> None:
        store, tracer, run_id = setup
        ceiling = load_pipeline_settings().budgets.modelCallsPerRun
        tracer._model_call_count = ceiling - 1
        with tracer.step("workers", "llm_worker", "op", right="call_model"):
            tracer.observe_model_call()
        assert tracer._model_call_count == ceiling
        with pytest.raises(Exception, match="ceiling|budget"), tracer.step(
            "workers", "llm_worker", "op2", right="call_model",
        ):
            tracer.observe_model_call()
