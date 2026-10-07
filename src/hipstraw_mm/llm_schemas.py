"""The five structured-output schemas (contracts/llm-outputs.md).

Every field is required (nullable where the contract allows null) and extra fields are forbidden, as
OpenAI strict mode needs. Count limits are enforced by the system after parsing, not in the schema.
There is no field for a person, an email address, or a phone number (FR-018).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlannedQuery(_Strict):
    query: str
    purpose: str


class QueryPlan(_Strict):
    queries: list[PlannedQuery]


class ListedCompany(_Strict):
    name: str
    linkId: str | None
    excerpt: str


class ListingExtraction(_Strict):
    companies: list[ListedCompany]


class HomepageIdentity(_Strict):
    isCompanyHomepage: bool
    name: str | None
    excerpt: str | None


EvidenceClaimField = Literal[
    "hq",
    "employees",
    "revenue",
    "parent",
    "fit_buyer",
    "fit_problem",
    "fit_trigger",
    "signal_pain",
    "signal_exploration",
]


class EvidenceClaim(_Strict):
    claimId: str
    claimField: EvidenceClaimField
    claimValue: str
    sourceId: str
    excerpt: str


class EvidenceFitClaim(_Strict):
    aspect: Literal["buyer", "problem", "trigger"]
    statement: str
    primaryInterestIds: list[str]
    claimIds: list[str]


class EvidenceInterestSignal(_Strict):
    kind: Literal["pain", "exploration"]
    statement: str
    claimIds: list[str]


class CompanyEvidence(_Strict):
    claims: list[EvidenceClaim]
    fitClaims: list[EvidenceFitClaim]
    interestSignals: list[EvidenceInterestSignal]
    falsifier: str


class ReviewJudgement(_Strict):
    falsifierMet: bool
    fitHolds: bool
    citedEvidenceIds: list[str]
    reason: str


ALL_SCHEMAS: dict[str, type[BaseModel]] = {
    "QueryPlan": QueryPlan,
    "ListingExtraction": ListingExtraction,
    "HomepageIdentity": HomepageIdentity,
    "CompanyEvidence": CompanyEvidence,
    "ReviewJudgement": ReviewJudgement,
}
