"""Testing Moves: M09 drafts Test Plans, M10 would dispatch an approved test, M11 records Deltas.

G0 has no approval path, so a Test Plan stays a draft and M10 never sends, publishes or spends; the gate
refuses it before this handler is reached, and the handler refuses again in case it ever is.
"""

from __future__ import annotations

from hipstraw_mm.campaign.models import Delta, TestPlan, Transition
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome

NO_APPROVAL = "no approved Test Plan: G0 has no approval path for external effects"


@register("testing.draft_test_plan")
def draft_test_plan(ctx: MoveContext) -> MoveOutcome:
    """M09: a draft Test Plan per proposed hypothesis. A draft is not an approval."""
    out = MoveOutcome()
    for item in ctx.items:
        if item.kind != "hypothesis" or item.state != "proposed":
            continue
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


@register("testing.record_delta")
def record_delta(ctx: MoveContext) -> MoveOutcome:
    """M11: compare expected and observed for each running hypothesis. Observational only: the hypothesis
    is left inconclusive for the Review to judge, and a Delta is never causal proof."""
    out = MoveOutcome()
    observed = [e.evidenceId for e in ctx.evidence if e.kind == "metric"]
    running = [i for i in ctx.items if i.kind == "hypothesis" and i.state == "running"]
    if not running:
        out.note = "no running hypothesis to compare"
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
