"""Loads config/grammar.yaml — the 19 Market Manager dimensions (Constitution XIV)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class Dimension(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    type: str
    question: str
    reviewFrequency: str
    states: list[str]
    rank: dict[str, int]
    level: str
    evaluationKind: str
    assessedBy: str
    decidedBy: str


class Grammar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimensions: list[Dimension]

    def by_key(self, key: str) -> Dimension | None:
        for d in self.dimensions:
            if d.key == key:
                return d
        return None


def load_grammar(config_dir: Path = Path("config")) -> Grammar:
    path = config_dir / "grammar.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Grammar.model_validate(raw)
