"""Pydantic records for the traced market discovery pipeline (data-model.md)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MarketRunStatus = Literal[
    "opened", "deliberated", "defined", "graphed", "validated", "linked",
    "searched", "assessed", "verified", "roled", "decided", "reported", "failed",
]

TraceStepStatus = Literal["running", "ok", "failed"]

LayerId = Literal[
    "market_manager", "market_development_controller", "search_research",
    "position_evaluation", "workers",
]

UnresolvedReason = Literal[
    "no information in the objective", "excluded by filter", "repair exhausted",
]

MarketStatusState = Literal[
    "progressing", "needs-attention", "at-risk", "blocked", "awaiting-evidence",
]


class _Doc(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cost(_Doc):
    inputTokens: int | None = None
    outputTokens: int | None = None
    usd: float | None = None


class ToolCall(_Doc):
    kind: Literal["search", "fetch", "model", "store"]
    target: str
    status: str
    detail: str | None = None
    blobId: str | None = None


class Check(_Doc):
    name: str
    status: Literal["pass", "fail"]
    reason: str


class ModelInfo(_Doc):
    name: str
    promptVersion: str
    schema_name: str = Field(alias="schema")
    attempt: int


class UnresolvedItem(_Doc):
    kind: Literal["dimension", "level", "gap"]
    ref: str
    reason: UnresolvedReason
    detail: str | None = None


class MarketStatus(_Doc):
    state: MarketStatusState
    reason: str
    right: str
    ruleFired: str
    decidedAt: str


class FinalPathShortfall(_Doc):
    wanted: int
    found: int
    reason: str


class MarketRun(_Doc):
    marketRunId: str
    programId: str
    objective: dict[str, Any]
    constraintsInForce: dict[str, Any]
    config: dict[str, Any]
    model: str | None = None
    status: MarketRunStatus = "opened"
    stepTimes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    unresolved: list[UnresolvedItem] = Field(default_factory=list)
    marketStatus: MarketStatus | None = None
    unassessed: list[dict[str, str]] = Field(default_factory=list)
    errorStage: str | None = None
    errorMessage: str | None = None
    lastSeq: int = 0
    finalPathShortfall: FinalPathShortfall | None = None


class TraceStep(_Doc):
    marketRunId: str
    seq: int
    stepId: str
    parentStepId: str | None = None
    layer: LayerId
    actor: str
    operation: str
    status: TraceStepStatus = "running"
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    decision: str | None = None
    right: str | None = None
    rationale: str | None = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    model: ModelInfo | None = None
    promptBlobId: str | None = None
    responseBlobId: str | None = None
    toolCalls: list[ToolCall] = Field(default_factory=list)
    cost: Cost = Field(default_factory=Cost)
    latencyMs: int | None = None
    startedAt: str | None = None
    endedAt: str | None = None
    error: str | None = None


class TraceBlob(_Doc):
    blobId: str
    marketRunId: str
    stepId: str
    kind: Literal["prompt", "response", "tool_result"]
    content: str
    truncated: bool = False
    bytes: int = 0
