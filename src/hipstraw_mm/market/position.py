"""Market Position per final path: what the Market Manager concludes, for the viewer and report.

A Market Position is a synthesis of already-stored, explainable data (the path's seven assessments,
its evidence states, its companies, and the Market Manager's rule decision). It is not a new model
call, so every field traces back to a record (Constitution VI). It replaces the raw "decision" in the
UI with the fuller picture the reviewer asked for: value proposition, economics, risks, evidence
strength, open gaps, and the target companies found.
"""

from __future__ import annotations

from typing import Any

Doc = dict[str, Any]

# the seven per-path assessment dimensions, in the order a reviewer reads them
NARRATIVE = ("value_proposition", "demand_signals", "adoption_readiness", "economics",
             "alternatives", "risks", "dependencies")

# evidence quality band -> how strongly to hold the position
_CONFIDENCE = {
    "high-confidence": "High", "strong": "High", "mixed": "Medium",
    "weak": "Low", "contradictory": "Low", "stale": "Low",
}
# the path decision -> a Market Position disposition and next action
_STANCE = {
    "pursue": ("Pursue", "Advance this market to selective testing."),
    "needs more evidence": ("Needs more evidence", "Commission targeted research to close the open gaps."),
    "drop": ("Drop", "Release capacity; no verified company and no gap more evidence can fill."),
}


def build_market_position(path: Doc, companies_on_path: list[Doc], decision: Doc) -> Doc:
    """Synthesize one path's Market Position from its assessment, evidence, companies and decision."""
    assessment = {a["dimensionKey"]: a for a in path.get("assessment", [])}
    evidence = path.get("evidenceStates") or {}
    packet = path.get("researchPacket") or {}
    disposition, action = _STANCE.get(decision.get("decision", ""), ("Needs attention", "Review this path."))
    included = [c for c in companies_on_path if c.get("disposition") == "include"]
    needs_v = [c for c in companies_on_path if c.get("disposition") == "needs_verification"]

    narrative = [
        {
            "dimensionKey": key,
            "state": assessment.get(key, {}).get("state", "unassessed"),
            "rationale": assessment.get(key, {}).get("rationale", ""),
            "label": "hypothesis",
        }
        for key in NARRATIVE
    ]
    economics = assessment.get("economics", {}).get("rationale", "")
    risks = assessment.get("risks", {}).get("rationale", "")

    return {
        "pathId": path["pathId"],
        "pathLabels": path.get("nodeLabels", []),
        "disposition": disposition,
        "recommendedAction": action,
        "decision": decision.get("decision"),
        "ruleFired": decision.get("ruleFired"),
        "reason": decision.get("reason"),
        "confidence": _CONFIDENCE.get(str(evidence.get("quality")), "Low"),
        "headline": _headline(path.get("nodeLabels", []), disposition, len(included), evidence),
        "valueProposition": assessment.get("value_proposition", {}).get("rationale", ""),
        "economics": economics,
        "risks": risks,
        "narrative": narrative,
        "evidence": {
            "sufficiency": evidence.get("sufficiency"),
            "quality": evidence.get("quality"),
            "criticalUnknowns": evidence.get("criticalUnknowns"),
        },
        "openGaps": packet.get("gaps", []),
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
    quality = evidence.get("quality") or "no"
    return (
        f"{disposition}: {where}. {included} verified compan{'y' if included == 1 else 'ies'}, "
        f"{evidence.get('sufficiency') or 'insufficient'} evidence ({quality} quality)."
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
