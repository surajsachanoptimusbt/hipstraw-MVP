"""Demand validation walkthrough (Nov 5 meeting): from a market thesis to a demand validation program.

Market discovery ends with a thesis: who to serve, with what, where. This module takes that thesis and works out
how to validate demand for it, logging each step so the reasoning can be read back:
- the thesis read, and what demand validation must show: Hipstraw's six demand dimensions (problem, buyer,
  solution, payment, recurring, reachable), each judged by its own rubric questions;
- one demand question per hypothesis (segment and offering), the evidence so far placed on the ladder and judged;
- each hypothesis's market read (buyer, sales motion, recurring, how far the problem is shown);
- the Lines (strategies) that fit it, phase by phase, and those that do not, with each condition checked;
- the Moves (methods) of the chosen Lines: what each does for this market, how, what it needs, the evidence it
  records, the demand dimensions it tests and the indicator it must reach;
- for each demand dimension, its Lines, Moves, evidence and indicators;
- the scorecard of demand indicators, the checkpoint rule, the first action and the open decisions.
Every choice is a rule in config/foundry (no model call), so the same thesis always gives the same program.
"""

from __future__ import annotations

import string
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from hipstraw_mm.errors import UsageError
from hipstraw_mm.foundry.demand import (
    SCOPE,
    DemandAssessment,
    DemandCase,
    DemandRubric,
    EvidenceItem,
    Indicator,
    Offering,
    RubricLine,
    Segment,
    assess,
    case_profile,
    check_case,
    load_case,
    scorecard,
)

Buyer = Literal["b2b", "b2c"]
Motion = Literal["sales_led", "self_serve"]
PROBLEM = {"met": "confirmed", "partly": "partial", "unknown": "none", "not_met": "rejected",
           "not_applicable": "none"}
BUYER_ROLE = "the person who decides and pays"
STARTING_POINT = "any existing account list or market plan for the segment"


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- the thesis ---------------------------------------------------------------------------------------------------

class Hypothesis(_Config):
    """One demand to validate: a segment and an offering."""
    id: str
    name: str
    demand: str  # what the segment would do, in one sentence
    segment: Segment
    offering: Offering
    triggers: list[str] = []  # observable events that make a buyer need it now
    buyerRole: str = ""  # who decides and pays; defaults to the thesis's
    priority: int = 1
    buyer: Buyer | None = None  # defaults to the thesis's
    motion: Motion | None = None
    motionWhy: str = ""
    targets: dict[str, int | float] = {}
    targetsWhy: str = ""
    gates: dict[str, bool | None] = {}
    evidence: list[EvidenceItem] = []
    evidenceFrom: str | None = None  # a demand case file whose evidence, Moves run and gates this shares
    movesRun: list[str] = []


class Thesis(_Config):
    thesis: str
    product: str
    statement: str
    market: str
    geography: str = ""
    source: str = ""  # where the thesis came from
    startingPoint: str = ""  # an existing market plan or account list to start from
    asOf: date
    buyer: Buyer
    motion: Motion
    buyerRole: str = ""
    evidence: list[EvidenceItem] = []  # shared by every hypothesis
    movesRun: list[str] = []
    hypotheses: list[Hypothesis]
    openQuestions: list[str] = []


def case_for(thesis: Thesis, h: Hypothesis, rubric: DemandRubric) -> DemandCase:
    evidence, moves_run, gates = list(thesis.evidence), [*thesis.movesRun, *h.movesRun], dict(h.gates)
    if h.evidenceFrom:
        shared = load_case(Path(h.evidenceFrom), rubric)
        evidence += shared.evidence
        moves_run += shared.movesRun
        gates = {**shared.gates, **gates}
    return DemandCase(
        case=f"{thesis.thesis}-{h.id.lower()}", question=f"{h.name}: {h.demand}", asOf=thesis.asOf,
        offering=h.offering, segment=h.segment, gates=gates, evidence=evidence + h.evidence,
        movesRun=list(dict.fromkeys(moves_run)), targets=h.targets,
    )


def load_thesis(path: Path, rubric: DemandRubric) -> Thesis:
    try:
        with open(path, encoding="utf-8") as f:
            thesis = Thesis.model_validate(yaml.safe_load(f))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise UsageError(f"thesis {path}: {exc}") from exc
    errors = []
    ids = [h.id for h in thesis.hypotheses]
    errors += [f"duplicate hypothesis {x}" for x in sorted({x for x in ids if ids.count(x) > 1})]
    for h in thesis.hypotheses:
        errors += [f"{h.id}: {e}" for e in check_case(case_for(thesis, h, rubric), rubric)]
    if errors:
        raise UsageError(f"thesis {path}: " + "; ".join(errors))
    return thesis


# --- the walkthrough ----------------------------------------------------------------------------------------------

class LogLine(_Config):
    text: str
    depth: int = 0  # 0 is a heading in its step; deeper lines explain the line above
    tag: str = ""  # a short verdict: chosen, not chosen, done, next, needs charter, a rubric state...


class Step(_Config):
    n: int
    title: str
    summary: str  # what the agent did in this step, in one sentence
    lines: list[LogLine]


class EvidenceKind(_Config):
    type: str
    level: str
    rung: str
    demand: bool  # rungs 3 to 7 count as demand

    @property
    def label(self) -> str:
        return (f"{self.type.replace('_', ' ')} (rung {self.level[1:]}, "
                + ("counts as demand)" if self.demand else "not demand)"))


class LineChoice(_Config):
    id: str
    name: str
    phase: int
    fits: bool
    chosen: bool
    reasons: list[str]


class PlannedMove(_Config):
    id: str
    name: str
    effect: str
    line: str
    stage: int
    does: str
    how: list[str]
    needs: str
    records: list[EvidenceKind]
    output: str
    watchOut: str
    tests: list[str]  # rubric questions
    dimensions: list[str]  # the demand dimensions those questions belong to
    passWhen: list[str]  # the indicators it moves, now against their targets
    fills: list[str]
    needsCharter: bool
    done: bool
    status: Literal["done", "next", "planned"]


class PlannedLine(_Config):
    id: str
    name: str
    phase: int
    phaseName: str
    purpose: str
    why: list[str]  # the conditions that made it fit
    tests: list[str]  # demand dimensions its Moves test
    exit: str
    stages: list[list[PlannedMove]]


class QuestionNow(_Config):
    id: str
    title: str
    state: str
    reason: str


class DimensionPlan(_Config):
    """One demand dimension for one hypothesis: its rubric questions now, and the Lines, Moves, evidence and
    indicators that will test it."""
    id: str
    name: str
    question: str
    questions: list[QuestionNow]
    lines: list[str]
    moves: list[str]
    evidence: list[EvidenceKind]
    indicators: list[Indicator]


class HypothesisPlan(_Config):
    id: str
    name: str
    demand: str
    segment: str
    offering: str
    buyerRole: str
    priority: int
    market: dict[str, str]  # buyer, motion, recurring, problem
    marketWhy: dict[str, str]
    assessment: DemandAssessment
    lines: list[LineChoice]
    program: list[PlannedLine]
    dimensions: list[DimensionPlan]
    scorecard: list[Indicator]
    targets: dict[str, int | float]
    targetsWhy: str
    checkpoint: str
    firstAction: str

    def moves(self) -> list[PlannedMove]:
        return [m for pl in self.program for stage in pl.stages for m in stage]


class CatalogueLine(_Config):
    """A Line of the repertoire, and the hypotheses whose program it is in."""
    id: str
    name: str
    phase: int
    purpose: str
    useWhen: list[str]
    stages: list[list[str]]
    usedBy: list[str]


class CatalogueMove(_Config):
    id: str
    name: str
    effect: str
    dimensions: list[str]
    records: list[EvidenceKind]
    usedBy: list[str]


class Walkthrough(_Config):
    thesis: str
    product: str
    statement: str
    market: str
    geography: str
    source: str
    asOf: date
    rubricVersion: str
    repertoireVersion: str | None
    qualification: str
    steps: list[Step]
    hypotheses: list[HypothesisPlan]
    openDecisions: list[str]
    lines: list[CatalogueLine]
    moves: list[CatalogueMove]
    scope: str = SCOPE


class _Params(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _fill(text: str, params: _Params) -> str:
    return string.Formatter().vformat(text, (), params)


def _price(offering: Offering) -> str:
    f = offering.priceFloor
    return f"{f.amount:,.0f} {f.currency} per {f.per}" if f else "a quoted price (no price floor set yet)"


def _kind(evidence_type: str, rubric: DemandRubric) -> EvidenceKind:
    level = rubric.evidenceTypes[evidence_type]
    return EvidenceKind(type=evidence_type, level=level, rung=rubric.levels[level].name,
                        demand=rubric.levels[level].demand)


def _consider(line: RubricLine, market: dict[str, str]) -> tuple[bool, list[str]]:
    fits, reasons = True, []
    for attr, allowed in line.useWhen.items():
        ok = market[attr] in allowed
        fits &= ok
        reasons.append(f"{attr} is {market[attr]}" + (", as needed" if ok else f", needs {' or '.join(allowed)}"))
    for attr, banned in line.excludeWhen.items():
        if market[attr] in banned:
            fits = False
            reasons.append(f"excluded when {attr} is {market[attr]}")
    if not line.useWhen and not line.excludeWhen:
        reasons.append("fits every market")
    return fits, reasons


def _plan(thesis: Thesis, h: Hypothesis, rubric: DemandRubric) -> HypothesisPlan:
    case = case_for(thesis, h, rubric)
    a = assess(case, rubric)
    profile = case_profile(case, rubric)
    indicators = scorecard(case, rubric)
    de01 = next(d.state for d in a.dimensions if d.id == "DE01")
    market = {"buyer": h.buyer or thesis.buyer, "motion": h.motion or thesis.motion,
              "recurring": "true" if h.offering.recurring else "false", "problem": PROBLEM[de01]}
    why = {
        "buyer": "set for this hypothesis" if h.buyer else "the thesis's buyer",
        "motion": h.motionWhy or ("set for this hypothesis" if h.motion else "the thesis's sales motion"),
        "recurring": ("the offering is bought again and again" if h.offering.recurring
                      else "the offering is bought once"),
        "problem": f"rubric question DE01 is {de01.replace('_', ' ')} on the evidence so far",
    }
    params = _params(thesis, h, profile)
    buyer_role = params["buyerRole"]
    choices: list[LineChoice] = []
    program: list[PlannedLine] = []
    ended_by: str | None = None
    for phase in sorted({line.phase for line in rubric.lines}):
        chosen_here = False
        for line in (x for x in rubric.lines if x.phase == phase):
            if ended_by:
                choices.append(LineChoice(id=line.id, name=line.name, phase=phase, fits=False, chosen=False,
                                          reasons=[f"not reached: {ended_by} ends the program"]))
                continue
            fits, reasons = _consider(line, market)
            chosen = fits and not chosen_here
            if fits and chosen_here:
                reasons.append("an earlier Line in this phase was chosen")
            choices.append(LineChoice(id=line.id, name=line.name, phase=phase, fits=fits, chosen=chosen,
                                      reasons=reasons))
            if chosen:
                chosen_here = True
                program.append(_planned_line(line, reasons, rubric, params, case.movesRun, indicators))
                if line.endsProgram:
                    ended_by = line.id
    first = next((m for pl in program for stage in pl.stages for m in stage if not m.done), None)
    if first:
        first.status = "next"
    rule = next(r for r in rubric.decisions if r.id == a.decision)
    return HypothesisPlan(
        id=h.id, name=h.name, demand=h.demand, segment=h.segment.name, offering=h.offering.name,
        buyerRole=buyer_role, priority=h.priority, market=market, marketWhy=why, assessment=a, lines=choices,
        program=program, dimensions=_dimensions(a, program, indicators, rubric), scorecard=indicators,
        targets=profile, targetsWhy=h.targetsWhy, checkpoint=rule.checkpoint or rule.id,
        firstAction=f"{first.id} {first.name}: {first.does}" if first else "None: the program is complete",
    )


def _params(thesis: Thesis, h: Hypothesis, profile: dict[str, int | float]) -> _Params:
    return _Params({**profile, "segment": h.segment.name, "offering": h.offering.name, "price": _price(h.offering),
                    "triggers": ", ".join(h.triggers) or "a buying trigger",
                    "buyerRole": h.buyerRole or thesis.buyerRole or BUYER_ROLE,
                    "startingPoint": thesis.startingPoint or STARTING_POINT})


def plan_line(thesis: Thesis, h: Hypothesis, line_id: str, rubric: DemandRubric, why: list[str]) -> PlannedLine:
    """One Line's Moves filled in for a hypothesis, however the Line was chosen."""
    case = case_for(thesis, h, rubric)
    profile = case_profile(case, rubric)
    return _planned_line(rubric.line(line_id), why, rubric, _params(thesis, h, profile), case.movesRun,
                         scorecard(case, rubric))


def _planned_line(line: RubricLine, why: list[str], rubric: DemandRubric, params: _Params, done: list[str],
                  indicators: list[Indicator]) -> PlannedLine:
    by_id = {i.id: i for i in indicators}
    stages = []
    for n, stage in enumerate(line.stages, 1):
        moves = []
        for move_id in stage:
            m = rubric.move(move_id)
            tests = rubric.tested_by(m.id)
            dims = [g.name for g in rubric.demandDimensions if set(g.questions) & set(tests)]
            passes = [f"{by_id[x].label}: {by_id[x].current} of {by_id[x].target:g}" for x in m.fills
                      if by_id[x].state != "not_applicable"]
            moves.append(PlannedMove(
                id=m.id, name=m.name, effect=m.effect, line=line.id, stage=n, does=_fill(m.does, params),
                how=[_fill(x, params) for x in m.how], needs=_fill(m.needs, params),
                records=[_kind(t, rubric) for t in m.records], output=m.output, watchOut=m.watchOut, tests=tests,
                dimensions=dims, passWhen=passes, fills=m.fills, needsCharter=m.effect == "E3",
                done=m.id in done, status="done" if m.id in done else "planned"))
        stages.append(moves)
    tested = {q for stage in stages for m in stage for q in m.tests}
    dims = [g.name for g in rubric.demandDimensions if tested & set(g.questions)]
    return PlannedLine(id=line.id, name=line.name, phase=line.phase, phaseName=rubric.phases.get(line.phase, ""),
                       purpose=line.purpose, why=why, tests=dims, exit=line.exit, stages=stages)


def _dimensions(a: DemandAssessment, program: list[PlannedLine], indicators: list[Indicator],
                rubric: DemandRubric) -> list[DimensionPlan]:
    results = {d.id: d for d in a.dimensions}
    out = []
    for g in rubric.demandDimensions:
        qs = set(g.questions)
        lines, moves, kinds = [], [], {}
        for pl in program:
            for stage in pl.stages:
                for m in stage:
                    if qs & set(m.tests):
                        lines.append(f"{pl.id} {pl.name}")
                        moves.append(f"{m.id} {m.name}")
                        kinds.update({k.type: k for k in m.records})
        out.append(DimensionPlan(
            id=g.id, name=g.name, question=g.question,
            questions=[QuestionNow(id=q, title=results[q].title, state=results[q].state, reason=results[q].reason)
                       for q in g.questions],
            lines=list(dict.fromkeys(lines)), moves=list(dict.fromkeys(moves)),
            evidence=sorted(kinds.values(), key=lambda k: (k.level, k.type)),
            indicators=[i for i in indicators if i.fills in qs]))
    return out


def run_walkthrough(thesis: Thesis, rubric: DemandRubric) -> Walkthrough:
    plans = sorted((_plan(thesis, h, rubric) for h in thesis.hypotheses), key=lambda p: (p.priority, p.id))
    steps: list[Step] = []

    def step(title: str, summary: str, lines: list[LogLine]) -> None:
        steps.append(Step(n=len(steps) + 1, title=title, summary=summary, lines=lines))

    def say(text: str, depth: int = 0, tag: str = "") -> LogLine:
        return LogLine(text=text, depth=depth, tag=tag)

    def state(s: str) -> str:
        return s.replace("_", " ")

    by_id = {h.id: h for h in thesis.hypotheses}

    # 1. The thesis, taken as given.
    lines = [say(f"Product: {thesis.product}"), say(f"Thesis: {thesis.statement}"),
             say(f"Market: {thesis.market}" + (f", {thesis.geography}" if thesis.geography else "")),
             say(f"Buyer {thesis.buyer}, sold {thesis.motion.replace('_', '-')} unless a hypothesis says otherwise")]
    if thesis.source:
        lines.append(say(f"Source: {thesis.source}"))
    if thesis.startingPoint:
        lines.append(say(f"Starting point: {thesis.startingPoint}"))
    lines.append(say(f"{len(plans)} demand hypotheses"))
    lines += [say(f"{p.id} {p.name}: {p.demand}", 1) for p in plans]
    step("Read the market thesis",
         "Took the thesis as given: market discovery chose the market; this walkthrough validates demand for it",
         lines)

    # 2. What demand validation must show.
    lines = []
    for g in rubric.demandDimensions:
        lines.append(say(f"{g.name}: {g.question}"))
        lines += [say(f"{q} {rubric.dimension(q).title}", 1) for q in g.questions]
    lines += [say("Only actions count as demand: replies, sign-ups, interviews, commitments, payments, repeat "
                  "payments (rungs 3 to 7). Simulations, desk research and clicks do not"),
              say("No total: each dimension is judged on its own questions, a gate that is not confirmed blocks "
                  "the decision, and the rubric may say there is not enough evidence yet")]
    step("Set what demand validation must show",
         f"Laid out Hipstraw's {len(rubric.demandDimensions)} demand dimensions and the rubric questions that "
         f"judge each ({rubric.version}, {rubric.qualification})", lines)

    # 3. One question per hypothesis.
    lines = []
    for p in plans:
        h = by_id[p.id]
        lines.append(say(f"{p.id} {p.name}: does \"{p.segment}\" demand \"{p.offering}\"?",
                         tag=f"priority {p.priority}"))
        lines.append(say(f"Who decides and pays: {p.buyerRole}", 1))
        lines.append(say("Buying triggers: " + (", ".join(h.triggers) or "none named yet"), 1))
        lines.append(say(f"Thresholds: the {h.segment.profile.replace('_', ' ')} profile"
                         + (f", with its own targets ({p.targetsWhy})" if h.targets else ""), 1))
    step("Frame one demand question per hypothesis",
         "Turned each hypothesis into one question: does this segment demand this offering?", lines)

    # 4. The evidence so far.
    lines = []
    for item in thesis.evidence:
        k = _kind(item.type, rubric)
        lines.append(say(f"{item.id} {k.label}: {item.summary}", tag="demand" if k.demand else "not demand"))
        lines.append(say(f"Source: {item.source}" + ("" if item.independent else " (not independent)")
                         + (f". Bears on {', '.join(item.supports)}" if item.supports else "")
                         + (f". Against {', '.join(item.contradicts)}" if item.contradicts else ""), 1))
    for p in plans:
        h = by_id[p.id]
        own = h.evidence
        lines.append(say(f"{p.id}: {sum(r.items for r in p.assessment.ladder)} items in all, "
                         f"{sum(r.fromSegment for r in p.assessment.ladder if r.demand)} demand-level from the "
                         f"segment", tag=f"{sum(r.fromSegment for r in p.assessment.ladder if r.demand)} demand"))
        if h.evidenceFrom:
            lines.append(say(f"Shared from the case file {h.evidenceFrom}: "
                             + ", ".join(f"{r.items} on rung {r.level[1:]} ({r.name})"
                                         for r in p.assessment.ladder if r.items), 1))
        for item in own:
            k = _kind(item.type, rubric)
            lines.append(say(f"{item.id} {k.label}: {item.summary}", 1, "demand" if k.demand else "not demand"))
    step("Place the evidence so far on the ladder",
         "Placed every evidence item on the ladder by its type and checked its source and independence", lines)

    # 5. Judge each hypothesis by demand dimension.
    lines = []
    for p in plans:
        lines.append(say(f"{p.id} {p.name}: {p.assessment.decisionText}", tag=p.checkpoint))
        for d in p.dimensions:
            lines.append(say(f"{d.name}: " + ", ".join(f"{q.id} {state(q.state)}" for q in d.questions), 1))
            lines += [say(f"{q.id} {q.title}: {q.reason}", 2, state(q.state)) for q in d.questions]
    step("Judge each hypothesis on the six demand dimensions (DV07)",
         "Ran the demand evidence rubric on each hypothesis: every question met, partly, not met or unknown, "
         "then the gates and the decision", lines)

    # 6. The market each Line will be chosen for.
    step("Read each hypothesis's market",
         "Read the four facts the Lines' conditions test: buyer, sales motion, bought again, problem shown",
         [x for p in plans for x in [say(f"{p.id}: " + ", ".join(f"{k} {v}" for k, v in p.market.items()))]
          + [say(f"{k} {v}: {p.marketWhy[k]}", 1) for k, v in p.market.items()]])

    # 7. Lines.
    lines = []
    for p in plans:
        lines.append(say(f"{p.id}: " + " then ".join(f"{pl.id} {pl.name}" for pl in p.program),
                         tag=_count(len(p.program), "Line")))
        for c in p.lines:
            line = rubric.line(c.id)
            tag = "chosen" if c.chosen else ("fits, not chosen" if c.fits else "not chosen")
            lines.append(say(f"Phase {c.phase}. {c.id} {c.name}: {line.purpose}", 1, tag))
            lines += [say(r, 2) for r in c.reasons]
    step("Choose the Lines (strategies), phase by phase",
         "Tested every Line's conditions against each market and took, in each phase, the first that fits", lines)

    # 8. Moves.
    lines = []
    for p in plans:
        moves = p.moves()
        charter = sum(m.needsCharter and not m.done for m in moves)
        lines.append(say(f"{p.id}: {_count(len(moves), 'Move')} in {_count(len(p.program), 'Line')}; {charter} "
                         f"need an approved charter; {sum(m.done for m in moves)} already done",
                         tag=_count(len(moves), "Move")))
        for pl in p.program:
            lines.append(say(f"{pl.id} {pl.name} (phase {pl.phase}, {pl.phaseName}): {pl.purpose}", 1))
            for m in (m for stage in pl.stages for m in stage):
                tag = {"done": "done", "next": "next"}.get(m.status, "needs charter" if m.needsCharter else
                                                           "internal" if m.effect == "E0" else "reads sources")
                lines.append(say(f"Stage {m.stage}. {m.id} {m.name}: {m.does}", 2, tag))
                if m.dimensions:
                    lines.append(say(f"Tests {', '.join(m.dimensions)} ({', '.join(m.tests)})", 3))
                if m.records:
                    lines.append(say("Records " + "; ".join(k.label for k in m.records), 3))
                lines += [say(f"Pass when {x}", 3) for x in m.passWhen]
                if m.needs:
                    lines.append(say(f"Needs {m.needs[0].lower()}{m.needs[1:]}", 3))
    step("Pick the Moves (methods) of each chosen Line",
         "Laid out each chosen Line's Moves stage by stage, filled in for this market, with what each tests, "
         "records and must reach", lines)

    # 9. Dimension by dimension.
    lines = []
    for p in plans:
        lines.append(say(f"{p.id} {p.name}"))
        for d in p.dimensions:
            if all(q.state == "not_applicable" for q in d.questions):
                lines.append(say(f"{d.name}: not tested, the offering is bought once", 1, "not applicable"))
                continue
            lines.append(say(f"{d.name}: Lines " + (", ".join(d.lines) or "none"), 1,
                             _count(len(d.moves), "Move")))
            lines.append(say("Moves " + (", ".join(d.moves) or "none in this program"), 2))
            if d.evidence:
                lines.append(say("Evidence " + "; ".join(k.label for k in d.evidence), 2))
            lines += [say(f"Indicator {i.label}: {i.current} of {i.target:g}", 2) for i in d.indicators
                      if i.state != "not_applicable"]
    step("Map each demand dimension to its Lines, Moves and evidence",
         "For each demand dimension, collected the Lines and Moves that test it, the evidence they record and "
         "the indicators it is read by", lines)

    # 10. Scorecard.
    lines = []
    for p in plans:
        lines.append(say(f"{p.id} {p.name}" + (f". Own targets: {p.targetsWhy}" if p.targetsWhy else "")))
        for d in p.dimensions:
            shown = [i for i in d.indicators if i.state != "not_applicable"]
            if shown:
                lines.append(say(f"{d.name}: " + ", ".join(f"{i.label} {i.current} of {i.target:g}"
                                                             for i in shown), 1))
    lines.append(say("Indicators sit side by side and are never added up; the rubric's rules make the decision"))
    step("Set the demand scorecard",
         "Set each demand indicator against its target, grouped by demand dimension", lines)

    # 11. Checkpoint.
    step("Set the checkpoint rule", "Fixed, before any result, what each rubric decision leads to",
         [say("After each assessment: validated, continue to scale; promising or problem confirmed, continue; not "
              "validated, revise the segment or offer; disproved, stop or reframe; a gate not confirmed, fix it "
              "first")]
         + [say(f"{p.id} now: {state(p.assessment.decision)}", tag=p.checkpoint) for p in plans])

    # 12. First action.
    step("Order the hypotheses and name the first action",
         "Ordered the hypotheses by priority and took the first Move not yet done in each program",
         [say(f"{n}. {p.id} {p.name} (priority {p.priority}): {p.firstAction}", tag="first action" if n == 1 else "")
          for n, p in enumerate(plans, 1)])

    # 13. Open decisions.
    decisions = list(thesis.openQuestions)
    decisions += [f"{p.id}: set a price floor for \"{p.offering}\"; until then rubric question DE07 cannot be met"
                  for p in plans if by_id[p.id].offering.priceFloor is None]
    decisions.append("Who signs the charter for the Moves that contact people, publish or spend")
    if rubric.qualification == "candidate":
        decisions.append(f"Rubric {rubric.version} is a candidate: confirm its thresholds before it decides alone")
    step("List what needs a decision", "Listed what a person must decide before the Moves that need it run",
         [say(d) for d in decisions])
    return Walkthrough(
        thesis=thesis.thesis, product=thesis.product, statement=thesis.statement, market=thesis.market,
        geography=thesis.geography, source=thesis.source, asOf=thesis.asOf, rubricVersion=rubric.version,
        repertoireVersion=rubric.repertoireVersion, qualification=rubric.qualification, steps=steps,
        hypotheses=plans, openDecisions=decisions, lines=_catalogue_lines(plans, rubric),
        moves=_catalogue_moves(plans, rubric),
    )


def _catalogue_lines(plans: list[HypothesisPlan], rubric: DemandRubric) -> list[CatalogueLine]:
    out = []
    for line in rubric.lines:
        when = [f"{k} is {' or '.join(v)}" for k, v in line.useWhen.items()]
        when += [f"not when {k} is {' or '.join(v)}" for k, v in line.excludeWhen.items()]
        out.append(CatalogueLine(id=line.id, name=line.name, phase=line.phase, purpose=line.purpose,
                                 useWhen=when or ["any market"], stages=line.stages,
                                 usedBy=[p.id for p in plans if any(pl.id == line.id for pl in p.program)]))
    return out


def _catalogue_moves(plans: list[HypothesisPlan], rubric: DemandRubric) -> list[CatalogueMove]:
    out = []
    for m in rubric.moves:
        tests = set(rubric.tested_by(m.id))
        out.append(CatalogueMove(
            id=m.id, name=m.name, effect=m.effect,
            dimensions=[g.name for g in rubric.demandDimensions if tests & set(g.questions)],
            records=[_kind(t, rubric) for t in m.records],
            usedBy=[p.id for p in plans if any(x.id == m.id for x in p.moves())]))
    return out
