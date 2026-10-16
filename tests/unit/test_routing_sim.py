"""The routing simulation: the real vichara stage with the open-weight route on, read back from the trace
as a walk-through in the order of the routing diagram."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hipstraw_mm.market import schemas
from hipstraw_mm.market.grammar import load_grammar
from hipstraw_mm.market.routing_sim import render_text, simulate
from hipstraw_mm.steps.intake import intake
from tests.unit.test_market_pipeline_e2e import (
    BAD_DIMENSION,
    CONFIG_DIR,
    PDF_PHRASE,
    SILENT_DIMENSION,
    ScriptedLLM,
    _context,
    make_pdf,
)


class OpenWeight(ScriptedLLM):
    """Answers well except: an ungrounded basis on BAD_DIMENSION, an abstention on SILENT_DIMENSION."""

    model = "qwen-test"

    def __init__(self) -> None:
        super().__init__()
        self.last_raw = {"model": "qwen-test-served"}
        self.last_usage = {"inputTokens": 1000, "outputTokens": 100}

    def _dimension_deliberation(self, p: dict[str, Any]) -> Any:
        key = p["dimensionKey"]
        if key == SILENT_DIMENSION:
            item = schemas.DeliberationItem(question="q", status="unresolved", reason="no information in the objective")
        else:
            basis = "text that is not in the objective" if key == BAD_DIMENSION else PDF_PHRASE
            item = schemas.DeliberationItem(question="q", status="answered", answer="a", basis=[basis])
        return schemas.DimensionDeliberation(dimensionKey=key, items=[item])


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[dict[str, Any], Any, Any]:
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    pdf = tmp_path / "objective.pdf"
    pdf.write_bytes(make_pdf(PDF_PHRASE))
    ctx = _context(tmp_path)
    ow = OpenWeight()
    ctx.open_llm = ow  # type: ignore[assignment]
    intake(ctx, "invoice_alpha")
    result = simulate(ctx, "invoice_alpha_genesis", [pdf], CONFIG_DIR)
    return result, ctx, ow


def test_runs_the_real_stage_and_leaves_routing_policy_untouched(sim: tuple[dict[str, Any], Any, Any]) -> None:
    result, ctx, ow = sim
    run = ctx.store.get_market_run(result["runId"])
    assert run["status"] == "deliberated"
    assert run["simulation"] == {"stage": "vichara", "routerVersion": "router.v1"}
    assert result["openWeight"] == {"model": "qwen-test", "available": True}
    assert result["frontier"] == {"model": "gpt-4o"}
    assert result["program"]["programId"] == "invoice_alpha_genesis"
    assert [d["fileName"] for d in result["objective"]["documents"]] == ["objective.pdf"]
    dims = len(load_grammar(CONFIG_DIR).dimensions)
    assert ow.calls == dims


def test_rubric_covers_every_task_without_a_model_call(sim: tuple[dict[str, Any], Any, Any]) -> None:
    result, _, _ = sim
    rows = {r["task"]: r for r in result["rubric"]}
    assert len(rows) == 15
    assert (rows["vichara.v1"]["route"], rows["vichara.v1"]["ruleId"]) == ("open_weight", "R8")
    assert (rows["graph_level.v2"]["route"], rows["graph_level.v2"]["ruleId"]) == ("frontier", "R3")
    assert rows["listing_extraction.v2"]["wired"] is False


def test_walkthrough_follows_each_task_to_its_saved_result(sim: tuple[dict[str, Any], Any, Any]) -> None:
    result, _, _ = sim
    by_subject = {e["subject"]: e for e in result["walkthrough"] if e["task"] == "vichara.v1"}
    kept = by_subject["segment_fit"]
    assert kept["router"]["ruleId"] == "R8" and kept["outcome"]["servedBy"] == "open_weight"
    assert [a["tier"] for a in kept["attempts"]] == ["open_weight"]
    assert kept["question"]
    assert kept["saved"]["lineage"]["servedBy"] == "open_weight"

    assert {c["id"] for c in kept["validation"]["open_weight"]} == {"schema", "echo_key", "grounding", "abstention"}
    assert result["validationRubric"]["version"] == "validation.v1"

    bad = by_subject[BAD_DIMENSION]
    ground = next(c for c in bad["validation"]["open_weight"] if c["id"] == "grounding")
    assert ground["details"]["quotes"][0]["diagnosis"]["verdict"] == "not_found"
    assert [a["tier"] for a in bad["attempts"]] == ["open_weight", "frontier"]
    assert bad["outcome"]["escalated"] is True
    assert any(c["name"] == "open_weight.grounding" and c["status"] == "fail" for c in bad["checks"])

    silent = by_subject[SILENT_DIMENSION]
    assert "abstention" in silent["outcome"]["escalationReason"]

    tasks = [e["task"] for e in result["walkthrough"]]
    assert "vichara_coverage.v1" in tasks and "vichara_propose.v1" in tasks
    repair = [e for e in result["walkthrough"] if e["task"] == "vichara_repair.v1"]
    assert repair and repair[0]["routed"] is False


def test_summary_counts_tiers_escalations_and_cost(sim: tuple[dict[str, Any], Any, Any]) -> None:
    result, ctx, ow = sim
    s = result["summary"]
    dims = len(load_grammar(CONFIG_DIR).dimensions)
    assert s["routedCalls"] == dims + 2
    assert s["keptOnOpenWeight"] == dims - 2
    assert s["escalated"] == 2
    assert s["escalationReasons"] == {"abstention": 1, "grounding": 1}
    assert s["modelCalls"]["open_weight"] == ow.calls
    assert s["modelCalls"]["frontier"] == ctx.llm.calls
    assert s["cost"]["frontierEquivalentOfKept"] > 0
    entries = result["walkthrough"]
    assert sum(e["allFrontierUsd"] for e in entries) == pytest.approx(s["cost"]["allFrontierEstimateUsd"], abs=1e-3)
    assert sum(e["costUsd"] for e in entries) == pytest.approx(s["cost"]["totalUsd"], abs=1e-3)


def test_attempts_carry_answer_previews(sim: tuple[dict[str, Any], Any, Any]) -> None:
    result, _, _ = sim
    bad = next(e for e in result["walkthrough"] if e["subject"] == BAD_DIMENSION and e["task"] == "vichara.v1")
    assert bad["attempts"][0]["answer"]["basis"] == "text that is not in the objective"
    silent = next(e for e in result["walkthrough"] if e["subject"] == SILENT_DIMENSION and e["task"] == "vichara.v1")
    assert silent["attempts"][0]["answer"]["status"] == "unresolved"
    kept = next(e for e in result["walkthrough"] if e["subject"] == "segment_fit")
    assert kept["saved"]["answer"]["basis"] == PDF_PHRASE


def test_text_walkthrough_reads_in_diagram_order(sim: tuple[dict[str, Any], Any, Any]) -> None:
    result, _, _ = sim
    text = render_text(result)
    for heading in ("RUBRIC", "WALK-THROUGH", "SUMMARY"):
        assert heading in text
    block = text[text.index(f"vichara.v1 | {BAD_DIMENSION}"):]
    order = ["Incoming task", "Router", "Open-weight", "Validation", "Frontier", "Saved"]
    positions = [block.index(word) for word in order]
    assert positions == sorted(positions)
