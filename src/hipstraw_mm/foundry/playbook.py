"""The playbook (Nov 6 meeting): predefined Lines and Moves, selected and ranked by rules. No model decides.

"We already have lines. We already have moves... we don't need LLM for that." For each demand validation task of
each hypothesis, the playbook lists the task's available Lines, checks each Line's conditions against the
hypothesis, ranks the eligible ones in playbook order, and picks the first. Jev may later help rank Lines within a
scenario; it stays deferred (constitution XI), so the playbook order ranks alone. Every pick carries the
conditions it rests on, so a reviewer sees the Lines that were available, why each was or was not eligible, and
which one was picked.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from hipstraw_mm.foundry.demand import SCOPE, DemandRubric, DemandTask, EvidenceItem
from hipstraw_mm.foundry.walkthrough import HypothesisPlan, Thesis, case_for, plan_line, run_walkthrough

NOT_LIVE = "Jev ranking is deferred (constitution XI): the playbook order ranks the eligible Lines"


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConditionCheck(_Config):
    text: str
    ok: bool


class LineOption(_Config):
    """One Line available for a task, as the playbook judged it."""
    lineId: str
    name: str
    purpose: str
    eligible: bool
    rank: int | None  # among the eligible Lines, in playbook order
    picked: bool
    checks: list[ConditionCheck]
    moves: list[str]


class MoveView(_Config):
    id: str
    name: str
    effect: str
    stage: int
    status: Literal["done", "next", "planned"]
    needsCharter: bool
    does: str
    records: list[str]
    passWhen: list[str]


class TaskPlay(_Config):
    taskId: str
    task: str
    question: str
    options: list[LineOption]
    lineId: str | None  # None: no Line is eligible
    lineName: str
    reason: str
    moves: list[MoveView]


class Metric(_Config):
    id: str
    label: str
    dimension: str
    current: int
    target: int | float
    state: str


class Finding(_Config):
    dimension: str
    ref: str
    title: str
    state: str
    text: str


class EvidenceView(_Config):
    id: str
    type: str
    rung: str
    demand: bool
    summary: str
    source: str
    independent: bool
    fromSegment: bool
    supports: list[str]
    contradicts: list[str]


class HypothesisPlay(_Config):
    id: str
    name: str
    demand: str
    segment: str
    offering: str
    buyerRole: str
    priority: int
    market: dict[str, str]
    decision: str
    decisionText: str
    checkpoint: str
    firstAction: str
    tasks: list[TaskPlay]
    metrics: list[Metric]
    findings: list[Finding]
    evidence: list[EvidenceView]


class Recommendation(_Config):
    thesis: str
    product: str
    market: str
    geography: str
    statement: str
    asOf: str
    rubricVersion: str
    repertoireVersion: str | None
    ranking: str = NOT_LIVE
    hypotheses: list[HypothesisPlay]
    scope: str = SCOPE

    def payload_hash(self) -> str:
        """What a reviewer approves: the Lines and Moves picked for every task. An approval is bound to this
        hash, so it cannot be carried over to a plan that has changed since."""
        picks = [[h.id, [[t.taskId, t.lineId, [m.id for m in t.moves]] for t in h.tasks]] for h in self.hypotheses]
        body = json.dumps({"thesis": self.thesis, "repertoire": self.repertoireVersion, "picks": picks},
                          sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


def recommend(thesis: Thesis, rubric: DemandRubric) -> Recommendation:
    walk = run_walkthrough(thesis, rubric)
    return Recommendation(
        thesis=thesis.thesis, product=thesis.product, market=thesis.market, geography=thesis.geography,
        statement=thesis.statement, asOf=thesis.asOf.isoformat(), rubricVersion=rubric.version,
        repertoireVersion=rubric.repertoireVersion,
        hypotheses=[_hypothesis(thesis, plan, rubric) for plan in walk.hypotheses],
    )


def _options(plan: HypothesisPlan, task: DemandTask, rubric: DemandRubric) -> list[LineOption]:
    considered = {c.id: c for c in plan.lines if c.phase == task.phase}
    out, rank = [], 0
    for line in rubric.task_lines(task):
        c = considered[line.id]
        rank += c.fits
        checks = [ConditionCheck(text=r, ok=r.endswith("as needed") or r == "fits every market")
                  for r in c.reasons if r != "an earlier Line in this phase was chosen"]
        out.append(LineOption(lineId=line.id, name=line.name, purpose=line.purpose, eligible=c.fits,
                              rank=rank if c.fits else None, picked=c.chosen, checks=checks,
                              moves=[m for stage in line.stages for m in stage]))
    return out


def _hypothesis(thesis: Thesis, plan: HypothesisPlan, rubric: DemandRubric) -> HypothesisPlay:
    h = next(x for x in thesis.hypotheses if x.id == plan.id)
    evidence = case_for(thesis, h, rubric).evidence
    tasks: list[TaskPlay] = []
    first = True
    for t in rubric.tasks:
        options = _options(plan, t, rubric)
        picked = next((o for o in options if o.picked), None)
        moves: list[MoveView] = []
        if picked:
            reason = (f"Playbook: {picked.lineId} {picked.name} is the first eligible Line for this task ("
                      + "; ".join(c.text for c in picked.checks) + ")")
            for stage in plan_line(thesis, h, picked.lineId, rubric, []).stages:
                for m in stage:
                    status: Literal["done", "next", "planned"] = "done" if m.done else "planned"
                    if status == "planned" and first:
                        status, first = "next", False
                    moves.append(MoveView(id=m.id, name=m.name, effect=m.effect, stage=m.stage, status=status,
                                          needsCharter=m.needsCharter, does=m.does,
                                          records=[k.label for k in m.records], passWhen=m.passWhen))
        else:
            reason = "Playbook: no Line is eligible. " + "; ".join(
                f"{o.lineId} {', '.join(c.text for c in o.checks if not c.ok)}" for o in options)
        tasks.append(TaskPlay(taskId=t.id, task=t.name, question=t.question, options=options,
                              lineId=picked.lineId if picked else None,
                              lineName=picked.name if picked else "No Line", reason=reason, moves=moves))
    nxt = next((m for t in tasks for m in t.moves if m.status == "next"), None)
    dimension = {q: g.name for g in rubric.demandDimensions for q in g.questions}
    order = {q: n for n, q in enumerate(q for g in rubric.demandDimensions for q in g.questions)}
    findings = [Finding(dimension=dimension.get(d.id, ""), ref=d.id, title=d.title, state=d.state, text=d.reason)
                for d in sorted(plan.assessment.dimensions, key=lambda d: order.get(d.id, 99))]
    findings += [Finding(dimension="Gate", ref=g.id, title=g.text, state=g.state,
                         text="A gate that is not confirmed blocks the decision")
                 for g in plan.assessment.gates if g.state in ("failed", "not_confirmed")]
    return HypothesisPlay(
        id=plan.id, name=plan.name, demand=plan.demand, segment=plan.segment, offering=plan.offering,
        buyerRole=plan.buyerRole, priority=plan.priority, market=plan.market,
        decision=plan.assessment.decision, decisionText=plan.assessment.decisionText, checkpoint=plan.checkpoint,
        firstAction=f"{nxt.id} {nxt.name}: {nxt.does}" if nxt else "None: no Move to run", tasks=tasks,
        metrics=[Metric(id=i.id, label=i.label, dimension=dimension.get(i.fills, ""), current=i.current,
                        target=i.target, state=i.state)
                 for i in sorted(plan.scorecard, key=lambda i: order.get(i.fills, 99))],
        findings=findings, evidence=[_evidence(i, rubric) for i in evidence],
    )


def _evidence(item: EvidenceItem, rubric: DemandRubric) -> EvidenceView:
    level = rubric.evidenceTypes[item.type]
    return EvidenceView(id=item.id, type=item.type, rung=level, demand=rubric.levels[level].demand,
                        summary=item.summary, source=item.source, independent=item.independent,
                        fromSegment=item.segment, supports=item.supports, contradicts=item.contradicts)
