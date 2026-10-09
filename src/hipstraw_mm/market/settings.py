"""Loads config/pipeline.yaml (contracts/config.md)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator


class BeamSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int
    finalPaths: int
    companiesPerPath: int
    minSearchScore: float = 0.0

    @field_validator("minSearchScore")
    @classmethod
    def _score_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("beam.minSearchScore must be between 0 and 1")
        return v

    @field_validator("companiesPerPath")
    @classmethod
    def _companies_le_10(cls, v: int) -> int:
        if v > 10:
            raise ValueError("companiesPerPath must be <= 10")
        return v


class RepairSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maxAttempts: int

    @field_validator("maxAttempts")
    @classmethod
    def _between_1_and_3(cls, v: int) -> int:
        if not (1 <= v <= 3):
            raise ValueError("maxAttempts must be between 1 and 3")
        return v


class VicharaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maxItemsPerDimension: int


class LinksSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lowConfidenceThreshold: float
    linksPerCall: int


class EvidenceStateSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sufficiencyHalf: float
    decisionReadyMinCompanies: int
    qualityMixedFloor: float
    qualityStrongFloor: float


class BudgetSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelCallsPerRun: int


class TraceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maxBlobBytes: int


class ModelPricing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: float
    output: float


class ViewerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str
    port: int
    pollSeconds: int

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, v: str) -> str:
        if v not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(f"viewer.host must be a loopback address, got {v!r}")
        return v


class ObjectiveSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maxChars: int = 120_000


class PipelineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    beam: BeamSettings
    defaultInterestIds: list[str]
    factorWeights: dict[str, float]
    repair: RepairSettings
    vichara: VicharaSettings
    links: LinksSettings
    evidenceStates: EvidenceStateSettings
    budgets: BudgetSettings
    trace: TraceSettings
    modelPricing: dict[str, ModelPricing]
    viewer: ViewerSettings
    objective: ObjectiveSettings = ObjectiveSettings()

    @field_validator("beam")
    @classmethod
    def _final_le_width(cls, v: BeamSettings) -> BeamSettings:
        if v.finalPaths > v.width:
            raise ValueError("beam.finalPaths must be <= beam.width")
        return v

    @field_validator("factorWeights")
    @classmethod
    def _weights_positive(cls, v: dict[str, float]) -> dict[str, float]:
        for name, weight in v.items():
            if weight <= 0:
                raise ValueError(f"factor weight {name} must be > 0")
        return v

    def model_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> float | None:
        pricing = self.modelPricing.get(model_name)
        if pricing is None:
            return None
        return (input_tokens / 1_000_000) * pricing.input + (output_tokens / 1_000_000) * pricing.output


def load_pipeline_settings(config_dir: Path = Path("config")) -> PipelineSettings:
    path = config_dir / "pipeline.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return PipelineSettings.model_validate(raw)
