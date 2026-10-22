"""Child-run task routing on a recorded scenario: feature 002's real discover, verify and review, with
replayed model, search and fetch responses. With the router attached and the open-weight route off,
the stored companies, evidence and decisions are exactly those of the plain run, and every child model
call is now a traced, routed step with its worker step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hipstraw_mm import cli
from hipstraw_mm.adapters.llm import LLMClient
from hipstraw_mm.config import LoadedConfig
from hipstraw_mm.logging_setup import EventLog
from hipstraw_mm.market.layers import load_layers
from hipstraw_mm.market.router import TaskRouter, load_routing
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer
from hipstraw_mm.store.memory import MemoryStore
from tests.integration.harness import FIXED_NOW, Harness, require_success, run_basic

MARKET_RUN = "mrun_child_routing"
VOLATILE = {"createdAt", "updatedAt"}


def _harness(tmp_path: Path, adapters: Any, routed: bool) -> Harness:
    store = MemoryStore()
    runs_dir, reports_dir = tmp_path / f"runs_{routed}", tmp_path / f"reports_{routed}"
    log = EventLog(runs_dir=runs_dir, stream=None, clock=lambda: FIXED_NOW)
    tracer = None
    if routed:
        store.upsert_market_run({"marketRunId": MARKET_RUN, "status": "assessed", "lastSeq": 0, "counts": {}})
        tracer = Tracer(store=store, layers=load_layers(Path("config")),
                        settings=load_pipeline_settings(Path("config")), run_id=MARKET_RUN, clock=lambda: FIXED_NOW)

    def context_factory(config: LoadedConfig) -> cli.Context:
        ctx = cli.Context(config=config, store=store, log=log,
                          llm=LLMClient(model=config.run.model.name, replay=adapters.replay, log=log),
                          search=adapters.search, new_fetcher=adapters.new_fetcher, reports_dir=reports_dir,
                          now=lambda: FIXED_NOW)
        if tracer is not None:
            ctx.router = TaskRouter(ctx, tracer, load_routing(Path("config")), run_id=MARKET_RUN)
        return ctx

    return Harness(store, runs_dir, reports_dir, context_factory)


def _snapshot(store: MemoryStore, run_id: str) -> dict[str, Any]:
    def clean(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(({k: v for k, v in d.items() if k not in VOLATILE} for d in docs), key=repr)

    records = store.list_company_records(run_id)
    return {
        "records": clean(records),
        "evidence": clean(store.list_evidence(run_id)),
        "decisions": clean([d for r in records if (d := store.get_review_decision(r["companyRecordId"]))]),
    }


def test_routed_child_runs_store_exactly_what_plain_runs_store(tmp_path: Path, replay_adapters: Any) -> None:
    plain = require_success(run_basic(_harness(tmp_path, replay_adapters("us1"), routed=False)))
    routed = require_success(run_basic(_harness(tmp_path, replay_adapters("us1"), routed=True)))
    assert _snapshot(routed.store, routed.run_id) == _snapshot(plain.store, plain.run_id)

    steps = routed.store.list_trace_steps_after(MARKET_RUN, 0)
    business = [s for s in steps if (s.get("outputs") or {}).get("routing")]
    ops = {s["operation"] for s in business}
    assert {"plan_queries", "extract_listing", "extract_evidence"} <= ops
    for s in business:
        r = s["outputs"]["routing"]
        expected = "R3" if s["operation"] in ("extract_evidence", "judge_company") else "R4"
        assert (r["ruleId"], r["servedBy"]) == (expected, "frontier"), s["operation"]
        assert s["inputs"]["childRunId"] == routed.run_id
    workers = [s for s in steps if s["operation"] == "call_model"]
    assert {w["parentStepId"] for w in workers} <= {s["stepId"] for s in business}
    assert len(workers) >= len(business)
    run = routed.store.get_market_run(MARKET_RUN)
    assert run["counts"]["modelCalls"] == len(workers)
