"""Demand evidence (Blueprint v0.1 section 07, rubric family "Demand evidence"; Nov 4 meeting: validate that a
specific market demands a specific product from several kinds of evidence, never one score).

A case file lists the evidence gathered for one question ("do US small businesses need a shadow launch
platform?"). Each item's type fixes its rung on the evidence ladder (config/foundry/demand_evidence.yaml), and
the item says whether it came from the target segment, whether it is independent and which dimensions it
supports or contradicts. The rubric turns counts of that evidence into a judgement per dimension, the gates into
confirmed or not, and the first decision rule that holds into the decision. Nothing calls a model, so the same
case and rubric always give the same assessment. There is no total, and the rubric may abstain.
"""

from __future__ import annotations

import string
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hipstraw_mm.campaign.models import MechanismStamp, content_hash
from hipstraw_mm.campaign.stamp import mechanism_stamp
from hipstraw_mm.errors import ConfigError, UsageError

State = Literal["met", "partly", "not_met", "unknown", "not_applicable"]
GateState = Literal["confirmed", "failed", "not_confirmed", "not_applicable"]
Qualification = Literal["candidate", "lab-tested", "shadow-tested", "field-qualified", "monitored", "retired"]

# The ladder is the Blueprint's (section 02); its rungs are fixed, their names and notes live in the config.
LADDER = ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7")
STATED = ("L3", "L4")  # a price someone states
COMMITTED = ("L5", "L6", "L7")  # a price someone commits to or pays

SCOPE = ("This assessment says what the recorded evidence shows about demand from one segment for one offering, "
         "judged against a versioned rubric. It is not a forecast of sales or of market size.")


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- the rubric ---------------------------------------------------------------------------------------------------

class Rung(_Config):
    name: str
    demand: bool
    note: str


class Condition(_Config):
    count: Literal["support", "contra", "total", "any"]
    levels: list[str]
    segment: bool = False
    atLeast: int | str | None = None  # a number or a profile key
    atMost: int | str | None = None


class Dimension(_Config):
    id: str
    title: str
    question: str
    met: str
    partly: str
    notMet: str
    whenMet: list[Condition] = []
    whenPartly: list[Condition] = []
    whenNotMet: list[Condition] = []
    check: Literal["price", "independence"] | None = None
    appliesWhen: Literal["recurring"] | None = None  # judged only for an offering bought again and again
    gatheredBy: list[str]


class Gate(_Config):
    id: str
    text: str
    field: str
    appliesFrom: str


class DecisionRule(_Config):
    id: str
    text: str
    checkpoint: str = ""  # continue, revise or stop, in a few words
    gateFailed: bool = False
    anyNotMet: list[str] = []
    allMet: list[str] = []
    atLeastPartly: list[str] = []
    allUnknown: list[str] = []
    demandBelowMinimum: bool = False
    noneNotMet: bool = False
    next: list[str] | None = None


class DemandDimension(_Config):
    """One of Hipstraw's six demand dimensions (Nov 5 meeting), judged by its own rubric questions."""
    id: str
    name: str
    question: str
    questions: list[str]


class RubricMove(_Config):
    """A method that gathers or judges evidence (config/foundry/demand_repertoire.yaml)."""
    id: str
    name: str
    effect: Literal["E0", "E1", "E2", "E3"]
    does: str = ""  # may name {segment}, {offering}, {triggers}, {price}, {buyerRole}, {startingPoint}, profile keys
    how: list[str] = []
    needs: str = ""
    records: list[str] = []  # evidence types
    output: str = ""
    watchOut: str = ""
    fills: list[str] = []  # scorecard indicators it moves


# What a Line's useWhen and excludeWhen may test, and the values each can take.
LINE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "buyer": ("b2b", "b2c"),
    "motion": ("sales_led", "self_serve"),
    "recurring": ("true", "false"),
    "problem": ("none", "partial", "confirmed", "rejected"),
}


class RubricLine(_Config):
    """A strategy: ordered stages of Moves, with the conditions that make it fit a market (Faculty grammar)."""
    id: str
    name: str
    phase: int = 1
    purpose: str = ""
    useWhen: dict[str, list[str]] = {}
    excludeWhen: dict[str, list[str]] = {}
    endsProgram: bool = False
    stages: list[list[str]]
    exit: str = ""  # when it is done and what follows
    note: str | None = None


class DemandTask(_Config):
    """A demand validation task: one Line is decided for it, from the Lines of its phase, or none."""
    id: str
    phase: int
    name: str
    question: str


class ScorecardItem(_Config):
    """One demand indicator: a count from the case's evidence against a profile target. Never summed."""
    id: str
    label: str
    target: str  # a profile key
    fills: str  # the dimension it informs
    by: list[str]  # the Moves that gather it
    types: list[str] = []  # count these evidence types...
    levels: list[str] = []  # ...or these rungs
    dimension: str | None = None  # only items tagged as supporting this dimension
    segment: bool = True
    distinct: Literal["channel", "source"] | None = None
    appliesWhen: Literal["recurring"] | None = None


class DemandRubric(_Config):
    version: str
    qualification: Qualification
    status: str | None = None
    levels: dict[str, Rung]
    evidenceTypes: dict[str, str]
    profiles: dict[str, dict[str, int | float]]
    demandDimensions: list[DemandDimension] = []
    dimensions: list[Dimension]
    gates: list[Gate]
    decisions: list[DecisionRule]
    scorecard: list[ScorecardItem] = []
    repertoireVersion: str | None = None
    phases: dict[int, str] = {}
    tasks: list[DemandTask] = []
    moves: list[RubricMove]
    lines: list[RubricLine]

    @model_validator(mode="after")
    def _lint(self) -> DemandRubric:
        errors = lint_rubric(self)
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def dimension(self, dimension_id: str) -> Dimension:
        return next(d for d in self.dimensions if d.id == dimension_id)

    def move(self, move_id: str) -> RubricMove:
        return next(m for m in self.moves if m.id == move_id)

    def line(self, line_id: str) -> RubricLine:
        return next(line for line in self.lines if line.id == line_id)

    def task_lines(self, task: DemandTask) -> list[RubricLine]:
        return [line for line in self.lines if line.phase == task.phase]

    def tested_by(self, move_id: str) -> list[str]:
        """The rubric questions a Move gathers evidence for."""
        return [d.id for d in self.dimensions if move_id in d.gatheredBy]

    def demand_dimension(self, question_id: str) -> DemandDimension | None:
        return next((g for g in self.demandDimensions if question_id in g.questions), None)


def lint_rubric(rubric: DemandRubric) -> list[str]:
    """Every reference in the rubric resolves: rungs, profile keys, dimensions, Moves. Empty when it is sound."""
    errors: list[str] = []
    if sorted(rubric.levels) != list(LADDER):
        errors.append(f"levels must be exactly {', '.join(LADDER)}")
    errors += [f"evidence type {t!r}: unknown level {lv!r}" for t, lv in rubric.evidenceTypes.items()
               if lv not in LADDER]
    keys = [set(p) for p in rubric.profiles.values()]
    common = set.intersection(*keys) if keys else set()
    if any(k != common for k in keys):
        errors.append("every profile must set the same keys")
    dims = {d.id for d in rubric.dimensions}
    moves = {m.id for m in rubric.moves}
    for d in rubric.dimensions:
        for cond in d.whenMet + d.whenPartly + d.whenNotMet:
            errors += [f"{d.id}: unknown level {lv!r}" for lv in cond.levels if lv not in LADDER]
            errors += [f"{d.id}: unknown profile key {t!r}" for t in (cond.atLeast, cond.atMost)
                       if isinstance(t, str) and t not in common]
        if d.check is None and not d.whenMet:
            errors.append(f"{d.id}: needs whenMet conditions or a check")
        for text in (d.met, d.partly, d.notMet):
            errors += [f"{d.id}: unknown profile key {k!r} in its anchor text"
                       for _, k, _, _ in string.Formatter().parse(text) if k and k not in common]
        errors += [f"{d.id}: unknown Move {m!r}" for m in d.gatheredBy if m not in moves]
    errors += [f"gate {g.id}: unknown level {g.appliesFrom!r}" for g in rubric.gates if g.appliesFrom not in LADDER]
    for rule in rubric.decisions:
        named = rule.anyNotMet + rule.allMet + rule.atLeastPartly + rule.allUnknown
        errors += [f"decision {rule.id}: unknown dimension {x!r}" for x in named if x not in dims]
        errors += [f"decision {rule.id}: unknown Move {m!r}" for m in rule.next or [] if m not in moves]
    if not rubric.decisions or _conditions(rubric.decisions[-1]):
        errors.append("the last decision must have no conditions, so every case gets one")
    for m in rubric.moves:
        errors += [f"{m.id}: unknown evidence type {t!r}" for t in m.records if t not in rubric.evidenceTypes]
    grouped = [q for g in rubric.demandDimensions for q in g.questions]
    errors += [f"demand dimension: unknown rubric question {q!r}" for q in grouped if q not in dims]
    if rubric.demandDimensions:
        errors += [f"{q}: in more than one demand dimension" for q in sorted({q for q in grouped
                                                                            if grouped.count(q) > 1})]
        errors += [f"{d}: in no demand dimension" for d in sorted(dims - set(grouped))]
    for line in rubric.lines:
        errors += [f"{line.id}: unknown Move {m!r}" for stage in line.stages for m in stage if m not in moves]
        if rubric.phases and line.phase not in rubric.phases:
            errors.append(f"{line.id}: unknown phase {line.phase}")
        for attr, values in {**line.useWhen, **line.excludeWhen}.items():
            if attr not in LINE_ATTRIBUTES:
                errors.append(f"{line.id}: unknown condition {attr!r} (known: {', '.join(LINE_ATTRIBUTES)})")
            else:
                errors += [f"{line.id}: {attr} cannot be {v!r}" for v in values if v not in LINE_ATTRIBUTES[attr]]
    errors += [f"task {t.id}: unknown phase {t.phase}" for t in rubric.tasks
               if rubric.phases and t.phase not in rubric.phases]
    if rubric.tasks:
        tasked = {t.phase for t in rubric.tasks}
        errors += [f"{line.id}: no task for phase {line.phase}" for line in rubric.lines if line.phase not in tasked]
    indicators = {i.id for i in rubric.scorecard}
    for m in rubric.moves:
        errors += [f"{m.id}: unknown scorecard indicator {x!r}" for x in m.fills if x not in indicators]
    for i in rubric.scorecard:
        if i.target not in common:
            errors.append(f"scorecard {i.id}: unknown profile key {i.target!r}")
        if i.fills not in dims:
            errors.append(f"scorecard {i.id}: unknown dimension {i.fills!r}")
        if i.dimension and i.dimension not in dims:
            errors.append(f"scorecard {i.id}: unknown dimension {i.dimension!r}")
        errors += [f"scorecard {i.id}: unknown evidence type {t!r}" for t in i.types if t not in rubric.evidenceTypes]
        errors += [f"scorecard {i.id}: unknown level {lv!r}" for lv in i.levels if lv not in LADDER]
        errors += [f"scorecard {i.id}: unknown Move {m!r}" for m in i.by if m not in moves]
        if bool(i.types) == bool(i.levels):
            errors.append(f"scorecard {i.id}: count either types or levels")
    return errors


def _conditions(rule: DecisionRule) -> bool:
    return bool(rule.gateFailed or rule.anyNotMet or rule.allMet or rule.atLeastPartly or rule.allUnknown
                or rule.demandBelowMinimum or rule.noneNotMet)


def raw_demand_rubric(config_dir: Path = Path("config")) -> dict[str, Any]:
    """The rubric (how evidence is judged) with the repertoire's Moves and Lines (how it is gathered) beside it."""
    with open(config_dir / "foundry" / "demand_evidence.yaml", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    with open(config_dir / "foundry" / "demand_repertoire.yaml", encoding="utf-8") as f:
        repertoire = yaml.safe_load(f)
    return {**raw, "repertoireVersion": repertoire["version"], "phases": repertoire.get("phases", {}),
            "tasks": repertoire.get("tasks", []), "moves": repertoire["moves"], "lines": repertoire["lines"]}


def load_demand_rubric(config_dir: Path = Path("config")) -> DemandRubric:
    try:
        return DemandRubric.model_validate(raw_demand_rubric(config_dir))
    except (OSError, KeyError, ValidationError) as exc:
        raise ConfigError(f"demand rubric in {config_dir / 'foundry'}: {exc}") from exc


# --- the case -----------------------------------------------------------------------------------------------------

class PriceFloor(_Config):
    amount: float
    currency: str = "USD"
    per: str = "purchase"


class Offering(_Config):
    name: str
    description: str = ""
    priceFloor: PriceFloor | None = None
    recurring: bool = False  # bought again and again (subscription, retainer, managed service)


class Segment(_Config):
    name: str
    profile: str


class EvidenceItem(_Config):
    id: str
    type: str
    summary: str
    source: str  # who or what it came from: a company (never a person's name), a page, a report
    channel: str = ""  # how it was gathered: interview, email, linkedin, landing page, desk
    segment: bool  # from the target segment
    independent: bool = True  # not the team, friends, existing customers or a panel told what to answer
    count: int = Field(default=1, ge=1)  # how many people or instances the item stands for
    supports: list[str] = []
    contradicts: list[str] = []
    price: float | None = None
    observedOn: date | None = None
    url: str | None = None


class Expectation(_Config):
    """A lab case's expected result, set before the rubric is run on it (Blueprint section 07: lab tests)."""
    decision: str
    dimensions: dict[str, State] = {}
    why: str = ""


class DemandCase(_Config):
    case: str
    question: str
    asOf: date
    offering: Offering
    segment: Segment
    gates: dict[str, bool | None] = {}
    evidence: list[EvidenceItem] = []
    notes: str | None = None
    movesRun: list[str] = []  # Moves already run for this case; not recommended again
    targets: dict[str, int | float] = {}  # this case's own thresholds, replacing the profile's
    expect: Expectation | None = None


def check_case(case: DemandCase, rubric: DemandRubric) -> list[str]:
    errors: list[str] = []
    if case.segment.profile not in rubric.profiles:
        errors.append(f"unknown segment profile {case.segment.profile!r} (known: {', '.join(rubric.profiles)})")
    fields = {g.field for g in rubric.gates}
    errors += [f"unknown gate {k!r} (known: {', '.join(sorted(fields))})" for k in case.gates if k not in fields]
    dims = {d.id for d in rubric.dimensions}
    seen: set[str] = set()
    for item in case.evidence:
        if item.id in seen:
            errors.append(f"evidence {item.id}: duplicate id")
        seen.add(item.id)
        if item.type not in rubric.evidenceTypes:
            errors.append(f"evidence {item.id}: unknown type {item.type!r}")
        errors += [f"evidence {item.id}: unknown dimension {x!r}" for x in item.supports + item.contradicts
                   if x not in dims]
        errors += [f"evidence {item.id}: both supports and contradicts {x}" for x in item.supports
                   if x in item.contradicts]
    moves = {m.id for m in rubric.moves}
    errors += [f"movesRun: unknown Move {m!r}" for m in case.movesRun if m not in moves]
    profile = rubric.profiles.get(case.segment.profile, {})
    errors += [f"targets: unknown profile key {k!r}" for k in case.targets if profile and k not in profile]
    if case.expect:
        if case.expect.decision not in {r.id for r in rubric.decisions}:
            errors.append(f"expect: unknown decision {case.expect.decision!r}")
        errors += [f"expect: unknown dimension {x!r}" for x in case.expect.dimensions if x not in dims]
    return errors


def load_case(path: Path, rubric: DemandRubric) -> DemandCase:
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        case = DemandCase.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise UsageError(f"demand case {path}: {exc}") from exc
    errors = check_case(case, rubric)
    if errors:
        raise UsageError(f"demand case {path}: " + "; ".join(errors))
    return case


# --- the assessment -----------------------------------------------------------------------------------------------

class DimensionResult(_Config):
    id: str
    title: str
    state: State
    reason: str
    support: int  # people or instances for, every rung above L0
    contra: int
    contested: bool = False
    missing: str | None = None  # what would meet it
    evidence: list[str]
    gatheredBy: list[str]


class GateResult(_Config):
    id: str
    text: str
    state: GateState


class RungCount(_Config):
    level: str
    name: str
    demand: bool
    items: int
    count: int
    fromSegment: int


class NextMove(_Config):
    id: str
    name: str
    effect: str
    forDimensions: list[str]


class DemandAssessment(_Config):
    case: str
    question: str
    asOf: date
    offering: str
    segment: str
    profile: str
    rubricVersion: str
    qualification: Qualification
    decision: str
    decisionText: str
    dimensions: list[DimensionResult]
    gates: list[GateResult]
    ladder: list[RungCount]
    nextMoves: list[NextMove]
    warnings: list[str]
    scope: str = SCOPE
    caseHash: str
    stamp: MechanismStamp


def assess(case: DemandCase, rubric: DemandRubric) -> DemandAssessment:
    errors = check_case(case, rubric)
    if errors:
        raise UsageError("demand case: " + "; ".join(errors))
    profile = case_profile(case, rubric)
    level = {item.id: rubric.evidenceTypes[item.type] for item in case.evidence}
    dims = [_judge(d, case, level, profile, rubric) for d in rubric.dimensions]
    state = {d.id: d.state for d in dims}
    gates = _gates(case, rubric, level)
    blocked = any(g.state in ("failed", "not_confirmed") for g in gates)
    demand = sum(i.count for i in case.evidence if i.segment and rubric.levels[level[i.id]].demand)
    rule = next(r for r in rubric.decisions if _holds(r, state, blocked, demand < profile["minDemandItems"]))
    return DemandAssessment(
        case=case.case, question=case.question, asOf=case.asOf, offering=case.offering.name,
        segment=case.segment.name, profile=case.segment.profile, rubricVersion=rubric.version,
        qualification=rubric.qualification, decision=rule.id, decisionText=rule.text, dimensions=dims,
        gates=gates, ladder=_ladder(case, rubric, level), nextMoves=_next_moves(rule, dims, rubric, case.movesRun),
        warnings=_warnings(case, rubric, level, dims),
        caseHash=content_hash(case.model_dump(mode="json", exclude={"expect"})),
        stamp=mechanism_stamp(rubric_version=rubric.version),
    )


def case_profile(case: DemandCase, rubric: DemandRubric) -> dict[str, int | float]:
    """The thresholds for this case: its segment's profile, with the case's own targets in their place."""
    return {**rubric.profiles[case.segment.profile], **case.targets}


def _holds(rule: DecisionRule, state: dict[str, State], blocked: bool, below_minimum: bool) -> bool:
    # A dimension that does not apply to this offering never holds a decision back.
    return all((
        not rule.gateFailed or blocked,
        not rule.anyNotMet or any(state[d] == "not_met" for d in rule.anyNotMet),
        all(state[d] in ("met", "not_applicable") for d in rule.allMet),
        all(state[d] in ("met", "partly", "not_applicable") for d in rule.atLeastPartly),
        all(state[d] in ("unknown", "not_applicable") for d in rule.allUnknown),
        not rule.demandBelowMinimum or below_minimum,
        not rule.noneNotMet or "not_met" not in state.values(),
    ))


def _count(case: DemandCase, level: dict[str, str], dim: str, cond: Condition) -> int:
    def tagged(item: EvidenceItem) -> bool:
        if cond.count == "support":
            return dim in item.supports
        if cond.count == "contra":
            return dim in item.contradicts
        return cond.count == "any" or dim in item.supports or dim in item.contradicts

    return sum(i.count for i in case.evidence
               if level[i.id] in cond.levels and (i.segment or not cond.segment) and tagged(i))


def _all_hold(conds: list[Condition], case: DemandCase, level: dict[str, str], dim: str,
              profile: dict[str, int | float]) -> bool:
    def limit(t: int | str) -> float:
        return profile[t] if isinstance(t, str) else t

    def ok(c: Condition) -> bool:
        n = _count(case, level, dim, c)
        return ((c.atLeast is None or n >= limit(c.atLeast)) and (c.atMost is None or n <= limit(c.atMost)))

    return bool(conds) and all(ok(c) for c in conds)


def _anchor(text: str, profile: dict[str, int | float]) -> str:
    return text.format(**profile)


def _judge(d: Dimension, case: DemandCase, level: dict[str, str], profile: dict[str, int | float],
           rubric: DemandRubric) -> DimensionResult:
    if d.appliesWhen == "recurring" and not case.offering.recurring:
        return DimensionResult(id=d.id, title=d.title, state="not_applicable", support=0, contra=0, evidence=[],
                               reason="Not applicable: the offering is bought once", gatheredBy=d.gatheredBy)
    counted = [i for i in case.evidence if level[i.id] != "L0"]
    support = sum(i.count for i in counted if d.id in i.supports)
    contra = sum(i.count for i in counted if d.id in i.contradicts)
    evidence = [i.id for i in counted if d.id in i.supports or d.id in i.contradicts]
    contested = False
    if d.check == "price":
        state, detail, priced = _price(case, level, profile)
        evidence = sorted(set(evidence) | set(priced), key=[i.id for i in case.evidence].index)
    elif d.check == "independence":
        # For and against here mean independent and not independent demand-level evidence from the segment.
        state, detail, items = _independence(case, level, profile, rubric)
        support = sum(i.count for i in items if i.independent)
        contra = sum(i.count for i in items if not i.independent)
        evidence = [i.id for i in items]
    else:
        not_met = _all_hold(d.whenNotMet, case, level, d.id, profile)
        met = _all_hold(d.whenMet, case, level, d.id, profile)
        contested = not_met and met
        if contested:
            state = "partly"
        elif not_met:
            state = "not_met"
        elif met:
            state = "met"
        elif _all_hold(d.whenPartly, case, level, d.id, profile):
            state = "partly"
        else:
            state = "unknown"
        detail = ""
    if contested:
        reason = (f"Contested: the evidence meets both '{_anchor(d.met, profile)}' and "
                  f"'{_anchor(d.notMet, profile)}'. The segment may be too broad")
    else:
        reason = {"met": _anchor(d.met, profile), "partly": _anchor(d.partly, profile),
                  "not_met": _anchor(d.notMet, profile), "unknown": "No evidence for or against yet"}[state]
    if detail:
        reason = f"{reason} ({detail})"
    return DimensionResult(
        id=d.id, title=d.title, state=state, reason=reason, support=support, contra=contra, contested=contested,
        missing=None if state == "met" else _anchor(d.met, profile), evidence=evidence, gatheredBy=d.gatheredBy,
    )


def _price(case: DemandCase, level: dict[str, str], profile: dict[str, int | float]
           ) -> tuple[State, str, list[str]]:
    floor = case.offering.priceFloor
    priced = [i for i in case.evidence if i.price is not None and i.segment and level[i.id] in STATED + COMMITTED]
    ids = [i.id for i in priced]
    if floor is None:
        return "unknown", "no price floor is recorded for the offering", ids
    at = sum(i.count for i in priced if level[i.id] in COMMITTED and i.price is not None and i.price >= floor.amount)
    below = sum(i.count for i in priced if level[i.id] in COMMITTED and i.price is not None and i.price < floor.amount)
    stated = sum(i.count for i in priced if level[i.id] in STATED and i.price is not None and i.price >= floor.amount)
    refused = sum(i.count for i in case.evidence
                  if i.segment and "DE07" in i.contradicts and level[i.id] in STATED + COMMITTED)
    detail = (f"floor {floor.amount:g} {floor.currency} per {floor.per}: {at} committed at or above, "
              f"{below} below, {stated} stated at or above, {refused} refused on price")
    if at >= profile["commitments"]:
        return "met", detail, ids
    if at == 0 and stated == 0 and (below >= profile["commitments"] or refused >= profile["refusals"]):
        return "not_met", detail, ids
    if at or below or stated:
        return "partly", detail, ids
    return "unknown", detail, ids


def _independence(case: DemandCase, level: dict[str, str], profile: dict[str, int | float],
                  rubric: DemandRubric) -> tuple[State, str, list[EvidenceItem]]:
    items = [i for i in case.evidence if i.segment and rubric.levels[level[i.id]].demand]
    n = sum(i.count for i in items)
    if n < profile["minDemandItems"]:
        return ("unknown", f"{n} demand-level items from the segment; {profile['minDemandItems']:g} needed to judge",
                items)
    share = sum(i.count for i in items if i.independent) / n
    sources = len({i.source for i in items})
    channels = len({i.channel for i in items if i.channel})
    detail = f"{sources} sources, {channels} channels, {share:.0%} independent"
    if share < 0.5:
        return "not_met", detail, items
    if sources >= profile["sources"] and channels >= profile["channels"] and share >= profile["independentShare"]:
        return "met", detail, items
    return "partly", detail, items


def _gates(case: DemandCase, rubric: DemandRubric, level: dict[str, str]) -> list[GateResult]:
    top = max((LADDER.index(lv) for lv in level.values()), default=-1)
    out = []
    for g in rubric.gates:
        value = case.gates.get(g.field)
        state: GateState
        if top < LADDER.index(g.appliesFrom):
            state = "not_applicable"
        elif value is None:
            state = "not_confirmed"
        else:
            state = "confirmed" if value else "failed"
        out.append(GateResult(id=g.id, text=g.text, state=state))
    return out


def _ladder(case: DemandCase, rubric: DemandRubric, level: dict[str, str]) -> list[RungCount]:
    out = []
    for lv in LADDER:
        items = [i for i in case.evidence if level[i.id] == lv]
        out.append(RungCount(level=lv, name=rubric.levels[lv].name, demand=rubric.levels[lv].demand,
                             items=len(items), count=sum(i.count for i in items),
                             fromSegment=sum(i.count for i in items if i.segment)))
    return out


def _next_moves(rule: DecisionRule, dims: list[DimensionResult], rubric: DemandRubric,
                done: list[str]) -> list[NextMove]:
    """The decision's own next Moves, or those that gather evidence for the dimensions not yet met, in Line
    order; a Move already run is left out."""
    unmet = [d for d in dims if d.state not in ("met", "not_applicable")]
    if rule.next is not None:
        ids = rule.next
    else:
        order = [m for stage in rubric.lines[0].stages for m in stage] if rubric.lines else []
        wanted = {m for d in unmet for m in d.gatheredBy}
        wanted -= set(done)
        ids = [m for m in dict.fromkeys(order) if m in wanted] + sorted(wanted - set(order))
        if ids and "DV07" in {m.id for m in rubric.moves}:
            ids.append("DV07")  # then assess again
    return [NextMove(id=m, name=rubric.move(m).name, effect=rubric.move(m).effect,
                     forDimensions=[d.id for d in unmet if m in d.gatheredBy]) for m in ids]


def _warnings(case: DemandCase, rubric: DemandRubric, level: dict[str, str],
              dims: list[DimensionResult]) -> list[str]:
    out = []
    if rubric.qualification == "candidate":
        out.append(f"Rubric {rubric.version} is a candidate: it can help a specialist think, but should not "
                   "decide a high-stakes allocation alone (Blueprint section 07)")
    sims = sum(1 for lv in level.values() if lv == "L0")
    if sims:
        out.append(f"{sims} simulated or model-generated item(s) are listed; they generate hypotheses and never "
                   "count as demand")
    attention = sum(i.count for i in case.evidence if i.segment and level[i.id] == "L2")
    acted = next((d for d in dims if d.id == "DE05"), None)
    if attention and acted is not None and acted.state != "met":
        actions = sum(i.count for i in case.evidence
                      if i.segment and rubric.levels[level[i.id]].demand and "DE05" in i.supports)
        out.append(f"Attention is not intent: {attention} visits, clicks or contacts from the segment against "
                   f"{actions} actions")
    out += [f"{d.id} is contested ({d.support} for, {d.contra} against): the segment may be too broad, so "
            "consider splitting it" for d in dims if d.contested]
    return out


# --- the scorecard -----------------------------------------------------------------------------------------------

class Indicator(_Config):
    id: str
    label: str
    current: int
    target: int | float
    state: Literal["reached", "open", "not_applicable"]
    fills: str
    by: list[str]


def scorecard(case: DemandCase, rubric: DemandRubric) -> list[Indicator]:
    """Each indicator counted from the case's evidence against its target. The indicators are shown side by side
    and never added up: the decision comes from the rubric, not from how many indicators are reached."""
    profile = case_profile(case, rubric)
    out = []
    for spec in rubric.scorecard:
        target = profile[spec.target]
        if spec.appliesWhen == "recurring" and not case.offering.recurring:
            out.append(Indicator(id=spec.id, label=spec.label, current=0, target=target, state="not_applicable",
                                 fills=spec.fills, by=spec.by))
            continue
        items = [i for i in case.evidence
                 if (i.type in spec.types if spec.types else rubric.evidenceTypes[i.type] in spec.levels)
                 and (i.segment or not spec.segment)
                 and (spec.dimension is None or spec.dimension in i.supports)]
        if spec.distinct:
            current = len({getattr(i, spec.distinct) for i in items if getattr(i, spec.distinct)})
        else:
            current = sum(i.count for i in items)
        out.append(Indicator(id=spec.id, label=spec.label, current=current, target=target,
                             state="reached" if current >= target else "open", fills=spec.fills, by=spec.by))
    return out


# --- the report ---------------------------------------------------------------------------------------------------

_STATE = {"met": "met", "partly": "partly", "not_met": "not met", "unknown": "unknown",
          "not_applicable": "not applicable"}
_GATE = {"confirmed": "confirmed", "failed": "FAILED", "not_confirmed": "not confirmed (blocks)",
         "not_applicable": "not yet applicable"}


def render_markdown(a: DemandAssessment, case: DemandCase, rubric: DemandRubric) -> str:
    def cell(text: Any) -> str:
        return str(text).replace("|", "\\|").replace("\n", " ")

    floor = case.offering.priceFloor
    price = f"{floor.amount:g} {floor.currency} per {floor.per}" if floor else "not set"
    lines = [
        f"# Demand evidence: {a.question}",
        "",
        f"> {a.scope}",
        "",
        f"**{a.decisionText}.**",
        "",
        "| | |",
        "|---|---|",
        f"| Offering | {cell(case.offering.name)}: {cell(case.offering.description)} (price floor {price}) |",
        f"| Segment | {cell(a.segment)} (profile `{a.profile}`) |",
        f"| Evidence | {len(case.evidence)} items, as of {a.asOf.isoformat()} |",
        f"| Rubric | `{a.rubricVersion}`, {a.qualification} |",
        "",
        "## Dimensions",
        "",
        "Each is judged on its own; there is no total.",
        "",
        "| ID | Dimension | Judgement | For | Against | Why | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [f"| {d.id} | {cell(d.title)} | {_STATE[d.state]} | {d.support} | {d.contra} | {cell(d.reason)} | "
              f"{', '.join(d.evidence) or '-'} |" for d in a.dimensions]
    lines += ["", "## Gates", "", "A gate that is not confirmed blocks the decision, whatever the dimensions say.",
              "", "| ID | Gate | State |", "|---|---|---|"]
    lines += [f"| {g.id} | {cell(g.text)} | {_GATE[g.state]} |" for g in a.gates]
    lines += ["", "## Evidence ladder", "",
              "| Rung | What it is | Counts as demand | Items | People or instances | From the segment |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {r.level} | {cell(r.name)} | {'yes' if r.demand else 'no'} | {r.items} | {r.count} | "
              f"{r.fromSegment} |" for r in a.ladder]
    missing = [d for d in a.dimensions if d.missing]
    lines += ["", "## What is missing", ""]
    lines += [f"- **{d.id} {d.title}** ({_STATE[d.state]}). To meet it: {d.missing}."
              for d in missing] or ["- Nothing."]
    lines += ["", "## Next Moves", ""]
    lines += [f"{n}. **{m.id}** {m.name} ({m.effect}"
              + ("; contacts, publishes or spends, so it needs an approved charter" if m.effect == "E3" else "")
              + ")" + (f", for {', '.join(m.forDimensions)}" if m.forDimensions else "")
              for n, m in enumerate(a.nextMoves, 1)] or ["None until the gates are confirmed."]
    if a.warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}." for w in a.warnings]
    lines += ["", "## Evidence", "",
              "| ID | Type | Rung | Summary | Source | Channel | Segment | Independent | Count | Price | For "
              "| Against |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i in case.evidence:
        lines.append(
            f"| {i.id} | {i.type} | {rubric.evidenceTypes[i.type]} | {cell(i.summary)} | {cell(i.source)} | "
            f"{cell(i.channel) or '-'} | {'yes' if i.segment else 'no'} | {'yes' if i.independent else 'no'} | "
            f"{i.count} | {'-' if i.price is None else f'{i.price:g}'} | {', '.join(i.supports) or '-'} | "
            f"{', '.join(i.contradicts) or '-'} |")
    s = a.stamp
    lines += ["", f"Mechanism: rubric `{a.rubricVersion}`, code {s.codeVersion}"
              + (f" ({s.gitCommit[:8]})" if s.gitCommit else "") + f", case hash `{a.caseHash[:12]}`.", ""]
    return "\n".join(lines)


# --- the lab ------------------------------------------------------------------------------------------------------

class LabResult(_Config):
    case: str
    expected: str
    decision: str
    differences: list[str]
    why: str
    agrees: bool


def run_lab(lab_dir: Path, rubric: DemandRubric) -> list[LabResult]:
    """Run every lab case that carries an expected result (Blueprint section 07: lab tests with difficult and
    adversarial examples). Agreement counts toward `lab-tested` only when someone other than the rubric's author
    set the expectations."""
    results = []
    for path in sorted(lab_dir.glob("*.yaml")):
        case = load_case(path, rubric)
        if case.expect is None:
            continue
        a = assess(case, rubric)
        got = {d.id: d.state for d in a.dimensions}
        differences = [f"{k} expected {v}, got {got[k]}" for k, v in case.expect.dimensions.items() if got[k] != v]
        results.append(LabResult(case=case.case, expected=case.expect.decision, decision=a.decision,
                                 differences=differences, why=case.expect.why,
                                 agrees=a.decision == case.expect.decision and not differences))
    return results
