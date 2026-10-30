"""The launch-tactic repertoire: Moves and Lines from config/campaign/, and the Line lint (FR-015 to FR-019).

At G0 a Line is a versioned list of stages a human chooses and the stage runner executes; there is no
compiler (HA section 5). The lint is what keeps that safe: a repertoire that names an unknown Move or
handler, puts an external effect before a Test Plan, or lets a model raise a claim does not load.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hipstraw_mm.campaign.conditions import Condition, condition_errors
from hipstraw_mm.campaign.models import ITEM_STATES, EffectClass, ItemKind
from hipstraw_mm.errors import ConfigError

# The highest claim states a model-produced (E2) output may set: never observed or verified.
E2_CLAIM_STATES = frozenset({"unverified", "reported", "contested"})


class TransitionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    kind: ItemKind
    fromStates: list[str | None] = Field(alias="from")
    toStates: list[str] = Field(alias="to")


class MoveDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int | None = None
    name: str
    group: str
    effectClasses: list[EffectClass] = Field(min_length=1)
    eligibility: Condition | None = None
    inputs: list[str] = []
    transitions: list[TransitionSpec] = []
    risks: list[str] = []
    handler: str
    promptVersion: str | None = None
    producesTestPlan: bool = False
    requiresApproval: Literal["test_plan"] | None = None


class LineDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int | None = None
    name: str
    stages: list[list[str]] = Field(min_length=1)
    reviewQuestion: str = ""
    useWhen: Condition
    excludeWhen: Condition | None = None


class MovesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    source: str | None = None
    moves: list[MoveDef]


class LinesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    lines: list[LineDef]


@dataclass(frozen=True)
class Repertoire:
    version: str
    moves: dict[str, MoveDef]
    lines: dict[str, LineDef]


def _move_errors(move: MoveDef, handlers: Collection[str]) -> list[str]:
    errors: list[str] = []
    if not move.version:
        errors.append(f"{move.id}: no version")
    if move.handler not in handlers:
        errors.append(f"{move.id}: handler {move.handler!r} does not exist")
    if "E3" in move.effectClasses and move.requiresApproval != "test_plan":
        errors.append(
            f"{move.id}: an external-effect (E3) Move must require Test Plan approval (requiresApproval: test_plan)"
        )
    if "E2" in move.effectClasses and not move.promptVersion:
        errors.append(f"{move.id}: an inference (E2) Move must name its promptVersion")
    for t in move.transitions:
        states = ITEM_STATES[t.kind]
        bad = [s for s in [*t.fromStates, *t.toStates] if s is not None and s not in states]
        if bad:
            errors.append(f"{move.id}: {', '.join(bad)} is not a {t.kind} state")
        if "E2" in move.effectClasses and t.kind == "claim":
            above = [s for s in t.toStates if s not in E2_CLAIM_STATES]
            if above:
                errors.append(f"{move.id}: an inference (E2) Move cannot set a claim to {', '.join(above)}")
    errors += condition_errors(move.eligibility, move.id, "eligibility")
    return errors


def _line_errors(line: LineDef, moves: dict[str, MoveDef]) -> list[str]:
    errors: list[str] = []
    if not line.version:
        errors.append(f"{line.id}: no version")
    if not line.reviewQuestion.strip():
        errors.append(f"{line.id}: no reviewQuestion (every Line ends in a Review)")
    test_plan_seen = False
    for n, stage in enumerate(line.stages, start=1):
        if not stage:
            errors.append(f"{line.id}: stage {n} is empty")
        for move_id in stage:
            move = moves.get(move_id)
            if move is None:
                errors.append(f"{line.id}: stage {n} names unknown Move {move_id}")
                continue
            if "E3" in move.effectClasses and not test_plan_seen:
                errors.append(
                    f"{line.id}: {move_id} is an external effect (E3) with no Test Plan step in an earlier stage"
                )
        # A Test Plan drafted in this stage only covers E3 Moves in later stages.
        test_plan_seen = test_plan_seen or any(
            moves[m].producesTestPlan for m in stage if m in moves
        )
    errors += condition_errors(line.useWhen, line.id, "useWhen")
    errors += condition_errors(line.excludeWhen, line.id, "excludeWhen")
    return errors


def lint(moves_file: MovesFile, lines_file: LinesFile, handlers: Collection[str]) -> list[str]:
    """Every Line lint error (contracts/config.md), in file order, each naming the Move or Line."""
    errors: list[str] = []
    if moves_file.version != lines_file.version:
        errors.append(f"moves.yaml is {moves_file.version} but lines.yaml is {lines_file.version}")
    for kind, ids in (("Move", [m.id for m in moves_file.moves]), ("Line", [x.id for x in lines_file.lines])):
        errors += [f"{i}: duplicate {kind} ID" for i, n in Counter(ids).items() if n > 1]
    moves = {m.id: m for m in moves_file.moves}
    for move in moves_file.moves:
        errors += _move_errors(move, handlers)
    for line in lines_file.lines:
        errors += _line_errors(line, moves)
    return errors


def _load(path: Path, model: type[MovesFile] | type[LinesFile]) -> MovesFile | LinesFile:
    try:
        with open(path, encoding="utf-8") as f:
            return model.model_validate(yaml.safe_load(f))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def load_repertoire(config_dir: Path = Path("config")) -> Repertoire:
    """Load and lint config/campaign/moves.yaml and lines.yaml; raise ConfigError listing every problem."""
    from hipstraw_mm.campaign.moves import HANDLERS

    folder = config_dir / "campaign"
    moves_file = _load(folder / "moves.yaml", MovesFile)
    lines_file = _load(folder / "lines.yaml", LinesFile)
    assert isinstance(moves_file, MovesFile) and isinstance(lines_file, LinesFile)
    errors = lint(moves_file, lines_file, HANDLERS.keys())
    if errors:
        raise ConfigError("Line lint failed:\n  " + "\n  ".join(errors))
    return Repertoire(
        version=moves_file.version,
        moves={m.id: m for m in moves_file.moves},
        lines={x.id: x for x in lines_file.lines},
    )
