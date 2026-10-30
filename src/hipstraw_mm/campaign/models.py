"""Campaign records (specs/004-campaign-readiness-g0/data-model.md).

No record has a score, probability, likelihood or forecast field: a Position is evidence-linked state,
never a prediction that the campaign will succeed (HA HR03; tests/unit/test_campaign_no_score.py).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

AssetKind = Literal["landing_page", "ad_copy", "email_copy", "creative", "brief", "other"]
EvidenceKind = Literal["asset", "metric", "page_read", "evidence_response", "observation"]
EvidenceSource = Literal["customer_submission", "mandate_url", "metrics_export"]
VerificationState = Literal["unverified", "reported", "observed", "verified", "stale"]
AccessClass = Literal["D2", "D3"]
Area = Literal["strategy", "readiness"]
ItemKind = Literal["claim", "assumption", "blocker", "unknown", "hypothesis", "observation"]
EffectClass = Literal["E0", "E1", "E2", "E3"]
SnapshotState = Literal["proposed", "accepted", "superseded"]
LineRunState = Literal["opened", "staged", "completed", "abandoned"]
ExecutionStatus = Literal["succeeded", "failed", "blocked"]
DeviationType = Literal["skipped", "added", "reordered", "stopped"]
ReviewState = Literal["requested", "gathering", "drafted", "validated", "accepted", "rejected", "failed"]
FindingKind = Literal[
    "blocker", "gap", "contested", "stale_metric", "assumption", "proposal", "test_plan", "delta", "escalation",
    "unknown", "rubric", "standard",
]
Verdict = Literal["met", "partly", "not_met", "unknown"]
FindingState = Literal["pending", "accepted", "rejected", "corrected"]
TestPlanState = Literal[
    "draft", "eligible", "awaiting_approval", "approved", "rejected", "running", "evaluated", "failed", "cancelled",
]

# Item states by kind (data-model.md). A claim from the customer or a model starts no higher than `reported`.
ITEM_STATES: dict[str, tuple[str, ...]] = {
    "claim": ("unverified", "reported", "contested", "observed", "verified"),
    "assumption": ("open", "awaiting_evidence", "supported", "not_supported"),
    "blocker": ("open", "cleared"),
    "unknown": ("open", "resolved"),
    "hypothesis": ("proposed", "planned", "running", "supported", "not_supported", "inconclusive"),
    "observation": ("observed", "stale"),
}
CLAIM_RANK = {state: rank for rank, state in enumerate(("unverified", "reported", "contested", "observed", "verified"))}


def content_hash(content: str | dict[str, Any]) -> str:
    text = content if isinstance(content, str) else json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- Launch and Mandate (C1) -------------------------------------------------------------------------


class Launch(Record):
    launchId: str
    tenant: str = "default"
    owner: str
    market: str
    productName: str
    createdAt: str


class Product(Record):
    name: str
    description: str
    website: str | None = None
    priceNote: str | None = None


class Audience(Record):
    description: str
    segments: list[str] = []


class Objective(Record):
    statement: str
    successMeasure: str | None = None


class Budget(Record):
    amount: float
    currency: str


class Strategy(Record):
    channels: list[str] = []
    message: str
    offer: str | None = None
    budget: Budget | None = None


class Asset(Record):
    assetId: str
    kind: AssetKind
    channel: str | None = None
    url: str | None = None
    text: str | None = None
    # The parts a channel's rules check, e.g. an email's subject, preheader and footer (config/campaign/channels.yaml).
    fields: dict[str, str] = {}
    readyDate: date | None = None


class ChannelPlan(Record):
    """One channel as the Sponsor plans it (Oct 30 meeting: a campaign starts by naming its channels): who it
    reaches, its budget and success measure, and the setup facts that channel's rules check."""

    channel: str
    audience: str | None = None
    budget: Budget | None = None
    successMeasure: str | None = None
    setup: dict[str, Any] = {}


class MetricsFile(Record):
    path: str
    sha256: str


class Mandate(Record):
    """Immutable per version; a change is a new, complete version."""

    launchId: str
    version: int
    createdAt: str
    createdBy: str
    product: Product
    audience: Audience
    market: str
    dayZero: date
    objective: Objective
    strategy: Strategy
    authorizedChannels: list[str] = []
    approver: str | None = None
    trackingPlan: str | None = None
    assets: list[Asset] = []
    channelPlans: list[ChannelPlan] = []
    metricsFile: MetricsFile | None = None


# -- Evidence (C2) -------------------------------------------------------------------------------------


class Provenance(Record):
    by: str
    method: str
    moveId: str | None = None


class MetricFields(Record):
    metric: str
    value: float
    unit: str | None = None
    windowStart: str | None = None
    windowEnd: str | None = None
    denominator: str | None = None
    definition: str | None = None


class EvidenceRecord(Record):
    """Immutable. Raw values are never rewritten; a later check adds a new record or a Position change."""

    evidenceId: str
    launchId: str
    kind: EvidenceKind
    source: EvidenceSource
    sourceRef: str
    capturedAt: str
    effectiveAt: str | None = None
    provenance: Provenance
    verificationState: VerificationState
    uncertainty: str = ""
    contentHash: str
    content: str | dict[str, Any]
    accessClass: AccessClass
    metric: MetricFields | None = None


# -- Campaign Position (C3) ----------------------------------------------------------------------------


class ModelUse(Record):
    configured: str | None = None
    served: str | None = None


class MechanismStamp(Record):
    """C8: what produced a Review or a snapshot, so a later mechanism change stays visible in history."""

    codeVersion: str
    gitCommit: str | None = None
    repertoireVersion: str | None = None
    criteriaVersion: str | None = None
    routerVersion: str | None = None
    rubricVersion: str | None = None
    promptVersions: list[str] = []
    models: list[ModelUse] = []


class PositionItem(Record):
    itemId: str
    kind: ItemKind
    area: Area
    text: str
    state: str
    core: bool = False
    evidenceRefs: list[str] = []
    setBy: str
    note: str | None = None
    # A stable source key, e.g. the readiness criterion `RC01`, so a later run clears the same blocker.
    key: str | None = None
    channel: str | None = None

    @model_validator(mode="after")
    def _state_fits_kind(self) -> PositionItem:
        if self.state not in ITEM_STATES[self.kind]:
            raise ValueError(f"{self.itemId}: state {self.state!r} is not a {self.kind} state {ITEM_STATES[self.kind]}")
        if self.core and self.kind != "assumption":
            raise ValueError(f"{self.itemId}: only assumptions can be core")
        return self


class PositionSnapshot(Record):
    positionId: str
    launchId: str
    version: int
    state: SnapshotState
    baseVersion: int | None = None
    evidenceCutoff: str
    createdAt: str
    origin: str
    mechanismStamp: MechanismStamp
    items: list[PositionItem]


# -- Tactic record (C10) -------------------------------------------------------------------------------


class LineChoice(Record):
    lineId: str
    version: int
    reasons: list[str]


class LineRecommendation(Record):
    positionVersion: int
    facts: dict[str, Any]
    eligible: list[LineChoice]
    excluded: list[LineChoice]


class LineRun(Record):
    lineRunId: str
    launchId: str
    lineId: str
    lineVersion: int
    repertoireVersion: str
    chosenBy: str
    chosenRole: str
    reason: str
    chosenAt: str
    recommendation: LineRecommendation
    basePositionVersion: int
    plannedStages: list[list[str]]
    nextStage: int = 0
    state: LineRunState = "opened"
    reviewId: str | None = None


class Transition(Record):
    itemId: str
    fromState: str | None
    toState: str
    evidenceRefs: list[str] = []


class MoveExecution(Record):
    executionId: str
    lineRunId: str
    launchId: str
    stageIndex: int
    moveId: str
    moveVersion: int
    effectClasses: list[EffectClass]
    status: ExecutionStatus
    gate: str
    startedAt: str
    endedAt: str
    transitions: list[Transition] = []
    newItems: list[PositionItem] = []
    produced: list[str] = []
    proposals: list[dict[str, Any]] = []
    models: list[str] = []  # served model names, for the mechanism stamp
    note: str | None = None
    error: str | None = None
    traceStepId: str | None = None


class Deviation(Record):
    deviationId: str
    lineRunId: str
    launchId: str
    beforeStage: int
    type: DeviationType
    moveId: str | None = None
    by: str
    role: str
    reason: str
    at: str


# -- Review (C4) and corrections (C9) ------------------------------------------------------------------


class Quote(Record):
    """Words copied exactly from one evidence record."""

    evidenceId: str
    quote: str


class Finding(Record):
    findingId: str
    area: Area
    kind: FindingKind
    text: str
    currentText: str
    evidenceRefs: list[str] = []
    itemRefs: list[str] = []
    uncertainty: str
    sourceMove: str | None = None
    isProposal: bool = False
    reviewState: FindingState = "pending"
    # Rubric findings (Session 2026-10-29): the question, its verdict, the quotes behind it, and the fix.
    questionId: str | None = None
    verdict: Verdict | None = None
    quotes: list[Quote] = []
    fix: str | None = None
    channel: str | None = None


class ReviewRun(Record):
    reviewId: str
    launchId: str
    lineRunId: str
    question: str
    basePositionVersion: int
    evidenceCutoff: str
    state: ReviewState
    findings: list[Finding] = []
    proposedItems: list[PositionItem] = []
    scopeStatement: str
    mechanismStamp: MechanismStamp
    createdAt: str
    validatedBy: str | None = None
    validatedAt: str | None = None
    decidedBy: str | None = None
    decidedAt: str | None = None
    decisionReason: str | None = None
    committedPositionVersion: int | None = None


class Correction(Record):
    correctionId: str
    reviewId: str
    launchId: str
    findingId: str
    action: Literal["accept", "reject", "correct"]
    originalText: str
    newText: str | None = None
    originalVerdict: Verdict | None = None
    newVerdict: Verdict | None = None
    by: str
    role: str
    reason: str
    at: str


# -- Audit (C5) and supporting records -----------------------------------------------------------------


class AuditEvent(Record):
    eventId: str
    launchId: str | None
    at: str
    actor: str
    role: str
    action: str
    right: str | None = None
    outcome: Literal["allowed", "refused"] = "allowed"
    beforeRef: str | None = None
    afterRef: str | None = None
    reason: str | None = None
    correlationId: str


class TestPlan(Record):
    """Only `draft` is reachable in G0's first slice: no approval path exists, so no test is dispatched."""

    __test__ = False  # not a pytest test class

    testPlanId: str
    launchId: str
    lineRunId: str
    hypothesisItemId: str
    hypothesis: str
    cohort: str
    method: str
    successCriteria: str
    stopRule: str
    budget: Budget | None = None
    risks: list[str] = []
    state: TestPlanState = "draft"


class EvidenceRequest(Record):
    requestId: str
    launchId: str
    assumptionItemId: str
    question: str
    requestedFrom: str
    state: Literal["open", "answered"] = "open"
    createdAt: str


class Escalation(Record):
    escalationId: str
    launchId: str
    itemRefs: list[str]
    reason: str
    to: str
    createdAt: str


class Delta(Record):
    """Expected versus observed change. Never causal proof (HA HR03)."""

    deltaId: str
    launchId: str
    hypothesisItemId: str
    expected: str
    observedEvidenceRefs: list[str]
    attributionNotes: str
    causal: Literal[False] = False
    createdAt: str


class ReportRecord(Record):
    reportId: str
    launchId: str
    positionVersion: int
    renderedAt: str
    path: str
    sha256: str
