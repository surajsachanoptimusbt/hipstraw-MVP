"""The stage runner (HA section 5, "How a Line runs without a compiler").

A Line's stages run in order. The Moves in one stage all read the same stage-start state, and their
outcomes merge only after the stage, so the order within a stage never matters (research R5). Between
stages the Campaign Manager may skip a Move, add one, or stop the Line; each is a deviation in the tactic
record (C10). Every Line, finished or stopped, ends in a Review.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hipstraw_mm.campaign import moves
from hipstraw_mm.campaign.audit import record_audit
from hipstraw_mm.campaign.conditions import evaluate as evaluate_condition
from hipstraw_mm.campaign.conditions import facts_from_items
from hipstraw_mm.campaign.config import load_roles
from hipstraw_mm.campaign.gate import authorize, gate_move
from hipstraw_mm.campaign.models import (
    Deviation,
    LineRun,
    MoveExecution,
    PositionSnapshot,
    TestPlan,
)
from hipstraw_mm.campaign.moves.common import Fetch, ItemAllocator, MoveContext, MoveOutcome, build_move_context
from hipstraw_mm.campaign.repertoire import Repertoire, load_repertoire
from hipstraw_mm.campaign.review import draft_review
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.campaign.working import working_items
from hipstraw_mm.errors import PreconditionError, UsageError
from hipstraw_mm.logging_setup import scrub


@dataclass
class StageResult:
    stageIndex: int
    executions: list[MoveExecution]
    reviewId: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_move(ctx: MoveContext, *, stage_index: int) -> MoveExecution:
    """The authority gate, then eligibility, then the handler. The gate goes first so an external effect is
    refused for lack of authority whatever else holds. A refusal or failure is recorded, not raised."""
    move = ctx.move
    started = _utc_now()
    outcome = MoveOutcome()
    error: str | None = None
    with ctx.tracer.step("readiness_testing", "move_runner", "run_move", right="run_move") as step:
        step.set_inputs({"moveId": move.id, "moveVersion": move.version, "lineRunId": ctx.line_run_id,
                         "stage": stage_index + 1, "effectClasses": list(move.effectClasses),
                         "itemsAtStageStart": len(ctx.items)})
        allowed, gate = gate_move(ctx.tracer, move)
        if allowed and move.eligibility is not None:
            facts = facts_from_items(ctx.mandate, ctx.items, ctx.now.date(),
                                     ctx.store.list_for_launch(TestPlan, ctx.launch_id))
            allowed, reasons = evaluate_condition(move.eligibility, facts)
            if not allowed:
                gate = "eligibility not met: " + "; ".join(reasons)
        if not allowed:
            outcome.status = "blocked"
        else:
            try:
                outcome = moves.HANDLERS[move.handler](ctx)
            except Exception as exc:  # a failing Move is recorded and the stage goes on
                outcome = MoveOutcome(status="failed")
                error = scrub(f"{type(exc).__name__}: {exc}")
            if outcome.status == "blocked" and outcome.note:
                gate = outcome.note
        step.add_check("gate", "pass" if outcome.status != "blocked" else "fail", gate)
        step.set_outputs({"status": outcome.status, "newItems": [i.itemId for i in outcome.newItems],
                          "transitions": [f"{t.itemId}:{t.fromState}->{t.toState}" for t in outcome.transitions],
                          "produced": outcome.produced, "note": outcome.note, "error": error})
        step.set_decision(outcome.status, outcome.note or gate)
        execution = MoveExecution(
            executionId=f"mx_{uuid.uuid4().hex[:12]}", lineRunId=ctx.line_run_id, launchId=ctx.launch_id,
            stageIndex=stage_index, moveId=move.id, moveVersion=move.version or 0,
            effectClasses=list(move.effectClasses), status=outcome.status, gate=gate, startedAt=started,
            endedAt=_utc_now(), transitions=outcome.transitions, newItems=outcome.newItems, produced=outcome.produced,
            proposals=outcome.proposals, models=outcome.models, note=outcome.note, error=error,
            traceStepId=step.step_id,
        )
    ctx.store.insert(execution)
    return execution


def _load_run(store: CampaignStore, line_run_id: str) -> LineRun:
    run = store.get(LineRun, line_run_id)
    if run is None:
        raise PreconditionError(f"Line run {line_run_id} not found")
    return run


def _require_open(run: LineRun) -> None:
    if run.state in ("completed", "abandoned"):
        raise PreconditionError(f"{run.lineRunId} is {run.state}; choose a Line again to run another")


def _finish(store: CampaignStore, config_dir: Path, run: LineRun, state: str, now: datetime) -> LineRun:
    tracer = campaign_tracer(store, config_dir, run.launchId)
    review = draft_review(store, config_dir, run, now, tracer)
    finished = run.model_copy(update={"state": state, "reviewId": review.reviewId})
    store.save(finished)
    return finished


def step_line(store: CampaignStore, config_dir: Path, line_run_id: str, *, by: str, role: str, now: datetime,
              fetch: Fetch | None = None, model: Any = None, repertoire: Repertoire | None = None) -> StageResult:
    """Run the next stage. After the last stage the Line is completed and its Review opened."""
    run = _load_run(store, line_run_id)
    authorize(store, load_roles(config_dir), launch_id=run.launchId, actor=by, role=role, action="run_line",
              at=now.isoformat())
    _require_open(run)
    rep = repertoire or load_repertoire(config_dir)
    base = store.get(PositionSnapshot, f"pos_{run.launchId}_v{run.basePositionVersion}")
    if base is None:
        raise PreconditionError(f"base Position v{run.basePositionVersion} of {run.launchId} not found")
    index = run.nextStage
    stage = run.plannedStages[index]
    done = [e for e in store.list_for_launch(MoveExecution, run.launchId) if e.lineRunId == run.lineRunId]
    items = working_items(base.items, done)
    ids = ItemAllocator(items)
    tracer = campaign_tracer(store, config_dir, run.launchId)
    executions = []
    with tracer.step("campaign_manager", "stage_runner", "run_stage", right="run_stage") as st:
        st.set_inputs({"lineRunId": run.lineRunId, "lineId": run.lineId, "stage": index + 1, "moves": stage})
        for move_id in stage:
            ctx = build_move_context(store, config_dir, run.launchId, move_id, now, line_run_id=run.lineRunId,
                                     items=list(items), fetch=fetch, model=model, ids=ids, tracer=tracer,
                                     repertoire=rep)
            executions.append(run_move(ctx, stage_index=index))
        st.set_outputs({"executions": {e.moveId: e.status for e in executions}})
        st.set_decision(f"stage {index + 1} of {len(run.plannedStages)} ran", None)
    run = run.model_copy(update={"nextStage": index + 1, "state": "staged"})
    store.save(run)
    record_audit(store, launch_id=run.launchId, at=now.isoformat(), actor=by, role=role, action="run_line",
                 right="run_line", before=f"{run.lineRunId}:stage{index}", after=f"{run.lineRunId}:stage{index + 1}")
    review_id = None
    if run.nextStage >= len(run.plannedStages):
        review_id = _finish(store, config_dir, run, "completed", now).reviewId
    return StageResult(stageIndex=index, executions=executions, reviewId=review_id)


def run_line(store: CampaignStore, config_dir: Path, line_run_id: str, *, by: str, role: str, now: datetime,
             fetch: Fetch | None = None, model: Any = None) -> list[StageResult]:
    """Run every remaining stage, then open the Review."""
    rep = load_repertoire(config_dir)
    results: list[StageResult] = []
    while True:
        run = _load_run(store, line_run_id)
        if run.state in ("completed", "abandoned") and results:
            return results
        results.append(step_line(store, config_dir, line_run_id, by=by, role=role, now=now, fetch=fetch,
                                 model=model, repertoire=rep))


def _record_deviation(store: CampaignStore, config_dir: Path, run: LineRun, *, kind: str, move_id: str | None,
                      by: str, role: str, reason: str, now: datetime) -> Deviation:
    deviation = Deviation(
        deviationId=f"dev_{uuid.uuid4().hex[:12]}", lineRunId=run.lineRunId, launchId=run.launchId,
        beforeStage=run.nextStage, type=kind,  # type: ignore[arg-type]
        moveId=move_id, by=by, role=role, reason=reason, at=now.isoformat(),
    )
    tracer = campaign_tracer(store, config_dir, run.launchId)
    with tracer.step("campaign_manager", "stage_runner", "record_deviation", right="record_deviation") as step:
        step.set_inputs({"lineRunId": run.lineRunId, "type": kind, "moveId": move_id, "by": by, "reason": reason})
        store.insert(deviation)
        step.set_outputs({"deviationId": deviation.deviationId, "plannedStages": run.plannedStages})
        step.set_decision(kind, reason)
    record_audit(store, launch_id=run.launchId, at=now.isoformat(), actor=by, role=role,
                 action="deviate" if kind != "stopped" else "stop_line",
                 right="deviate" if kind != "stopped" else "stop_line",
                 before=run.lineRunId, after=deviation.deviationId, reason=reason)
    return deviation


def deviate(store: CampaignStore, config_dir: Path, line_run_id: str, *, by: str, role: str, reason: str,
            now: datetime, skip: str | None = None, add: str | None = None, stage: int | None = None) -> Deviation:
    """Skip a Move from a remaining stage, or add an approved Move (as the next stage, or into stage K)."""
    if (skip is None) == (add is None):
        raise UsageError("give exactly one of --skip or --add")
    run = _load_run(store, line_run_id)
    authorize(store, load_roles(config_dir), launch_id=run.launchId, actor=by, role=role, action="deviate",
              at=now.isoformat())
    _require_open(run)
    rep = load_repertoire(config_dir)
    stages = [list(s) for s in run.plannedStages]
    first = run.nextStage
    if stage is not None and not first < stage <= len(stages) + 1:
        raise UsageError(f"stage must be between {first + 1} and {len(stages) + 1} for {run.lineRunId}")
    if skip is not None:
        candidates = [stage - 1] if stage is not None else range(first, len(stages))
        target = next((i for i in candidates if i < len(stages) and skip in stages[i]), None)
        if target is None:
            raise PreconditionError(f"{skip} is not in a remaining stage of {run.lineRunId}")
        stages[target].remove(skip)
        stages = stages[:first] + [s for s in stages[first:] if s]
        kind, move_id = "skipped", skip
    else:
        assert add is not None
        move = rep.moves.get(add)
        if move is None:
            raise UsageError(f"unknown Move {add}; the catalogue has {', '.join(sorted(rep.moves))}")
        if "E3" in move.effectClasses:
            raise PreconditionError(f"{add} is an external-effect Move; it cannot be added by deviation in G0")
        if stage is None:
            stages.insert(first, [add])
        elif stage == len(stages) + 1:
            stages.append([add])
        else:
            stages[stage - 1].append(add)
        kind, move_id = "added", add
    run = run.model_copy(update={"plannedStages": stages})
    store.save(run)
    deviation = _record_deviation(store, config_dir, run, kind=kind, move_id=move_id, by=by, role=role,
                                  reason=reason, now=now)
    if run.nextStage >= len(run.plannedStages):
        _finish(store, config_dir, run, "abandoned", now)
    return deviation


def stop_line(store: CampaignStore, config_dir: Path, line_run_id: str, *, by: str, role: str, reason: str,
              now: datetime) -> LineRun:
    """Stop the Line early. It is abandoned, and the Review covers the evidence gathered so far."""
    run = _load_run(store, line_run_id)
    authorize(store, load_roles(config_dir), launch_id=run.launchId, actor=by, role=role, action="stop_line",
              at=now.isoformat())
    _require_open(run)
    _record_deviation(store, config_dir, run, kind="stopped", move_id=None, by=by, role=role, reason=reason, now=now)
    return _finish(store, config_dir, run, "abandoned", now)
