"""Loads config/agents.yaml: each agent's innate capabilities, skills, and tools."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Capability(_Strict):
    id: str
    name: str
    behavior: str
    plain: str | None = None
    operations: list[str] = []
    playbook: list[str] = []


class Skill(_Strict):
    id: str
    name: str
    kind: Literal["model", "rule", "mixed"]
    version: str
    purpose: str
    plain: str | None = None
    operations: list[str] = []
    promptVersions: list[str] = []
    playbook: list[str] = []


class Tool(_Strict):
    id: str
    name: str
    purpose: str
    plain: str | None = None
    toolCallKinds: list[str] = []


class Agent(_Strict):
    id: str
    name: str
    title: str | None = None
    role: str | None = None
    layer: str
    centralQuestion: str
    knowledge: list[str] = []
    innateCapabilities: list[Capability]
    skills: list[Skill]
    tools: list[Tool]


class Term(_Strict):
    term: str
    playbookTerm: str
    meaning: str
    source: str


def _owners(agent: Agent) -> list[Capability | Skill]:
    return [*agent.innateCapabilities, *agent.skills]


class AgentRegistry(_Strict):
    version: int
    agents: list[Agent]
    glossary: list[Term] = []

    @model_validator(mode="after")
    def _operations_unique(self) -> AgentRegistry:
        seen: dict[str, str] = {}
        for agent in self.agents:
            for owner in _owners(agent):
                for op in owner.operations:
                    if op in seen:
                        raise ValueError(f"operation {op!r} is claimed by both {seen[op]} and {agent.id}.{owner.id}")
                    seen[op] = f"{agent.id}.{owner.id}"
        return self

    def operation_owner(self, operation: str) -> tuple[str, str] | None:
        """(agent id, capability or skill id) that a trace operation belongs to."""
        for agent in self.agents:
            for owner in _owners(agent):
                if operation in owner.operations:
                    return agent.id, owner.id
        return None


def load_agent_registry(config_dir: Path = Path("config")) -> AgentRegistry:
    with open(config_dir / "agents.yaml", encoding="utf-8") as f:
        return AgentRegistry.model_validate(yaml.safe_load(f))
