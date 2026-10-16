"""The validation rubric (config/validation.yaml): what each check asks, how it is tested, when it
passes and what happens when it fails. The checks themselves are code in market/vichara.py."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict


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


class ValidationRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    source: str
    task: str
    analogy: str
    escalation: str
    checks: list[RubricCheck]
    groundingVerdicts: dict[str, str]


@cache
def _load(path: Path) -> ValidationRubric:
    with open(path, encoding="utf-8") as f:
        return ValidationRubric.model_validate(yaml.safe_load(f))


def load_validation_rubric(config_dir: Path = Path("config")) -> ValidationRubric:
    return _load(Path(config_dir) / "validation.yaml")
