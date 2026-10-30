"""Line recommendation and choice (US2, FR-020 to FR-023).

The system lists which Lines fit and why, from typed facts; a person chooses. A model never picks a Line
(compiler spec, option E). The choice opens the launch tactic record (C10) with the recommendation as it
stood, so later comparisons can see what was on offer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from hipstraw_mm.campaign import moves
from hipstraw_mm.campaign.audit import record_audit
from hipstraw_mm.campaign.conditions import Facts, compute_facts, describe, evaluate
from hipstraw_mm.campaign.config import load_roles
from hipstraw_mm.campaign.gate import authorize
from hipstraw_mm.campaign.models import LineChoice, LineRecommendation, LineRun, TestPlan
from hipstraw_mm.campaign.repertoire import LineDef, Repertoire, load_repertoire
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.errors import PreconditionError, UsageError


def _assess(line: LineDef, facts: Facts) -> tuple[bool, list[str]]:
    if line.excludeWhen is not None:
        results = [describe(c, facts) for c in line.excludeWhen.checks]
        hits = [text for ok, text in results if ok]
        excluded = bool(hits) if line.excludeWhen.any is not None else len(hits) == len(results)
        if excluded:
            return False, [text.replace("(needs ", "(excluded when ") for text in hits]
    fits, _ = evaluate(line.useWhen, facts)
    results = [describe(c, facts) for c in line.useWhen.checks]
    if fits:
        return True, [text for ok, text in results if ok]
    return False, [text[:-1] + ", not met)" for ok, text in results if not ok]


def recommend_lines(repertoire: Repertoire, facts: Facts, position_version: int) -> LineRecommendation:
    eligible: list[LineChoice] = []
    excluded: list[LineChoice] = []
    for line in repertoire.lines.values():
        fits, reasons = _assess(line, facts)
        assert line.version is not None
        (eligible if fits else excluded).append(LineChoice(lineId=line.id, version=line.version, reasons=reasons))
    return LineRecommendation(positionVersion=position_version, facts=dict(facts), eligible=eligible,
                              excluded=excluded)


def recommend_for_launch(store: CampaignStore, config_dir: Path, launch_id: str, now: datetime,
                         repertoire: Repertoire | None = None) -> LineRecommendation:
    """The recommendation for the head Position, traced (`campaign lines`, and before every choice)."""
    rep = repertoire or load_repertoire(config_dir)
    mandate, position = store.latest_mandate(launch_id), store.head_position(launch_id)
    if mandate is None or position is None:
        raise PreconditionError(f"launch {launch_id} not found")
    facts = compute_facts(mandate, position, now.date(), store.list_for_launch(TestPlan, launch_id))
    rec = recommend_lines(rep, facts, position.version)
    tracer = campaign_tracer(store, config_dir, launch_id)
    with tracer.step("campaign_manager", "line_selector", "recommend_lines", right="recommend_lines") as step:
        step.set_inputs({"positionVersion": rec.positionVersion, "repertoireVersion": rep.version,
                         "facts": rec.facts})
        step.set_outputs({"eligible": [c.lineId for c in rec.eligible], "excluded": [c.lineId for c in rec.excluded]})
        for choice in rec.excluded:
            step.add_alternative(choice.lineId, "; ".join(choice.reasons))
        step.set_decision(", ".join(c.lineId for c in rec.eligible) or "no Line fits",
                          "typed use-when and exclude-when checks; a person chooses")
    return rec


def choose_line(store: CampaignStore, config_dir: Path, launch_id: str, line_id: str, *, by: str, role: str,
                reason: str, now: datetime, repertoire: Repertoire | None = None) -> LineRun:
    at = now.isoformat()
    authorize(store, load_roles(config_dir), launch_id=launch_id, actor=by, role=role, action="choose_line", at=at)
    rep = repertoire or load_repertoire(config_dir)
    line = rep.lines.get(line_id)
    if line is None:
        raise UsageError(f"unknown Line {line_id}; the repertoire has {', '.join(sorted(rep.lines))}")
    rec = recommend_for_launch(store, config_dir, launch_id, now, rep)
    excluded = {c.lineId: c for c in rec.excluded}
    if line_id in excluded:
        raise PreconditionError(f"{line_id} is excluded for this launch: {'; '.join(excluded[line_id].reasons)}")
    withdrawn = [m for stage in line.stages for m in stage if rep.moves[m].handler not in moves.HANDLERS]
    if withdrawn:
        raise PreconditionError(
            f"{line_id} uses {', '.join(withdrawn)} whose handler is withdrawn; choose another Line or run "
            "Moves individually"
        )

    assert line.version is not None
    run = LineRun(
        lineRunId=f"lrun_{launch_id}_{len(store.list_for_launch(LineRun, launch_id)) + 1}", launchId=launch_id,
        lineId=line_id, lineVersion=line.version, repertoireVersion=rep.version, chosenBy=by, chosenRole=role,
        reason=reason, chosenAt=at, recommendation=rec, basePositionVersion=rec.positionVersion,
        plannedStages=[list(stage) for stage in line.stages],
    )
    tracer = campaign_tracer(store, config_dir, launch_id)
    with tracer.step("campaign_manager", "line_selector", "choose_line", right="choose_line") as step:
        step.set_inputs({"lineId": line_id, "by": by, "role": role, "reason": reason})
        store.insert(run)
        step.set_outputs({"lineRunId": run.lineRunId, "lineVersion": run.lineVersion,
                          "plannedStages": run.plannedStages})
        step.set_decision(line_id, reason)
    record_audit(store, launch_id=launch_id, at=at, actor=by, role=role, action="choose_line", right="choose_line",
                 before=f"pos_{launch_id}_v{rec.positionVersion}", after=run.lineRunId, reason=reason)
    return run
