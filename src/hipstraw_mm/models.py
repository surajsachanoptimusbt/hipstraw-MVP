"""Domain models and identity helpers (data-model.md)."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    created = "created"
    discovered = "discovered"
    verified = "verified"
    reviewed = "reviewed"
    reported = "reported"
    failed = "failed"


ClaimField = Literal[
    "origin",
    "existence",
    "hq",
    "employees",
    "revenue",
    "parent",
    "parent_employees",
    "parent_revenue",
    "fit_buyer",
    "fit_problem",
    "fit_trigger",
    "signal_pain",
    "signal_exploration",
]
SourceType = Literal["registry", "news", "company_site", "job_board", "directory"]
Reliability = Literal["high", "medium", "low"]
CheckStatus = Literal["pass", "fail"]
CheckReason = Literal[
    "not_retrievable",
    "robots_disallowed",
    "denylisted",
    "excerpt_not_found",
    "value_not_in_excerpt",
    "excerpt_too_long",
    "contains_contact_data",
]
IdentifierStatus = Literal["resolves", "unreadable", "fails", "no_website"]
OriginKind = Literal["listing_link", "profile_hop", "direct_homepage", "registry_only"]
Disposition = Literal["include", "exclude", "needs_verification"]
RuleName = Literal["existence", "hq", "size", "large_enterprise", "interest_signal"]
RuleOutcome = Literal["pass", "fail", "unknown", "conflict"]


class Doc(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdLabel(Doc):
    id: str
    label: str


class Program(Doc):
    programId: str
    name: str
    objective: str
    sourceUrl: str
    experimentContexts: list[IdLabel]
    primaryInterests: list[IdLabel]
    defaultConstraints: dict[str, int | list[str]]


class MarketCandidate(Doc):
    candidateId: str
    programId: str
    experimentContextId: str
    label: str
    origin: Literal["program_experiment_context"] = "program_experiment_context"


class Position(Doc):
    segment: str
    companyArchetype: str
    buyer: str
    problem: str
    trigger: str
    primaryInterestIds: list[str] = Field(min_length=1)
    searchHints: list[str] = []


class MetroRef(Doc):
    id: str
    csaCode: str
    name: str


class ConstraintsInForce(Doc):
    maxEmployees: int
    maxRevenueUsd: int
    metros: list[MetroRef]
    largeEnterpriseParents: list[str] = []


class Run(Doc):
    runId: str
    programId: str
    candidateId: str
    position: Position
    constraintsInForce: ConstraintsInForce
    budgets: dict[str, int]
    model: str | None  # None when LLM_MODEL was unset at `position`; model steps require it
    status: RunStatus = RunStatus.created
    stepTimes: dict[str, str] = {}
    counts: dict[str, int] = {}
    shortfallReason: str | None = None
    errorStep: str | None = None
    errorMessage: str | None = None


class EvidenceCheck(Doc):
    status: CheckStatus
    reason: CheckReason | None = None


class Evidence(Doc):
    evidenceId: str
    runId: str
    companyRecordId: str | None
    claimField: ClaimField
    claimValue: str
    url: str
    sourceType: SourceType
    reliability: Reliability
    publishedAt: str | None = None
    fetchedAt: str
    excerpt: str
    contentSha256: str
    check: EvidenceCheck


class OriginMatch(Doc):
    """Discovery ranking inputs after the system's location check (research R19, FR-022)."""

    location: str | None
    metroMatch: Literal["in", "out", "unknown"]
    positionMatch: Literal["strong", "partial", "weak"]


class Origin(Doc):
    kind: OriginKind
    searchQuery: str | None
    resultUrl: str
    listingEvidenceId: str | None
    profileUrl: str | None = None
    match: OriginMatch | None = None


class IdentifierCheck(Doc):
    status: IdentifierStatus
    httpStatus: int | None = None
    finalUrl: str | None = None
    failReason: str | None = None  # the fetcher's reason when the website was not read
    nameMatchesDomain: bool | None = None  # None for registry-only companies (research R4)
    checkedAt: str


class Hq(Doc):
    city: str | None = None
    state: str | None = None
    status: Literal["met", "not_met", "conflict", "unknown"] = "unknown"
    evidenceIds: list[str] = []


class SizeSignal(Doc):
    kind: Literal["employees", "revenue"]
    low: float | None
    high: float | None
    evidenceId: str


class Size(Doc):
    signals: list[SizeSignal] = []
    status: Literal["under", "over", "conflict", "unknown"] = "unknown"


class Parent(Doc):
    """The company's parent (research R6). A record without a passing parent claim has `parent: null`."""

    name: str
    evidenceIds: list[str] = []
    status: Literal["small", "large", "unknown_size"]


class FitClaim(Doc):
    aspect: Literal["buyer", "problem", "trigger"]
    statement: str
    primaryInterestIds: list[str] = Field(min_length=1)
    evidenceIds: list[str] = Field(min_length=1)


class InterestSignal(Doc):
    kind: Literal["pain", "exploration"]
    statement: str
    evidenceIds: list[str] = Field(min_length=1)


class Unknown(Doc):
    field: str
    reason: str


class Confidence(Doc):
    value: float = Field(ge=0, le=1)
    band: Literal["High", "Medium", "Low"]


class CompanyRecord(Doc):
    companyRecordId: str
    runId: str
    candidateId: str
    name: str
    domain: str | None
    origin: Origin
    identifierCheck: IdentifierCheck | None = None
    existenceEvidenceId: str | None = None
    hq: Hq | None = None
    size: Size | None = None
    parent: Parent | None = None
    fitClaims: list[FitClaim] = []
    interestSignals: list[InterestSignal] = []
    unknowns: list[Unknown] = []
    falsifier: str | None = None
    confidence: Confidence | None = None
    # Findings are never canonical; only Review (reviewDecisions) dispositions a company (FR-011).
    status: Literal["finding"] = "finding"


class RuleResult(Doc):
    rule: RuleName
    outcome: RuleOutcome
    evidenceIds: list[str] = []


class Judgement(Doc):
    falsifierMet: bool
    fitHolds: bool
    citedEvidenceIds: list[str]
    reason: str
    model: str


class ReviewDecision(Doc):
    companyRecordId: str
    disposition: Disposition
    reason: str = Field(min_length=1)
    ruleResults: list[RuleResult]
    judgement: Judgement | None
    # The record's passing evidence, attached by the system (not the model); an include needs at least one.
    evidenceIds: list[str] = []
    reviewer: str
    reviewedAt: str


class BaselineCompany(Doc):
    companyRecordId: str
    name: str
    domain: str | None
    disposition: Disposition


class PositionBaseline(Doc):
    runId: str
    programId: str
    candidateId: str
    position: Position
    constraintsInForce: ConstraintsInForce
    companies: list[BaselineCompany]
    baselineAt: str


class DemoReport(Doc):
    runId: str
    path: str
    sha256: str
    counts: dict[str, int]
    generatedAt: str


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PUNCT = re.compile(r"[^\w\s]")
_LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
    "co",
    "company",
    "lp",
    "llp",
    "plc",
}


def new_run_id(now: datetime) -> str:
    return f"run_{now:%Y%m%dT%H%M%S}"


def host_of(url_or_host: str) -> str:
    """Lowercase host without port, from a URL or a bare host."""
    if "://" in url_or_host:
        host = urlparse(url_or_host).hostname or ""
    else:
        host = url_or_host.split("/", 1)[0].split(":", 1)[0]
    return host.lower().rstrip(".")


def site_host(url_or_host: str) -> str:
    """Host with a leading `www.` removed."""
    host = host_of(url_or_host)
    return host[4:] if host.startswith("www.") else host


def domain_key(url_or_host: str) -> str:
    """`www.Acme.test` -> `acme-test` (data-model.md)."""
    return site_host(url_or_host).replace(".", "-")


def registry_key(name: str) -> str:
    """`Zeta Holdings LLC` -> `registry-zeta-holdings-llc` (data-model.md)."""
    return "registry-" + _NON_ALNUM.sub("-", name.lower()).strip("-")


def company_record_id(run_id: str, key: str) -> str:
    return f"{run_id}__{key}"


def host_matches_domain(host: str, domain: str) -> bool:
    """True when `host` is `domain` or one of its subdomains (dot boundary, so no look-alikes)."""
    host, domain = host.lower(), domain.lower().lstrip(".")
    return host == domain or host.endswith("." + domain)


def is_denylisted(url_or_host: str, denylist: list[str]) -> bool:
    host = host_of(url_or_host)
    return any(host_matches_domain(host, d) for d in denylist)


def same_company_or_subdomain(origin_url: str, target_url: str) -> bool:
    """FR-008 redirect rule: the target stays on the origin's company key or one of its subdomains."""
    return host_matches_domain(site_host(target_url), site_host(origin_url))


def normalize_company_name(name: str) -> str:
    """Merge-rule normalization: casefold, drop punctuation, collapse spaces, drop one legal suffix."""
    words = _PUNCT.sub(" ", name.casefold()).split()
    if len(words) > 1 and words[-1] in _LEGAL_SUFFIXES:
        words = words[:-1]
    return " ".join(words)
