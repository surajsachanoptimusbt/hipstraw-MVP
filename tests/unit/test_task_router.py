"""The task router: a deterministic route choice (never a model call), open-weight first for simple
tasks, validators, escalation to frontier, and the lineage recorded on the trace."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from hipstraw_mm import prompts
from hipstraw_mm.adapters.llm import LLMClient, LLMSchemaError
from hipstraw_mm.adapters.replay import ReplayMissingError, ReplayStore
from hipstraw_mm.errors import ExternalServiceError, TransientServiceError
from hipstraw_mm.market import router as router_mod
from hipstraw_mm.market.layers import load_layers
from hipstraw_mm.market.router import Check, RoutingConfig, TaskRouter, decide_route, load_routing
from hipstraw_mm.market.schemas import DeliberationItem, DimensionDeliberation
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer
from hipstraw_mm.market.vichara import vichara_checks
from hipstraw_mm.store.memory import MemoryStore

OBJECTIVE = "Objective: find mid market finance teams that reconcile vendor invoices by hand"
GOOD_BASIS = "reconcile vendor invoices by hand"


def _config(enabled: bool = True, **policy: Any) -> RoutingConfig:
    raw = load_routing().model_dump(by_alias=True)
    raw["openWeight"].update({"enabled": enabled, **policy})
    return RoutingConfig.model_validate(raw)


# --------------------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------------------


def test_every_prompt_version_is_routed_or_listed_unused() -> None:
    versions = {v for k, v in vars(prompts).items() if k.isupper() and isinstance(v, str)}
    cfg = load_routing()
    assert versions == set(cfg.tasks) | set(cfg.unused)
    assert not set(cfg.tasks) & set(cfg.unused)


def test_slice_wires_only_the_vichara_stage_and_ships_dark() -> None:
    cfg = load_routing()
    assert cfg.openWeight.enabled is False
    wired = {k for k, t in cfg.tasks.items() if t.wired}
    assert wired == {prompts.VICHARA, prompts.VICHARA_COVERAGE, prompts.VICHARA_PROPOSE}
    assert cfg.tasks[prompts.VICHARA].class_ == "simple"


def test_router_module_never_imports_a_model_client() -> None:
    from pathlib import Path

    source = Path(router_mod.__file__).read_text(encoding="utf-8")
    assert "openai" not in source and "anthropic" not in source


# --------------------------------------------------------------------------------------------------
# decide_route: pure, ordered rules
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("task", "enabled", "available", "chars", "failures", "route", "rule"), [
    ("unknown.v9", True, True, 10, 0, "frontier", "R1"),
    (prompts.VICHARA_PROPOSE, True, True, 10, 0, "frontier", "R3"),
    (prompts.VICHARA, False, True, 10, 0, "frontier", "R4"),
    (prompts.VICHARA, True, False, 10, 0, "frontier", "R5"),
    (prompts.VICHARA, True, True, 60_001, 0, "frontier", "R6"),
    (prompts.VICHARA, True, True, 10, 3, "frontier", "R7"),
    (prompts.VICHARA, True, True, 60_000, 2, "open_weight", "R8"),
])
def test_decide_route(task: str, enabled: bool, available: bool, chars: int, failures: int,
                      route: str, rule: str) -> None:
    decision = decide_route(_config(enabled), task, open_weight_available=available,
                            input_chars=chars, consecutive_failures=failures)
    assert (decision.route, decision.ruleId) == (route, rule)
    assert decision.why


def test_rules_class_routes_to_rules() -> None:
    raw = load_routing().model_dump(by_alias=True)
    raw["tasks"][prompts.VICHARA_COVERAGE]["class"] = "rules"
    decision = decide_route(RoutingConfig.model_validate(raw), prompts.VICHARA_COVERAGE,
                            open_weight_available=True, input_chars=10, consecutive_failures=0)
    assert (decision.route, decision.ruleId) == ("rules", "R2")


# --------------------------------------------------------------------------------------------------
# validators for vichara.v1
# --------------------------------------------------------------------------------------------------


def _deliberation(key: str = "segment_fit", *items: DeliberationItem) -> DimensionDeliberation:
    if not items:
        items = (DeliberationItem(question="q", status="answered", answer="a", basis=[GOOD_BASIS]),)
    return DimensionDeliberation(dimensionKey=key, items=list(items))


def _blocking(checks: list[Check]) -> set[str]:
    return {c.name for c in checks if not c.passed and c.blocking}


def test_vichara_checks_pass_a_grounded_answer() -> None:
    checks = vichara_checks(_deliberation(), "open_weight", dimension_key="segment_fit",
                            objective_text=OBJECTIVE, max_items=3, has_documents=True)
    assert all(c.passed for c in checks)


def test_vichara_checks_block_echo_and_grounding() -> None:
    bad = DeliberationItem(question="q", status="answered", answer="a", basis=["not in the objective"])
    checks = vichara_checks(_deliberation("timing", bad), "open_weight", dimension_key="segment_fit",
                            objective_text=OBJECTIVE, max_items=3, has_documents=False)
    assert _blocking(checks) == {"echo_key", "grounding"}


def test_vichara_checks_ignore_items_past_the_kept_limit() -> None:
    good = DeliberationItem(question="q", status="answered", answer="a", basis=[GOOD_BASIS])
    bad = DeliberationItem(question="q", status="answered", answer="a", basis=["not in the objective"])
    checks = vichara_checks(_deliberation("segment_fit", good, bad), "open_weight", dimension_key="segment_fit",
                            objective_text=OBJECTIVE, max_items=1, has_documents=False)
    assert _blocking(checks) == set()


def test_abstention_blocks_only_open_weight_and_only_with_documents() -> None:
    silent = DeliberationItem(question="q", status="unresolved", reason="no information in the objective")
    result = _deliberation("segment_fit", silent)
    kw: dict[str, Any] = {"dimension_key": "segment_fit", "objective_text": OBJECTIVE, "max_items": 3}
    assert _blocking(vichara_checks(result, "open_weight", has_documents=True, **kw)) == {"abstention"}
    assert _blocking(vichara_checks(result, "open_weight", has_documents=False, **kw)) == set()
    assert _blocking(vichara_checks(result, "frontier", has_documents=True, **kw)) == set()


# --------------------------------------------------------------------------------------------------
# TaskRouter: executes the decision, escalates, records lineage
# --------------------------------------------------------------------------------------------------


class FakeTier:
    """A model tier whose behaviour is chosen per match key."""

    def __init__(self, model: str, behaviour: dict[str, str] | None = None) -> None:
        self.model = model
        self.behaviour = behaviour or {}
        self.calls = 0
        self.keys: list[str] = []
        self.last_usage = {"inputTokens": 100, "outputTokens": 20}
        self.last_raw: dict[str, Any] | None = None

    def parse(self, schema: Any, messages: list[dict[str, str]], match_key: str, prompt_version: str,
              **_: Any) -> Any:
        self.calls += 1
        self.keys.append(match_key)
        payload = json.loads(messages[1]["content"])
        mode = next((m for k, m in self.behaviour.items() if match_key.endswith(k)), "pass")
        self.last_raw = {"content": "{}", "model": f"{self.model}-served"}
        if mode == "schema_error":
            self.last_raw = {"content": "{not json", "model": self.model}
            raise LLMSchemaError("DimensionDeliberation: schema validation failed")
        if mode == "transient":
            raise TransientServiceError("timeout")
        if mode == "http400":
            raise ExternalServiceError("BadRequestError: response_format not supported")
        if mode == "replay_missing":
            raise ReplayMissingError("no recording")
        if mode == "unresolved":
            item = DeliberationItem(question="q", status="unresolved", reason="no information in the objective")
        else:
            basis = "a sentence the objective never says" if mode == "bad_basis" else GOOD_BASIS
            item = DeliberationItem(question="q", status="answered", answer="a", basis=[basis])
        result = DimensionDeliberation(dimensionKey=payload["dimensionKey"], items=[item])
        self.last_raw = {"content": result.model_dump_json(), "model": f"{self.model}-served"}
        return result


class Ctx:
    def __init__(self, frontier: FakeTier, open_llm: FakeTier | None) -> None:
        self.llm = frontier
        self.open_llm = open_llm


@pytest.fixture
def tracer_store() -> tuple[Tracer, MemoryStore]:
    store = MemoryStore()
    store.upsert_market_run({"marketRunId": "mrun_t", "status": "opened", "lastSeq": 0, "counts": {}})
    ticks = [1696761600.0]

    def clock() -> datetime:
        ticks[0] += 1
        return datetime.fromtimestamp(ticks[0], tz=timezone.utc)

    tracer = Tracer(store=store, layers=load_layers(), settings=load_pipeline_settings(), run_id="mrun_t", clock=clock)
    return tracer, store


def _deliberate(router: TaskRouter, tracer: Tracer, key: str, *, has_documents: bool = True) -> tuple[Any, dict]:
    payload = {"dimensionKey": key, "question": "q?", "objectiveText": OBJECTIVE}
    with tracer.step("search_research", "vichara", "deliberate_dimension", right="ask_dimension") as step:
        return router.call(
            step, DimensionDeliberation, prompts.messages(prompts.VICHARA, payload),
            task=prompts.VICHARA, match_key=f"vichara:{key}",
            validate=lambda r, tier: vichara_checks(r, tier, dimension_key=key, objective_text=OBJECTIVE,
                                                    max_items=3, has_documents=has_documents),
        )


def test_dark_routes_to_frontier_with_todays_key(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    tracer, _ = tracer_store
    frontier = FakeTier("gpt-4o")
    router = TaskRouter(Ctx(frontier, None), tracer, _config(enabled=False), run_id="mrun_t")
    _, routing = _deliberate(router, tracer, "segment_fit")
    assert frontier.keys == ["vichara:segment_fit"]
    assert routing["servedBy"] == "frontier" and routing["ruleId"] == "R4" and routing["escalated"] is False


def test_open_weight_answer_that_passes_is_kept(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    tracer, store = tracer_store
    frontier, ow = FakeTier("gpt-4o"), FakeTier("qwen-test")
    router = TaskRouter(Ctx(frontier, ow), tracer, _config(), run_id="mrun_t")
    result, routing = _deliberate(router, tracer, "segment_fit")
    assert result.items[0].basis == [GOOD_BASIS]
    assert ow.keys == ["ow:qwen-test:vichara:segment_fit"] and frontier.keys == []
    assert routing["servedBy"] == "open_weight" and routing["ruleId"] == "R8"
    worker = [s for s in store.list_trace_steps_after("mrun_t", 0) if s["operation"] == "call_model"][0]
    assert worker["inputs"]["route"] == "open_weight" and worker["inputs"]["model"] == "qwen-test"
    assert worker["outputs"]["servedModel"] == "qwen-test-served"
    assert worker["model"]["name"] == "qwen-test"


@pytest.mark.parametrize(("mode", "reason"), [
    ("bad_basis", "grounding"),
    ("unresolved", "abstention"),
    ("schema_error", "LLMSchemaError"),
    ("transient", "TransientServiceError"),
    ("http400", "ExternalServiceError"),
    ("replay_missing", "ReplayMissingError"),
])
def test_open_weight_failure_escalates_once_to_frontier(
    tracer_store: tuple[Tracer, MemoryStore], monkeypatch: pytest.MonkeyPatch, mode: str, reason: str
) -> None:
    monkeypatch.setattr("hipstraw_mm.market.stages.time.sleep", lambda s: pytest.fail("open-weight must not back off"))
    tracer, store = tracer_store
    frontier, ow = FakeTier("gpt-4o"), FakeTier("qwen-test", {"segment_fit": mode})
    router = TaskRouter(Ctx(frontier, ow), tracer, _config(), run_id="mrun_t")
    result, routing = _deliberate(router, tracer, "segment_fit")
    assert ow.calls == 1
    assert frontier.keys == ["vichara:segment_fit"]
    assert result.items[0].basis == [GOOD_BASIS]
    assert routing["servedBy"] == "frontier" and routing["escalated"] is True
    assert reason in routing["escalationReason"]
    assert routing["attempts"][0]["route"] == "open_weight"
    workers = [s for s in store.list_trace_steps_after("mrun_t", 0) if s["operation"] == "call_model"]
    assert [w["inputs"]["route"] for w in workers] == ["open_weight", "frontier"]
    business = [s for s in store.list_trace_steps_after("mrun_t", 0) if s["operation"] == "deliberate_dimension"][0]
    if mode in ("bad_basis", "unresolved"):
        assert any(c["name"] == f"open_weight.{reason}" and c["status"] == "fail" for c in business["checks"])


def test_schema_failed_attempt_keeps_its_raw_response(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    tracer, store = tracer_store
    router = TaskRouter(Ctx(FakeTier("gpt-4o"), FakeTier("qwen-test", {"segment_fit": "schema_error"})),
                        tracer, _config(), run_id="mrun_t")
    _deliberate(router, tracer, "segment_fit")
    steps = store.list_trace_steps_after("mrun_t", 0)
    failed = [s for s in steps if s["operation"] == "call_model" and s["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["responseBlobId"]
    assert store.get_trace_blob(failed[0]["responseBlobId"])["content"] == "{not json"


def test_frontier_results_are_validated_but_never_rejected(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    tracer, store = tracer_store
    frontier = FakeTier("gpt-4o", {"segment_fit": "bad_basis"})
    router = TaskRouter(Ctx(frontier, None), tracer, _config(enabled=False), run_id="mrun_t")
    result, _ = _deliberate(router, tracer, "segment_fit")
    assert result.items[0].basis == ["a sentence the objective never says"]
    business = [s for s in store.list_trace_steps_after("mrun_t", 0) if s["operation"] == "deliberate_dimension"][0]
    grounding = [c for c in business["checks"] if c["name"] == "frontier.grounding"]
    assert grounding and grounding[0]["status"] == "fail" and "recorded only" in grounding[0]["reason"]


def test_breaker_sends_the_rest_of_the_stage_to_frontier(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    tracer, _ = tracer_store
    frontier, ow = FakeTier("gpt-4o"), FakeTier("qwen-test", {"": "http400"})
    router = TaskRouter(Ctx(frontier, ow), tracer, _config(), run_id="mrun_t")
    rules = [_deliberate(router, tracer, f"d{i}")[1]["ruleId"] for i in range(5)]
    assert ow.calls == 3
    assert rules == ["R8", "R8", "R8", "R7", "R7"]


def test_rejected_answers_do_not_trip_the_breaker(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    """Weak answers escalate one by one; only a failing endpoint stops the open-weight tier."""
    tracer, _ = tracer_store
    ow = FakeTier("qwen-test", {"": "unresolved"})
    router = TaskRouter(Ctx(FakeTier("gpt-4o"), ow), tracer, _config(), run_id="mrun_t")
    rules = [_deliberate(router, tracer, f"d{i}")[1]["ruleId"] for i in range(5)]
    assert ow.calls == 5 and rules == ["R8"] * 5


def test_breaker_resets_after_a_pass(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    tracer, _ = tracer_store
    ow = FakeTier("qwen-test", {"d0": "http400", "d1": "http400", "d3": "http400", "d4": "http400"})
    router = TaskRouter(Ctx(FakeTier("gpt-4o"), ow), tracer, _config(), run_id="mrun_t")
    rules = [_deliberate(router, tracer, f"d{i}")[1]["ruleId"] for i in range(6)]
    assert rules == ["R8"] * 6


def test_complex_task_never_touches_open_weight(tracer_store: tuple[Tracer, MemoryStore]) -> None:
    tracer, _ = tracer_store
    frontier, ow = FakeTier("gpt-4o"), FakeTier("qwen-test")
    router = TaskRouter(Ctx(frontier, ow), tracer, _config(), run_id="mrun_t")
    payload = {"dimensionKey": "segment_fit", "question": "q?", "objectiveText": OBJECTIVE}
    with tracer.step("search_research", "vichara", "propose_hypotheses", right="ask_dimension") as step:
        _, routing = router.call(step, DimensionDeliberation, prompts.messages(prompts.VICHARA, payload),
                                 task=prompts.VICHARA_PROPOSE, match_key="vichara_propose")
    assert ow.calls == 0 and frontier.keys == ["vichara_propose"]
    assert routing["ruleId"] == "R3" and routing["class"] == "complex"


# --------------------------------------------------------------------------------------------------
# LLMClient: single schema attempt for open-weight, raw response kept
# --------------------------------------------------------------------------------------------------


class _StubCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, **_: Any) -> Any:
        self.calls += 1
        raise ValueError("unreachable")


def test_llm_client_single_schema_attempt_and_last_raw(tmp_path: Any) -> None:
    replay = ReplayStore(tmp_path, mode="record")
    client = LLMClient(model="qwen-test", replay=replay, schema_attempts=1)
    bad = {"content": "{not json", "refusal": None, "model": "qwen-test"}
    client._live = lambda schema, messages: bad  # type: ignore[method-assign]
    with pytest.raises(LLMSchemaError):
        client.parse(DimensionDeliberation, [{"role": "user", "content": "x"}], "k", "vichara.v1")
    assert client.calls == 1
    assert client.last_raw == bad
