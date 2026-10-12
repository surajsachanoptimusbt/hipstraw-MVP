"""Market Position: the Market Manager's canonical, versioned belief about one micro market.

Position & Evaluation recommends; the Market Manager reviews and commits (Market Manager spec 1.4, 4.3;
P&E spec 2.3). `commit_record` builds the canonical, versioned record with lineage to the evaluation
case. `build_market_position` builds the fuller view the reviewer reads: value proposition, economics,
risks, evidence, open gaps, and the target companies found.
"""

from __future__ import annotations

import hashlib
from typing import Any

from hipstraw_mm.market.evaluation import RECOMMENDATION_SUPPORTS, economic_midpoint, label_tokens

Doc = dict[str, Any]

# the seven per-path assessment dimensions, in the order a reviewer reads them
NARRATIVE = ("value_proposition", "demand_signals", "adoption_readiness", "economics",
             "alternatives", "risks", "dependencies")

# the Market Manager's path decision -> canonical status and next action
_STANCE = {
    "pursue": ("Pursue", "Advance this market to selective testing."),
    "needs more evidence": ("Needs more evidence", "Commission targeted research to close the open gaps."),
    "drop": ("Drop", "Release capacity; no verified company and no gap more evidence can fill."),
}


def position_key(program_id: str, labels: list[str]) -> str:
    digest = hashlib.sha256(" ".join(sorted(label_tokens(labels))).encode("utf-8")).hexdigest()[:10]
    return f"{program_id}__mm_{digest}"


def trajectory(prior: Doc | None, status: str, confidence: str) -> str:
    """Direction relative to the prior canonical version: new, up, down, or flat."""
    if prior is None:
        return "new"
    order = {"Drop": 0, "Needs more evidence": 1, "Pursue": 2}
    bands = {"Low": 0, "Medium": 1, "High": 2}
    before = (order.get(prior.get("status", ""), 1), bands.get(prior.get("confidence", "Low"), 0))
    after = (order.get(status, 1), bands.get(confidence, 0))
    return "up" if after > before else "down" if after < before else "flat"


def commit_record(run: Doc, path: Doc, case: Doc | None, decision: Doc, prior: Doc | None, at: str) -> Doc:
    """The canonical Market Position version the Market Manager commits for one path (4.3 fields)."""
    status, action = _STANCE.get(decision["decision"], ("Needs more evidence", "Review this path."))
    labels = path.get("nodeLabels", [])
    rec = (case or {}).get("recommendation") or {}
    confidence = ((case or {}).get("confidence") or {}).get("band", "Low")
    accepted = rec.get("supportsDecision") == decision["decision"] if rec else None
    requirements = (case or {}).get("researchRequirements", [])
    economics = (case or {}).get("economics")
    assessment = {a["dimensionKey"]: a for a in path.get("assessment", [])}
    return {
        "positionKey": (prior or {}).get("positionKey") or position_key(run["programId"], labels),
        "version": int((prior or {}).get("version", 0)) + 1,
        "programId": run["programId"],
        "marketRunId": run["marketRunId"],
        "pathId": path["pathId"],
        "labels": labels,
        "status": status,
        "judgment": f"{status}: {' > '.join(labels)}",
        "reasons": [decision.get("reason", "")] + ([rec["rationale"]] if rec.get("rationale") else []),
        "confidence": confidence,
        "limitingFactors": ((case or {}).get("confidence") or {}).get("limitingFactors", []),
        "contradictions": (path.get("researchPacket") or {}).get("contradictions", []),
        "unknowns": [r["evidenceGap"] for r in requirements],
        "trajectory": trajectory(prior, status, confidence),
        "materiality": {
            "valuePoolUsdLow": (economics or {}).get("valuePoolUsdLow"),
            "valuePoolUsdHigh": (economics or {}).get("valuePoolUsdHigh"),
            "valueMid": economic_midpoint(economics),
            "basis": (economics or {}).get("unit"),
            "label": "hypothesis",
        },
        "learningPriority": requirements[0]["evidenceGap"] if requirements else None,
        "direction": action,
        "valueProposition": assessment.get("value_proposition", {}).get("rationale", ""),
        "recommendationReviewed": rec.get("recommendation"),
        "recommendationAccepted": accepted,
        "reviewNote": None if accepted in (True, None) else (
            f"Market Manager rule {decision.get('ruleFired')} decided '{decision['decision']}'; the "
            f"Position & Evaluation recommendation '{rec.get('recommendation')}' supports "
            f"'{rec.get('supportsDecision')}' and was not accepted."
        ),
        "decisionRule": decision.get("ruleFired"),
        "evidenceLineage": {
            "evaluationCaseId": (case or {}).get("caseId"),
            "childRunId": path.get("childRunId"),
            "priorVersion": f"{prior['positionKey']}__v{prior['version']}" if prior else None,
        },
        "committedAt": at,
        "right": "commit_position",
    }


def build_market_position(path: Doc, companies_on_path: list[Doc], decision: Doc,
                          case: Doc | None = None, canonical: Doc | None = None) -> Doc:
    """The Market Position view for one final path, read by the viewer and the report."""
    assessment = {a["dimensionKey"]: a for a in path.get("assessment", [])}
    evidence = path.get("evidenceStates") or {}
    packet = path.get("researchPacket") or {}
    disposition, action = _STANCE.get(decision.get("decision", ""), ("Needs attention", "Review this path."))
    included = [c for c in companies_on_path if c.get("disposition") == "include"]
    needs_v = [c for c in companies_on_path if c.get("disposition") == "needs_verification"]
    confidence = (case or {}).get("confidence") or {}
    rec = (case or {}).get("recommendation") or {}
    economics = (case or {}).get("economics")
    return {
        "pathId": path["pathId"],
        "pathLabels": path.get("nodeLabels", []),
        "disposition": disposition,
        "recommendedAction": action,
        "decision": decision.get("decision"),
        "ruleFired": decision.get("ruleFired"),
        "reason": decision.get("reason"),
        "confidence": confidence.get("band", "Low"),
        "limitingFactors": confidence.get("limitingFactors", []),
        "recommendation": rec.get("recommendation"),
        "recommendationRationale": rec.get("rationale"),
        "recommendationAccepted": (canonical or {}).get("recommendationAccepted"),
        "reviewNote": (canonical or {}).get("reviewNote"),
        "positionKey": (canonical or {}).get("positionKey"),
        "version": (canonical or {}).get("version"),
        "trajectory": (canonical or {}).get("trajectory"),
        "headline": _headline(path.get("nodeLabels", []), disposition, len(included), evidence),
        "valueProposition": assessment.get("value_proposition", {}).get("rationale", ""),
        "economics": assessment.get("economics", {}).get("rationale", ""),
        "economicEstimate": economics,
        "risks": assessment.get("risks", {}).get("rationale", ""),
        "narrative": [
            {"dimensionKey": k, "state": assessment.get(k, {}).get("state", "unassessed"),
             "rationale": assessment.get(k, {}).get("rationale", ""), "label": "hypothesis"}
            for k in NARRATIVE
        ],
        "evidence": {k: evidence.get(k) for k in ("sufficiency", "quality", "criticalUnknowns")},
        "openGaps": packet.get("gaps", []),
        "researchRequirements": (case or {}).get("researchRequirements", []),
        "targetCompanies": [
            {"name": c["name"], "domain": c.get("domain"), "disposition": c.get("disposition"),
             "evidenceConfidence": c.get("evidenceConfidence")}
            for c in [*included, *needs_v]
        ],
        "companiesIncluded": len(included),
        "companiesNeedingVerification": len(needs_v),
    }


def _headline(labels: list[str], disposition: str, included: int, evidence: Doc) -> str:
    where = " > ".join(labels) if labels else "this path"
    return (
        f"{disposition}: {where}. {included} verified compan{'y' if included == 1 else 'ies'}, "
        f"{evidence.get('sufficiency') or 'insufficient'} evidence ({evidence.get('quality') or 'no'} quality)."
    )


def companies_for_path(path_id: str, market_companies: list[Doc]) -> list[Doc]:
    """The market-company records that link to this path, with the path's own disposition."""
    out: list[Doc] = []
    for c in market_companies:
        for link in c.get("links", []):
            if link.get("pathId") == path_id:
                out.append({**c, "disposition": link.get("disposition")})
                break
    return out


__all__ = ["RECOMMENDATION_SUPPORTS", "build_market_position", "commit_record", "companies_for_path",
           "position_key", "trajectory"]
