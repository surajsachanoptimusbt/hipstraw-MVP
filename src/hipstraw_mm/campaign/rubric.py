"""The campaign rubric (config/campaign/rubric.yaml): plain questions with observable anchors."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict


class RubricQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    # `channel`: judged once per channel of the campaign; `campaign`: once for the whole campaign.
    scope: Literal["channel", "campaign"] = "campaign"
    area: Literal["strategy", "readiness"]
    question: str
    met: str
    partly: str
    notMet: str
    fix: str


class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    status: str | None = None
    questions: list[RubricQuestion]

    def question(self, question_id: str) -> RubricQuestion | None:
        return next((q for q in self.questions if q.id == question_id), None)

    def expected(self, channels: list[str]) -> list[tuple[str, str]]:
        """Every (question, channel) the rubric asks for, channel "" for a campaign-wide question."""
        return [(q.id, c) for q in self.questions for c in (channels if q.scope == "channel" else [""])]


def load_rubric(config_dir: Path = Path("config")) -> Rubric:
    with open(config_dir / "campaign" / "rubric.yaml", encoding="utf-8") as f:
        return Rubric.model_validate(yaml.safe_load(f))
