"""Configuration files: program, run, metros, source policy, and the first position (contracts/config.md)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from hipstraw_mm.errors import ConfigError
from hipstraw_mm.models import IdLabel, Reliability, SourceType, host_matches_domain, host_of

SourceTypeCategory = Literal["registry", "job_board", "directory", "news"]
ALL_SOURCE_TYPES: tuple[str, ...] = ("registry", "news", "company_site", "job_board", "directory")

_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

M = TypeVar("M", bound=BaseModel)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProgramConfig(_Strict):
    programId: str = Field(min_length=1)
    name: str
    sourceUrl: str
    objective: str
    experimentContexts: list[IdLabel]
    primaryInterests: list[IdLabel]

    @field_validator("experimentContexts", "primaryInterests")
    @classmethod
    def _exactly_six_unique(cls, v: list[IdLabel]) -> list[IdLabel]:
        if len(v) != 6:
            raise ValueError(f"must have exactly 6 entries, got {len(v)}")
        if len({x.id for x in v}) != 6:
            raise ValueError("ids must be unique")
        return v


class Constraints(_Strict):
    maxEmployees: int = Field(gt=0)
    maxRevenueUsd: int = Field(gt=0)
    metroIds: list[str] = Field(min_length=1)
    largeEnterpriseParents: list[str] = []


class Budgets(_Strict):
    discoveryQueries: int = Field(ge=1)
    resultsPerQuery: int = Field(ge=1, le=20)
    listingPagesFetched: int = Field(ge=1)
    profileHopsPerRun: int = Field(ge=0)
    companiesKept: int = Field(ge=1, le=10)
    ownSitePagesPerCompany: int = Field(ge=0)
    signalSearchesPerCompany: int = Field(ge=0)
    thirdPartyPagesPerCompany: int = Field(ge=0)
    verifyFetchesPerRun: int = Field(ge=1)
    verifyModelCallsPerRun: int = Field(ge=1)


class FetchSettings(_Strict):
    timeoutSeconds: float = Field(gt=0)
    maxBytes: int = Field(gt=0)
    perHostDelaySeconds: float = Field(ge=0)
    maxPageChars: int = Field(gt=0)


class ModelSettings(_Strict):
    # None when the environment variable it refers to is unset; steps that call the model require it.
    name: str | None


class RunConfig(_Strict):
    projectId: str
    constraints: Constraints
    budgets: Budgets
    fetch: FetchSettings
    model: ModelSettings

    @field_validator("projectId")
    @classmethod
    def _demo_only(cls, v: str) -> str:
        if not v.startswith("demo-"):
            raise ValueError("must start with 'demo-' (emulator projects only)")
        return v


class SourcePolicy(_Strict):
    userAgent: str = Field(min_length=1)
    denylistDomains: list[str]
    reliabilityBySourceType: dict[SourceType, Reliability]
    reliabilityWeights: dict[str, float]
    sourceTypeDomains: dict[SourceTypeCategory, list[str]]

    @field_validator("denylistDomains")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [d.lower().strip() for d in v]

    @field_validator("reliabilityBySourceType")
    @classmethod
    def _all_types(cls, v: dict[str, str]) -> dict[str, str]:
        missing = set(ALL_SOURCE_TYPES) - set(v)
        if missing:
            raise ValueError(f"missing source types: {sorted(missing)}")
        return v

    @field_validator("reliabilityWeights")
    @classmethod
    def _weights(cls, v: dict[str, float]) -> dict[str, float]:
        if set(v) != {"high", "medium", "low"}:
            raise ValueError("must have exactly the keys high, medium, low")
        for key, weight in v.items():
            if not 0 < weight <= 1:
                raise ValueError(f"{key} must be in (0, 1], got {weight}")
        return v

    def category_for(self, url_or_host: str) -> SourceTypeCategory | None:
        """The `sourceTypeDomains` category whose domain matches this host or a parent of it."""
        host = host_of(url_or_host)
        for category, domains in self.sourceTypeDomains.items():
            if any(host_matches_domain(host, d) for d in domains):
                return category
        return None


class Metro(_Strict):
    id: str
    name: str
    csaCode: str
    states: list[str] = Field(min_length=1)
    places: list[str] = Field(min_length=1)

    @field_validator("states")
    @classmethod
    def _state_codes(cls, v: list[str]) -> list[str]:
        for s in v:
            if not re.fullmatch(r"[A-Z]{2}", s):
                raise ValueError(f"state must be a 2-letter code, got {s!r}")
        return v


class MetroConfig(_Strict):
    metros: list[Metro] = Field(min_length=1)

    @field_validator("metros")
    @classmethod
    def _unique(cls, v: list[Metro]) -> list[Metro]:
        if len({m.id for m in v}) != len(v):
            raise ValueError("metro ids must be unique")
        return v


class FirstPosition(_Strict):
    candidateId: str = Field(min_length=1)
    segment: str = Field(min_length=1)
    companyArchetype: str = Field(min_length=1)
    buyer: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    primaryInterestIds: list[str] = Field(min_length=1)
    searchHints: list[str] = []


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc


def _resolve_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    if isinstance(value, str):
        match = _ENV_REF.match(value.strip())
        if match:
            return os.environ.get(match.group(1)) or None
    return value


def _validate(model: type[M], data: Any, path: Path) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigError(f"{path}: {problems}") from exc


def load_program_config(path: Path) -> ProgramConfig:
    return _validate(ProgramConfig, _read_yaml(path), path)


def load_run_config(path: Path) -> RunConfig:
    return _validate(RunConfig, _resolve_env(_read_yaml(path)), path)


def load_source_policy(path: Path) -> SourcePolicy:
    return _validate(SourcePolicy, _read_yaml(path), path)


def load_metro_config(path: Path) -> MetroConfig:
    return _validate(MetroConfig, _read_yaml(path), path)


def load_first_position(path: Path, known_interest_ids: set[str]) -> FirstPosition:
    position = _validate(FirstPosition, _read_yaml(path), path)
    unknown = [i for i in position.primaryInterestIds if i not in known_interest_ids]
    if unknown:
        raise ConfigError(f"{path}: unknown primaryInterestIds {unknown}")
    return position


@dataclass(frozen=True)
class LoadedConfig:
    config_dir: Path
    run: RunConfig
    source_policy: SourcePolicy
    metros: MetroConfig

    def program_path(self, program: str) -> Path:
        return self.config_dir / "programs" / f"{program}.yaml"

    def metros_in_force(self) -> list[Metro]:
        by_id = {m.id: m for m in self.metros.metros}
        return [by_id[i] for i in self.run.constraints.metroIds]


def load_config(config_dir: Path) -> LoadedConfig:
    config_dir = Path(config_dir)
    cfg = LoadedConfig(
        config_dir=config_dir,
        run=load_run_config(config_dir / "run.yaml"),
        source_policy=load_source_policy(config_dir / "source_policy.yaml"),
        metros=load_metro_config(config_dir / "metros.yaml"),
    )
    known = {m.id for m in cfg.metros.metros}
    missing = [i for i in cfg.run.constraints.metroIds if i not in known]
    if missing:
        raise ConfigError(f"{config_dir / 'run.yaml'}: constraints.metroIds not in metros.yaml: {missing}")
    return cfg
