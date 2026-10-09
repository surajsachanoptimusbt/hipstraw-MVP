"""Evidence result rules per path (research R16), pure functions of company records and settings.

A company is a dict: `proofs` {existence, location, size, interest_signal: True/False/None},
`evidenceConfidence` (0 to 1), `needsVerification`, `conflict`, and `unknowns` (other open items).
The step that applies them runs in Position & Evaluation with right `evaluate_evidence`; each result
stores the grammar's `assessedBy` for its dimension.
"""

from __future__ import annotations

from typing import Any

MINIMUM_PROOFS = ("existence", "location", "size", "interest_signal")


def _has_all_proofs(company: dict[str, Any]) -> bool:
    proofs = company.get("proofs", {})
    return all(proofs.get(p) is True for p in MINIMUM_PROOFS)


def compute_sufficiency(companies: list[dict[str, Any]], settings: dict[str, Any]) -> str:
    total = len(companies)
    full = sum(1 for c in companies if _has_all_proofs(c))
    if full == 0:
        return "insufficient"
    if full == total and total >= int(settings["decisionReadyMinCompanies"]):
        return "decision-ready"
    if full >= float(settings["sufficiencyHalf"]) * total:
        return "sufficient"
    return "partial"


def compute_quality(companies: list[dict[str, Any]], settings: dict[str, Any]) -> str:
    if any(c.get("conflict") for c in companies):
        return "contradictory"
    if not companies:
        return "weak"
    mean = sum(float(c.get("evidenceConfidence", 0.0)) for c in companies) / len(companies)
    if mean < float(settings["qualityMixedFloor"]):
        return "weak"
    if mean < float(settings["qualityStrongFloor"]):
        return "mixed"
    if any(c.get("needsVerification") for c in companies):
        return "strong"
    return "high-confidence"


def compute_critical_unknowns(companies: list[dict[str, Any]]) -> str:
    if not companies:
        return "unidentified"
    if any(not _has_all_proofs(c) for c in companies):
        return "open"
    if any(c.get("unknowns") for c in companies):
        return "reduced"
    return "resolved"
