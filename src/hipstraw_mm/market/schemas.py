"""Model-call schemas for the traced market discovery pipeline (contracts/llm-outputs.md)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeliberationItem(_Strict):
    question: str
    status: Literal["answered", "unresolved"]
    answer: str | None = None
    basis: list[str] = []
    reason: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> DeliberationItem:
        if self.status == "answered":
            if not self.answer:
                raise ValueError("answered item must have a non-empty answer")
            if not self.basis:
                raise ValueError("answered item must have at least one basis excerpt")
        if self.status == "unresolved":
            if self.basis:
                raise ValueError("unresolved item must have empty basis")
            if not self.reason:
                raise ValueError("unresolved item must have a reason")
        return self


class DimensionDeliberation(_Strict):
    dimensionKey: str
    items: list[DeliberationItem]

    @model_validator(mode="after")
    def _at_least_one(self) -> DimensionDeliberation:
        if len(self.items) < 1:
            raise ValueError("must have at least one item")
        return self


class CoverageDimension(_Strict):
    dimensionKey: str
    addressesDimension: bool
    reason: str


class CoverageJudgement(_Strict):
    dimensions: list[CoverageDimension]


class DimensionRepairEntry(_Strict):
    dimensionKey: str
    items: list[DeliberationItem]


class DimensionRepair(_Strict):
    dimensions: list[DimensionRepairEntry]


class ProposedItem(_Strict):
    question: str
    answer: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class ProposedDimension(_Strict):
    dimensionKey: str
    items: list[ProposedItem]


class VicharaProposals(_Strict):
    """Model-proposed hypotheses for dimensions the objective is silent on. Never grounded evidence."""

    dimensions: list[ProposedDimension]


class GraphNode(_Strict):
    label: str
    description: str
    parentLabels: list[str] = []
    metroIds: list[str] = []
    sizeBand: str | None = None
    sourceItemIds: list[str] = []


class CoverageGap(_Strict):
    dimensionKey: str
    covered: bool
    reason: str


class GraphCoverage(_Strict):
    gaps: list[CoverageGap]


class RepairNode(GraphNode):
    level: Literal["segment", "archetype", "problem", "trigger", "buyerRole", "useCase"]


class GraphRepair(_Strict):
    addNodes: list[RepairNode]
    removeNodeIds: list[str] = []

    @model_validator(mode="after")
    def _additive(self) -> GraphRepair:
        if self.removeNodeIds:
            raise ValueError("repair is additive: removeNodeIds must be empty")
        return self


def check_additive(before_nodes: list[dict[str, Any]], after_nodes: list[dict[str, Any]]) -> bool:
    """True if no node of `before_nodes` is missing from `after_nodes`."""
    after_ids = {n.get("nodeId") for n in after_nodes}
    return all(n.get("nodeId") in after_ids for n in before_nodes)


GRAPH_LEVELS = ("segment", "archetype", "problem", "trigger", "buyerRole", "useCase")


class GraphLevelProposal(_Strict):
    level: Literal["segment", "archetype", "problem", "trigger", "buyerRole", "useCase"]
    nodes: list[GraphNode]

    @model_validator(mode="after")
    def _check_level_constraints(self) -> GraphLevelProposal:
        for node in self.nodes:
            if self.level == "segment":
                if not node.metroIds:
                    raise ValueError(f"segment node {node.label!r} must have non-empty metroIds")
            else:
                if node.metroIds:
                    raise ValueError(f"non-segment node {node.label!r} must have empty metroIds")

            if self.level == "archetype":
                if not node.sizeBand:
                    raise ValueError(f"archetype node {node.label!r} must have a sizeBand")
            else:
                if node.sizeBand is not None:
                    raise ValueError(f"non-archetype node {node.label!r} must have null sizeBand")
        return self


class ScoredFactor(_Strict):
    value: float = Field(ge=0.0, le=1.0)
    rationale: str


class BeamCandidateScore(_Strict):
    pathId: str
    relevance: ScoredFactor
    feasibility: ScoredFactor
    timing: ScoredFactor
    cost: ScoredFactor


class BeamScoring(_Strict):
    candidates: list[BeamCandidateScore]

    @model_validator(mode="after")
    def _each_once(self) -> BeamScoring:
        ids = [c.pathId for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("every candidate must appear exactly once")
        return self


class BuyerRole(_Strict):
    pathId: str
    role: str
    authority: Literal["owns_budget", "approves", "uses", "influences"]
    evidenceIds: list[str] = Field(min_length=1)
    rationale: str


class BuyerRoles(_Strict):
    roles: list[BuyerRole]


class LinkEntry(_Strict):
    fromNodeId: str
    toNodeId: str
    rationale: str
    linkConfidence: float = Field(ge=0.0, le=1.0)


class LinkVerification(_Strict):
    links: list[LinkEntry]


class DimensionAssessment(_Strict):
    dimensionKey: Literal[
        "value_proposition",
        "demand_signals",
        "adoption_readiness",
        "economics",
        "alternatives",
        "risks",
        "dependencies",
    ]
    state: str
    rationale: str
    label: Literal["hypothesis"]


class PathAssessment(_Strict):
    dimensions: list[DimensionAssessment]
