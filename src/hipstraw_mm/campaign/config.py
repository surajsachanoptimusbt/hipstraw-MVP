"""Loaders for config/campaign/: trace layers, roles and settings. Unknown keys are rejected."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from hipstraw_mm.market.layers import LayerConfig


def _read(config_dir: Path, name: str) -> Any:
    with open(config_dir / "campaign" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


class RolesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    roles: dict[str, list[str]]


class CoreAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    general: list[str]
    perChannel: str


class FetchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeoutSeconds: float
    maxBytes: int


class CampaignSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    launchMarkets: list[str]
    nearDayZeroDays: int
    maxVariants: int
    metricFreshDays: int
    fetch: FetchSettings
    scopeStatement: str
    coreAssumptions: CoreAssumptions


def load_campaign_layers(config_dir: Path = Path("config")) -> LayerConfig:
    return LayerConfig.model_validate(_read(config_dir, "layers.yaml"))


def load_roles(config_dir: Path = Path("config")) -> RolesConfig:
    return RolesConfig.model_validate(_read(config_dir, "roles.yaml"))


def load_settings(config_dir: Path = Path("config")) -> CampaignSettings:
    return CampaignSettings.model_validate(_read(config_dir, "settings.yaml"))
