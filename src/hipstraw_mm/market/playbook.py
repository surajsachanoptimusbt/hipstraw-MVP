"""The Hipstraw Market Mastery Playbook as structured data (config/playbook/*.yaml).

Extracted from the playbook PDF by scripts/extract_playbook.py and reviewed. `load_playbook` checks that
every reference resolves and that each card's stance set matches the playbook's stance matrices, so a
bad edit fails at load time instead of producing a wrong recommendation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

STANCES = ["Listen", "Scout", "Probe", "Co-create", "Activate", "Build", "Expand", "Protect"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StanceSet(_Strict):
    default: str | None
    allowed: list[str] = []
    never: list[str] = []

    def permits(self, stance: str) -> bool:
        return stance == self.default or stance in self.allowed


class StrategyPlays(_Strict):
    primary: list[str]
    also: list[str]


class Strategy(_Strict):
    id: str
    name: str
    purpose: str
    useWhen: str | None
    dontUseWhen: str | None
    mustBeTrue: str | None
    stance: StanceSet
    plays: StrategyPlays
    lines: list[str]
    levers: list[str]
    whoDecides: str | None
    doneWhen: str | None
    example: str | None
    tip: str | None


class PlayStrategy(_Strict):
    primary: str
    also: list[str]


class PlayLines(_Strict):
    preferredText: str
    preferred: list[str]
    alternatives: list[str]


class FirstStep(_Strict):
    id: str | None
    text: str


class Play(_Strict):
    id: str
    name: str
    discipline: str
    purpose: str
    useWhen: str | None
    dontUseWhen: str | None
    mustBeTrue: str | None
    stance: StanceSet
    strategy: PlayStrategy
    lines: PlayLines
    gambits: list[str]
    firstStep: FirstStep
    whoDecides: str | None
    doneWhen: str | None
    example: str | None
    tip: str | None


class LineStep(_Strict):
    id: str
    text: str | None


class LineUsedBy(_Strict):
    primary: list[str]
    alternative: list[str]


class Line(_Strict):
    id: str
    name: str
    discipline: str
    purpose: str
    startsWhen: str
    steps: list[LineStep]
    branches: str | None
    branchIds: list[str]
    window: str | None
    stopIf: str | None
    escalateIf: str | None
    doneWhen: str | None
    stance: StanceSet
    usedBy: LineUsedBy
    whoDecides: str | None


class MoveStance(_Strict):
    default: str | None
    never: list[str]
    everyStance: bool


class Move(_Strict):
    id: str
    name: str
    useWhen: str
    neverWhen: str
    stance: MoveStance
    tasks: list[str]
    doneWhen: str


class Gambit(_Strict):
    id: str
    name: str
    give: str
    get: str
    maxLossIllustrative: str
    fallback: str
    approver: str
    useWhen: str | None
    dontUseWhen: str | None
    mustBeTrue: str | None
    stance: StanceSet
    usedWith: list[str]
    netValueCheck: str | None


class Action(_Strict):
    id: str
    name: str
    tier: int
    tierName: str
    showsInActivityAs: str
    whoCanRun: str
    undo: str


class StanceDef(_Strict):
    name: str
    behaviour: str
    typicalMoves: list[str]
    never: str
    soundsLike: str
    lastsUntil: str


class HardRule(_Strict):
    id: int
    rule: str
    why: str
    example: str
    whenHit: str


class Gate(_Strict):
    gate: str
    discipline: str
    requiredEvidence: str
    ifNotMet: str


class MarketType(_Strict):
    id: str
    name: str
    reality: str
    priorityPlays: list[str]
    typicalTrap: str


class Situation(_Strict):
    whatYouSee: str
    play: str
    firstStep: str
    firstStepId: str | None
    axis: str


class StateCall(_Strict):
    axis: str
    state: str
    showsWhen: str
    callsFor: list[str]
    callsForText: str


class AxisState(_Strict):
    screen: str
    registry: str


class Axis(_Strict):
    id: str
    screenName: str
    registryName: str
    manages: str
    states: list[AxisState]


class Matrices(_Strict):
    positionStance: dict[str, dict[str, dict[str, str]]]
    strategyStance: dict[str, dict[str, str]]
    gambitStance: dict[str, dict[str, str]]


class BindingRule(_Strict):
    worstFirst: list[tuple[str, str]]
    order: list[str]
    settled: dict[str, list[str]]


class StateOverride(_Strict):
    axis: str
    state: str
    disposition: str


class DispositionRule(_Strict):
    overrides: list[StateOverride]
    noIncludedCompanies: str
    byStance: dict[str, str]
    attention: dict[str, str]
    order: list[str]


class Picker(_Strict):
    version: str
    source: str
    executionMode: str
    bindingConstraint: BindingRule
    disposition: DispositionRule


class Playbook(_Strict):
    version: str
    axes: list[Axis]
    dispositions: list[str]
    attentionTiers: list[str]
    strategies: list[Strategy]
    plays: list[Play]
    lines: list[Line]
    moves: list[Move]
    gambits: list[Gambit]
    actions: list[Action]
    stances: list[StanceDef]
    hardRules: list[HardRule]
    gates: list[Gate]
    marketTypes: list[MarketType]
    situations: list[Situation]
    stateCalls: list[StateCall]
    matrices: Matrices
    picker: Picker

    @model_validator(mode="after")
    def _integrity(self) -> Playbook:
        problems = integrity_problems(self)
        if problems:
            raise ValueError("playbook integrity: " + "; ".join(problems[:10]))
        return self

    def strategy(self, sid: str) -> Strategy:
        return _index(self.strategies)[sid]

    def play(self, pid: str) -> Play:
        return _index(self.plays)[pid]

    def line(self, lid: str) -> Line:
        return _index(self.lines)[lid]

    def move(self, mid: str) -> Move:
        return _index(self.moves)[mid]

    def gambit(self, gid: str) -> Gambit:
        return _index(self.gambits)[gid]

    def action(self, aid: str) -> Action:
        return _index(self.actions)[aid]

    def market_type(self, tid: str) -> MarketType:
        return _index(self.marketTypes)[tid]

    def axis(self, aid: str) -> Axis:
        return _index(self.axes)[aid]

    def step_name(self, sid: str) -> str:
        if sid.startswith("M"):
            return self.move(sid).name
        if sid.startswith("A"):
            return self.action(sid).name
        return self.line(sid).name

    def calls_for(self, axis: str, state: str) -> list[str]:
        return next(c.callsFor for c in self.stateCalls if c.axis == axis and c.state == state)


class _Identified(Protocol):
    id: str


_T = TypeVar("_T", bound=_Identified)


def _index(items: list[_T]) -> dict[str, _T]:
    return {i.id: i for i in items}


def integrity_problems(pb: Playbook) -> list[str]:
    """References resolve, counts match the playbook, and card stance sets agree with the matrices."""
    problems: list[str] = []
    counts = {"strategies": 16, "plays": 32, "lines": 20, "moves": 56, "gambits": 12, "actions": 60,
              "stances": 8, "hardRules": 20, "marketTypes": 16, "axes": 7}
    for name, n in counts.items():
        if len(getattr(pb, name)) != n:
            problems.append(f"{name}: {len(getattr(pb, name))} items, the playbook has {n}")
    known = {i.id for group in (pb.strategies, pb.plays, pb.lines, pb.moves, pb.gambits, pb.actions) for i in group}

    def need(ref: str | None, where: str) -> None:
        if ref and ref not in known:
            problems.append(f"{where} refers to unknown {ref}")

    for s in pb.strategies:
        for ref in [*s.plays.primary, *s.plays.also, *s.lines]:
            need(ref, s.id)
        if _stance_cells(s.stance) != pb.matrices.strategyStance.get(s.id):
            problems.append(f"{s.id} stance card differs from the Strategy × Stance matrix")
    for p in pb.plays:
        refs: list[str | None] = [p.strategy.primary, *p.strategy.also, *p.lines.preferred,
                                  *p.lines.alternatives, *p.gambits, p.firstStep.id]
        for maybe in refs:
            need(maybe, p.id)
    for ln in pb.lines:
        for ref in [st.id for st in ln.steps] + ln.branchIds + ln.usedBy.primary + ln.usedBy.alternative:
            need(ref, ln.id)
        naming = {p.id for p in pb.plays if ln.id in p.lines.preferred + p.lines.alternatives}
        if naming != set(ln.usedBy.primary + ln.usedBy.alternative):
            problems.append(f"{ln.id} 'used by' differs from the plays that name it")
    for m in pb.moves:
        for ref in m.tasks:
            need(ref, m.id)
    for g in pb.gambits:
        for ref in g.usedWith:
            need(ref, g.id)
        cells = pb.matrices.gambitStance.get(g.id, {})
        usable = {k: v for k, v in cells.items() if v != "never"}
        if {k: v for k, v in _stance_cells(g.stance).items() if v != "never"} != usable:
            problems.append(f"{g.id} stance card differs from the Gambit × Stance matrix")
        if any(cells.get(s) != "never" for s in ("Listen", "Scout", "Protect")):
            problems.append(f"{g.id} breaks stance rule 5 (no Gambit in Listen, Scout or Protect)")
    for t in pb.marketTypes:
        for ref in t.priorityPlays:
            need(ref, t.id)
    for sit in pb.situations:
        need(sit.play, f"situation '{sit.whatYouSee}'")
        need(sit.firstStepId, f"situation '{sit.whatYouSee}'")
    for axis in pb.axes:
        screens = [s.screen for s in axis.states]
        if list(pb.matrices.positionStance.get(axis.id, {})) != screens:
            problems.append(f"{axis.id} states differ from the Position × Stance matrix")
        if [c.state for c in pb.stateCalls if c.axis == axis.id] != screens:
            problems.append(f"{axis.id} states differ from §2.2")
    return problems


def _stance_cells(stance: StanceSet) -> dict[str, str]:
    cells = {s: "allowed" for s in stance.allowed}
    cells |= {s: "never" for s in stance.never}
    if stance.default:
        cells[stance.default] = "default"
    return cells


def _read(path: Path, key: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)[key]


@lru_cache(maxsize=4)
def load_playbook(config_dir: Path = Path("config")) -> Playbook:
    d = config_dir / "playbook"
    axes_doc = yaml.safe_load((d / "axes.yaml").read_text(encoding="utf-8"))
    with open(d / "picker.yaml", encoding="utf-8") as f:
        picker = yaml.safe_load(f)
    return Playbook.model_validate({
        "version": axes_doc["version"],
        "axes": axes_doc["axes"],
        "dispositions": axes_doc["dispositions"],
        "attentionTiers": axes_doc["attentionTiers"],
        "strategies": _read(d / "strategies.yaml", "strategies"),
        "plays": _read(d / "plays.yaml", "plays"),
        "lines": _read(d / "lines.yaml", "lines"),
        "moves": _read(d / "moves.yaml", "moves"),
        "gambits": _read(d / "gambits.yaml", "gambits"),
        "actions": _read(d / "actions.yaml", "actions"),
        "stances": _read(d / "stances.yaml", "stances"),
        "hardRules": _read(d / "hard_rules.yaml", "hardRules"),
        "gates": _read(d / "gates.yaml", "gates"),
        "marketTypes": _read(d / "market_types.yaml", "marketTypes"),
        "situations": _read(d / "situations.yaml", "situations"),
        "stateCalls": _read(d / "state_calls.yaml", "stateCalls"),
        "matrices": _read(d / "matrices.yaml", "matrices"),
        "picker": picker,
    })
