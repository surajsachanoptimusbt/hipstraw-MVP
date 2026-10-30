"""T041: the stage runner. Stages run in order; Moves in a stage read the same stage-start state; human
deviations between stages are recorded; every executed Move is in the tactic record (C10)."""

from __future__ import annotations

from typing import Any

import pytest

from hipstraw_mm.campaign import moves
from hipstraw_mm.campaign.models import AuditEvent, Deviation, Escalation, LineRun, MoveExecution, ReviewRun
from hipstraw_mm.campaign.runner import deviate, run_line, run_move, step_line, stop_line
from hipstraw_mm.campaign.selection import choose_line
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError, UsageError
from tests.unit.campaign_moves_support import CONFIG, NOW, context, launch

CM = {"by": "Demo CM", "role": "campaign_manager", "now": NOW}


def _chosen(name: str = "launch_complete.yaml", line: str = "L01") -> tuple[SqliteCampaignStore, str, str]:
    store, launch_id = launch(name)
    run = choose_line(store, CONFIG, launch_id, line, reason="test", **CM)
    return store, launch_id, run.lineRunId


def _executed(store: SqliteCampaignStore, launch_id: str) -> list[str]:
    return [e.moveId for e in store.list_for_launch(MoveExecution, launch_id)]


def test_step_runs_one_stage() -> None:
    store, launch_id, run_id = _chosen()
    result = step_line(store, CONFIG, run_id, **CM)
    assert result.stageIndex == 0 and [e.moveId for e in result.executions] == ["M01"]
    run = store.get(LineRun, run_id)
    assert run is not None and (run.state, run.nextStage) == ("staged", 1)


def test_l01_end_to_end_with_a_skip() -> None:
    store, launch_id, run_id = _chosen()
    step_line(store, CONFIG, run_id, **CM)
    deviation = deviate(store, CONFIG, run_id, skip="M05", reason="dates confirmed by phone", **CM)
    assert (deviation.type, deviation.moveId, deviation.beforeStage) == ("skipped", "M05", 1)
    results = run_line(store, CONFIG, run_id, **CM)
    assert [r.stageIndex for r in results] == [1, 2]
    assert _executed(store, launch_id) == ["M01", "M04", "M13", "M12"]
    run = store.get(LineRun, run_id)
    assert run is not None and run.state == "completed" and run.plannedStages == [["M01"], ["M04", "M13"], ["M12"]]
    assert run.reviewId is not None and store.get(ReviewRun, run.reviewId) is not None
    assert [d.reason for d in store.list_for_launch(Deviation, launch_id)] == ["dates confirmed by phone"]
    actions = [e.action for e in store.list_for_launch(AuditEvent, launch_id)]
    assert actions.count("run_line") == 3 and actions.count("deviate") == 1


def test_moves_in_one_stage_read_the_stage_start_state() -> None:
    # M04 opens the landing-page blocker in stage 2. M12 added to the same stage must not see it;
    # M12 in stage 3 must.
    store, launch_id, run_id = _chosen("launch_missing_landing.yaml")
    step_line(store, CONFIG, run_id, **CM)
    deviate(store, CONFIG, run_id, add="M12", stage=2, reason="escalate early", **CM)
    run_line(store, CONFIG, run_id, **CM)
    escalations = store.list_for_launch(Escalation, launch_id)
    assert len(escalations) == 2
    early, late = escalations
    assert not any(ref.startswith("B") for ref in early.itemRefs)
    assert any(ref.startswith("B") for ref in late.itemRefs)


def test_add_inserts_a_new_stage_next_by_default() -> None:
    store, launch_id, run_id = _chosen()
    deviate(store, CONFIG, run_id, add="M08", reason="ask for proof first", **CM)
    run = store.get(LineRun, run_id)
    assert run is not None and run.plannedStages[0] == ["M08"]


def test_an_external_effect_move_cannot_be_added() -> None:
    store, _, run_id = _chosen()
    with pytest.raises(PreconditionError, match="M10"):
        deviate(store, CONFIG, run_id, add="M10", reason="x", **CM)


def test_unknown_move_cannot_be_added_or_skipped() -> None:
    store, _, run_id = _chosen()
    with pytest.raises(UsageError, match="M77"):
        deviate(store, CONFIG, run_id, add="M77", reason="x", **CM)
    with pytest.raises(PreconditionError, match="M09.*not in a remaining stage"):
        deviate(store, CONFIG, run_id, skip="M09", reason="x", **CM)


def test_stop_abandons_the_line_and_still_opens_a_review() -> None:
    store, launch_id, run_id = _chosen()
    step_line(store, CONFIG, run_id, **CM)
    run = stop_line(store, CONFIG, run_id, reason="Sponsor paused the launch", **CM)
    assert run.state == "abandoned" and run.reviewId is not None
    assert [d.type for d in store.list_for_launch(Deviation, launch_id)] == ["stopped"]
    with pytest.raises(PreconditionError, match="abandoned"):
        step_line(store, CONFIG, run_id, **CM)


def test_skipping_every_remaining_move_abandons_the_line() -> None:
    store, _, run_id = _chosen()
    for move_id in ("M01", "M04", "M05", "M13", "M12"):
        deviate(store, CONFIG, run_id, skip=move_id, reason="human-directed instead", **CM)
    run = store.get(LineRun, run_id)
    assert run is not None and run.state == "abandoned" and run.reviewId is not None


def test_a_failing_move_is_recorded_and_the_stage_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_ctx: Any) -> None:
        raise RuntimeError("criteria file unreadable")

    monkeypatch.setitem(moves.HANDLERS, "readiness.completeness", boom)
    store, launch_id, run_id = _chosen()
    run_line(store, CONFIG, run_id, **CM)
    by_move = {e.moveId: e for e in store.list_for_launch(MoveExecution, launch_id)}
    assert by_move["M04"].status == "failed" and "criteria file unreadable" in (by_move["M04"].error or "")
    assert by_move["M05"].status == "succeeded" and "M12" in by_move


def test_completed_line_cannot_step_again() -> None:
    store, _, run_id = _chosen()
    run_line(store, CONFIG, run_id, **CM)
    with pytest.raises(PreconditionError, match="completed"):
        step_line(store, CONFIG, run_id, **CM)


def test_only_the_campaign_manager_runs_a_line() -> None:
    store, _, run_id = _chosen()
    with pytest.raises(PreconditionError, match="run_line"):
        step_line(store, CONFIG, run_id, by="Demo Sponsor", role="sponsor", now=NOW)


def test_an_external_effect_is_blocked_by_the_gate_and_its_handler_never_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    monkeypatch.setitem(moves.HANDLERS, "testing.dispatch_blocked", lambda ctx: called.append("ran"))
    store, launch_id = launch()
    execution = run_move(context(store, launch_id, "M10"), stage_index=0)
    assert execution.status == "blocked" and "no approved Test Plan" in execution.gate
    assert called == []


def test_ineligible_move_is_blocked_with_the_reason() -> None:
    store, launch_id = launch()  # no metrics, so M03 is not eligible
    execution = run_move(context(store, launch_id, "M03"), stage_index=0)
    assert execution.status == "blocked" and "metrics supplied" in execution.gate


def test_every_move_execution_is_traced() -> None:
    store, launch_id, run_id = _chosen()
    run_line(store, CONFIG, run_id, **CM)
    steps = {s["stepId"]: s for s in store.list_trace_steps(launch_id)}
    for execution in store.list_for_launch(MoveExecution, launch_id):
        step = steps[execution.traceStepId or ""]
        assert (step["layer"], step["actor"], step["operation"]) == ("readiness_testing", "move_runner", "run_move")
        assert step["inputs"]["moveId"] == execution.moveId
