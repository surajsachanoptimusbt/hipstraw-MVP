"""Testing Moves: M09 drafts Test Plans, M10 would dispatch an approved test, M11 records Deltas.

G0 has no approval path, so a Test Plan stays a draft and M10 never sends, publishes or spends; the gate
refuses it before this handler is reached, and the handler refuses again in case it ever is. A live direction
(M14) is different: the Sponsor applies it on their own platform and records it (live.record_change), and M11
compares its measure over the days before with the days since.
"""

from __future__ import annotations

from datetime import timedelta

from hipstraw_mm.campaign.models import ChangeRecord, Delta, Direction, TestPlan, Transition
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome
from hipstraw_mm.campaign.performance import (
    cost_floor,
    daily_metrics,
    fmt,
    load_performance_rules,
    measure_between,
    metric_evidence_ids,
    value_between,
)

NO_APPROVAL = "no approved Test Plan: G0 has no approval path for external effects"


@register("testing.draft_test_plan")
def draft_test_plan(ctx: MoveContext) -> MoveOutcome:
    """M09: a draft Test Plan per proposed hypothesis. A draft is not an approval."""
    out = MoveOutcome()
    directions = {d.hypothesisItemId: d for d in ctx.store.list_for_launch(Direction, ctx.launch_id)}
    rules = load_performance_rules(ctx.config_dir) if directions else None
    for item in ctx.items:
        if item.kind != "hypothesis" or item.state != "proposed":
            continue
        direction = directions.get(item.itemId)
        if direction is not None and rules is not None:
            d = rules.measure(direction.channel, direction.measure)
            label = d.label.lower() if d else direction.measure
            share = int(rules.supportedChange * 100)
            plan = TestPlan(
                testPlanId=ctx.record_id("tp"), launchId=ctx.launch_id, lineRunId=ctx.line_run_id,
                hypothesisItemId=item.itemId, hypothesis=item.text,
                cohort=f"the live {direction.channel or 'campaign'} audience, as targeted",
                method=f"before and after: {label} over the {rules.window} days before the Sponsor applies the "
                       "change, against the days since (the Sponsor applies it; Hipstraw measures)",
                successCriteria=f"{label} {'rises' if direction.expected == 'increase' else 'falls'} by at least "
                                f"{share}% from {fmt(d, direction.baseline)}",
                stopRule=f"revert if {label} moves the wrong way for {rules.window} days",
                risks=["other changes in the same days are not controlled; the result is observational"],
            )
        else:
            plan = TestPlan(
                testPlanId=ctx.record_id("tp"), launchId=ctx.launch_id, lineRunId=ctx.line_run_id,
                hypothesisItemId=item.itemId, hypothesis=item.text, cohort="to be set by the Campaign Manager",
                method="compare against the current version", successCriteria="to be agreed with the Sponsor",
                stopRule="stop at 7 days or at the first adverse signal",
                risks=["needs Sponsor approval and an authorized channel before it can run"],
            )
        ctx.store.insert(plan)
        out.produced.append(plan.testPlanId)
        out.transitions.append(Transition(itemId=item.itemId, fromState="proposed", toState="planned"))
    out.note = f"{len(out.produced)} draft Test Plans" if out.produced else "no proposed hypotheses to plan"
    return out


@register("testing.dispatch_blocked")
def dispatch_blocked(ctx: MoveContext) -> MoveOutcome:
    """M10: never dispatches in G0."""
    return MoveOutcome(status="blocked", note=NO_APPROVAL)


def _live_deltas(ctx: MoveContext, out: MoveOutcome) -> set[str]:
    """Directions the Sponsor applied: `running` while the days since are too few, then a Delta with the
    measure before and after. Observational: changes applied in the same days are named, never ruled out."""
    changes = {c.hypothesisItemId: c for c in ctx.store.list_for_launch(ChangeRecord, ctx.launch_id)}
    directions = {d.hypothesisItemId: d for d in ctx.store.list_for_launch(Direction, ctx.launch_id)}
    handled: set[str] = set()
    if not changes:
        return handled
    rules = load_performance_rules(ctx.config_dir)
    series = daily_metrics(ctx.evidence)
    today = ctx.now.date()
    for item in ctx.items:
        change, direction = changes.get(item.itemId), directions.get(item.itemId)
        if item.kind != "hypothesis" or change is None or direction is None:
            continue
        if item.state not in ("proposed", "planned", "running"):
            continue
        handled.add(item.itemId)
        if (today - change.appliedOn).days < rules.deltaMinDays:
            if item.state != "running":
                out.transitions.append(Transition(itemId=item.itemId, fromState=item.state, toState="running"))
            continue
        before_start = change.appliedOn - timedelta(days=rules.window)
        before_end = change.appliedOn - timedelta(days=1)
        d = rules.measure(direction.channel, direction.measure)
        before_value = value_between(rules, direction.channel, direction.measure, series, before_start, before_end)
        before = before_value.value
        floor_note = ""
        if before is None and (floor := cost_floor(d, before_value)) is not None:
            before = floor
            floor_note = (f"before the change {fmt(d, floor)} was spent with no result, counted as {fmt(d, floor)} "
                          "each (a lower bound); ")
        after = measure_between(rules, direction.channel, direction.measure, series, change.appliedOn, today)
        result = "inconclusive"
        if before is not None and after is not None:
            moved = (after - before) / before if before else (1.0 if after > 0 else 0.0)
            gain = moved if direction.expected == "increase" else -moved
            result = "supported" if gain >= rules.supportedChange else "not_supported" if gain <= 0 else "inconclusive"
        others = [c for c in changes.values() if c.changeId != change.changeId
                  and abs((c.appliedOn - change.appliedOn).days) <= rules.window]
        named = [f"{c.hypothesisItemId} on {c.appliedOn.isoformat()} ({c.what.split(';')[0].split(',')[0][:70]})"
                 for c in others]
        delta = Delta(
            deltaId=ctx.record_id("dlt"), launchId=ctx.launch_id, hypothesisItemId=item.itemId,
            expected=f"{d.label if d else direction.measure} to {direction.expected} after: {change.what}",
            observedEvidenceRefs=metric_evidence_ids(ctx.evidence, direction.channel, before_start, today),
            attributionNotes=f"observational before and after; {floor_note}" + (
                "also changed in the same days: " + "; ".join(named) if others
                else "no other recorded change in the same days, but the market is not controlled"),
            createdAt=ctx.now.isoformat(), channel=direction.channel, measure=direction.measure, before=before,
            after=after, windowBefore=f"{before_start.isoformat()} to {before_end.isoformat()}",
            windowAfter=f"{change.appliedOn.isoformat()} to {today.isoformat()}", result=result,  # type: ignore[arg-type]
        )
        ctx.store.insert(delta)
        out.produced.append(delta.deltaId)
        out.transitions.append(Transition(itemId=item.itemId, fromState=item.state, toState=result,
                                          evidenceRefs=delta.observedEvidenceRefs))
    return handled


@register("testing.record_delta")
def record_delta(ctx: MoveContext) -> MoveOutcome:
    """M11: compare expected and observed. A live direction the Sponsor applied gets its measure before and
    after; any other running hypothesis is left inconclusive for the Review to judge. A Delta is never causal
    proof."""
    out = MoveOutcome()
    handled = _live_deltas(ctx, out)
    observed = [e.evidenceId for e in ctx.evidence if e.kind == "metric"]
    running = [i for i in ctx.items if i.kind == "hypothesis" and i.state == "running" and i.itemId not in handled]
    if handled:
        out.note = (f"{len(out.produced)} Deltas" if out.produced else "applied changes still measuring") + (
            f"; {len(running)} other running hypotheses" if running else "")
    if not running:
        out.note = out.note or "no running hypothesis to compare"
        return out
    if not observed:
        out.note = "no metric evidence to compare against"
        return out
    for item in running:
        delta = Delta(
            deltaId=ctx.record_id("dlt"), launchId=ctx.launch_id, hypothesisItemId=item.itemId,
            expected=item.text, observedEvidenceRefs=observed,
            attributionNotes="observational comparison; other changes in the same window are not controlled",
            createdAt=ctx.now.isoformat(),
        )
        ctx.store.insert(delta)
        out.produced.append(delta.deltaId)
        out.transitions.append(Transition(itemId=item.itemId, fromState="running", toState="inconclusive",
                                          evidenceRefs=observed))
    out.note = f"{len(out.produced)} Deltas"
    return out
