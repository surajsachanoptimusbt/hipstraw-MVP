"""The validation rubric (config/validation.yaml): for each task the router may send to open-weight,
which checks run, what each asks, how it is tested, when it passes and what happens when it fails, and
which rules may answer before any model. The checks and rules themselves are code."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RubricCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    question: str
    method: str
    passWhen: str
    onFail: str
    catches: str
    tiers: list[Literal["open_weight", "frontier"]]
    blocking: bool = True  # False: a failure is logged as a warning and does not escalate


class RubricRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    when: str
    result: str


class TaskRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checks: list[str]
    rules: list[str] = Field(default_factory=list)


class ValidationRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    source: str
    analogy: str
    escalation: str
    rules: list[RubricRule]
    checks: list[RubricCheck]
    tasks: dict[str, TaskRubric]
    groundingVerdicts: dict[str, str]

    @model_validator(mode="after")
    def _references_exist(self) -> ValidationRubric:
        checks = {c.id for c in self.checks}
        rules = {r.id for r in self.rules}
        for name, task in self.tasks.items():
            if missing := set(task.checks) - checks:
                raise ValueError(f"{name} lists undefined checks {sorted(missing)}")
            if missing := set(task.rules) - rules:
                raise ValueError(f"{name} lists undefined rules {sorted(missing)}")
        return self

    def task_checks(self, task: str, tier: str) -> list[str]:
        by_id = {c.id: c for c in self.checks}
        return [c for c in self.tasks[task].checks if tier in by_id[c].tiers]


@cache
def _load(path: Path) -> ValidationRubric:
    with open(path, encoding="utf-8") as f:
        return ValidationRubric.model_validate(yaml.safe_load(f))


def load_validation_rubric(config_dir: Path = Path("config")) -> ValidationRubric:
    return _load(Path(config_dir) / "validation.yaml")
