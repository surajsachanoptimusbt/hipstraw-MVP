"""Cases, ledger events and the platform's offerings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Offering = Literal["shadow_launch", "day_zero", "campaign"]
State = Literal["agent_working", "waiting_review", "approved", "returned"]
WaitingOn = Literal["agent", "reviewer", "customer", "people"]
Stage = Literal["ingest", "review", "position", "recommend", "workflow", "approval"]
Actor = Literal["agent", "customer", "reviewer", "system"]
Kind = Literal["request", "step", "finding", "pick", "gate", "decision"]

# The pipeline (the Nov 6 architecture): the agent runs the first five stages; a person runs the sixth.
STAGES: list[tuple[Stage, str, str]] = [
    ("ingest", "Ingest", "Read the request"),
    ("review", "Review", "Judge the evidence against the rubric"),
    ("position", "Position", "Where each hypothesis stands"),
    ("recommend", "Recommend", "The playbook picks the Lines"),
    ("workflow", "Workflow", "Gated Moves, in order"),
    ("approval", "Human approval", "A reviewer approves the plan"),
]

OFFERINGS: list[dict[str, Any]] = [
    {"id": "shadow_launch", "name": "Shadow launch", "status": "live",
     "summary": "Validate demand for a recommended market before launch: the evidence judged, the Lines picked, "
                "the Moves to run", "caseTypes": ["Market validation"]},
    {"id": "day_zero", "name": "Day Zero launch", "status": "preview",
     "summary": "From T-30 to launch day and after: what has to be done at each stage, and what has been done",
     "caseTypes": ["Launch readiness"]},
    {"id": "campaign", "name": "Campaign management", "status": "preview",
     "summary": "Campaign strategy and readiness tested channel by channel, before and during launch",
     "caseTypes": ["Campaign review"]},
]


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Approval(_Config):
    action: Literal["approve", "return"]
    actor: str
    role: str
    at: str
    note: str
    payloadHash: str


class Case(_Config):
    id: str
    offering: Offering
    caseType: str
    company: str
    market: str
    state: State
    waitingOn: WaitingOn
    stage: Stage
    createdAt: str
    updatedAt: str
    requestedBy: str
    thesis: dict[str, Any]  # the request as submitted (a market thesis)
    recommendation: dict[str, Any] | None = None  # the playbook's plan, once the agent has made it
    payloadHash: str | None = None
    approval: Approval | None = None


class Event(_Config):
    seq: int
    caseId: str
    at: str
    stage: Stage
    actor: Actor
    who: str
    kind: Kind
    title: str
    detail: str = ""
    data: dict[str, Any] = {}
    prevHash: str
    hash: str
