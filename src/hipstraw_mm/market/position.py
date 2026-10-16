"""Market Position: the Market Manager's canonical, versioned Position for one market unit.

Position & Evaluation recommends; the Market Manager's Review (the playbook quick picker, review.py)
decides and commits. `commit_record` builds the canonical, versioned record: the seven axes, the
binding constraint, the chain (stance, Strategy, Play, Line, Moves, Gambits, Actions), the Disposition
and the Recommended next step, with lineage to the evaluation case. `build_market_position` builds the
fuller view the viewer and the report read.
"""

from __future__ import annotations

import hashlib
from typing import Any

from hipstraw_mm.market.evaluation import RECOMMENDATION_SUPPORTS, economic_midpoint, label_tokens

Doc = dict[str, Any]

# the seven per-path assessment dimensions, in the order a reviewer reads them
NARRATIVE = ("value_proposition", "demand_signals", "adoption_readiness", "economics",
             "alternatives", "risks", "dependencies")

CHAIN_FIELDS = ("axes", "bindingConstraint", "blocks", "stance", "marketTypes", "strategy", "strategyName",
                "play", "playName", "pickReason", "line", "nextStep", "gambits", "actions", "disposition",
                "attention", "playbookVersion", "pickerVersion")


def position_key(program_id: str, labels: list[str]) -> str:
    digest = hashlib.sha256(" ".join(sorted(label_tokens(labels))).encode("utf-8")).hexdigest()[:10]
    return f"{program_id}__mm_{digest}"


def trajectory(prior: Doc | None, disposition: str, confidence: str, order: list[str]) -> str:
    """Direction relative to the prior canonical version: new, up, down, or flat."""
    if prior is None:
        return "new"
    bands = {"Low": 0, "Medium": 1, "High": 2}

    def rank(d: str | None) -> int:
        return order.index(d) if d in order else 0

    before = (rank(prior.get("disposition")), bands.get(prior.get("confidence", "Low"), 0))
    after = (rank(disposition), bands.get(confidence, 0))
    return "up" if after > before else "down" if after < before else "flat"


def next_step_text(chain: Doc) -> str:
    step = chain.get("nextStep")
    if not step:
        return "No step left in the chosen Line; review the Position."
    return f"{step['id']} {step['name']} ({step['where']})"


def commit_record(run: Doc, path: Doc, case: Doc | None, chain: Doc, prior: Doc | None, at: str,
                  order: list[str]) -> Doc:
    """The canonical Market Position version the Market Manager commits for one market unit."""
    disposition = chain["disposition"]
    labels = path.get("nodeLabels", [])
    rec = (case or {}).get("recommendation") or {}
    confidence = ((case or {}).get("confidence") or {}).get("band", "Low")
    supports = rec.get("supportsDisposition") or RECOMMENDATION_SUPPORTS.get(rec.get("recommendation", ""))
    accepted = supports == disposition if rec else None
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
        **{k: chain.get(k) for k in CHAIN_FIELDS},
        "judgment": f"{disposition}: {' > '.join(labels)}",
        "reasons": [f"Disposition from {chain['reason']} ({chain['pickerVersion']})"]
                   + ([rec["rationale"]] if rec.get("rationale") else []),
        "confidence": confidence,
        "limitingFactors": ((case or {}).get("confidence") or {}).get("limitingFactors", []),
        "contradictions": (path.get("researchPacket") or {}).get("contradictions", []),
        "unknowns": [r["evidenceGap"] for r in requirements],
        "trajectory": trajectory(prior, disposition, confidence, order),
        "materiality": {
            "valuePoolUsdLow": (economics or {}).get("valuePoolUsdLow"),
            "valuePoolUsdHigh": (economics or {}).get("valuePoolUsdHigh"),
            "valueMid": economic_midpoint(economics),
            "basis": (economics or {}).get("unit"),
            "label": "hypothesis",
        },
        "learningPriority": requirements[0]["evidenceGap"] if requirements else None,
        "direction": next_step_text(chain),
        "valueProposition": assessment.get("value_proposition", {}).get("rationale", ""),
        "recommendationReviewed": rec.get("recommendation"),
        "recommendationAccepted": accepted,
        "reviewNote": None if accepted in (True, None) else (
            f"The Review chose {disposition} ({chain['reason']}); the Position & Evaluation recommendation "
            f"'{rec.get('recommendation')}' supports {supports} and was not taken."
        ),
        "evidenceLineage": {
            "evaluationCaseId": (case or {}).get("caseId"),
            "childRunId": path.get("childRunId"),
            "priorVersion": f"{prior['positionKey']}__v{prior['version']}" if prior else None,
        },
        "committedAt": at,
        "right": "commit_position",
    }


def build_market_position(path: Doc, companies_on_path: list[Doc], case: Doc | None, canonical: Doc) -> Doc:
    """The Market Position view for one market unit, read by the viewer and the report."""
    assessment = {a["dimensionKey"]: a for a in path.get("assessment", [])}
    evidence = path.get("evidenceStates") or {}
    packet = path.get("researchPacket") or {}
    included = [c for c in companies_on_path if c.get("disposition") == "include"]
    needs_v = [c for c in companies_on_path if c.get("disposition") == "needs_verification"]
    confidence = (case or {}).get("confidence") or {}
    rec = (case or {}).get("recommendation") or {}
    return {
        "pathId": path["pathId"],
        "pathLabels": path.get("nodeLabels", []),
        **{k: canonical.get(k) for k in CHAIN_FIELDS},
        "confidence": confidence.get("band", "Low"),
        "limitingFactors": confidence.get("limitingFactors", []),
        "recommendation": rec.get("recommendation"),
        "recommendationRationale": rec.get("rationale"),
        "recommendationAccepted": canonical.get("recommendationAccepted"),
        "reviewNote": canonical.get("reviewNote"),
        "positionKey": canonical.get("positionKey"),
        "version": canonical.get("version"),
        "trajectory": canonical.get("trajectory"),
        "headline": _headline(path.get("nodeLabels", []), canonical["disposition"], len(included), evidence),
        "valueProposition": assessment.get("value_proposition", {}).get("rationale", ""),
        "economics": assessment.get("economics", {}).get("rationale", ""),
        "economicEstimate": (case or {}).get("economics"),
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
    where = " > ".join(labels) if labels else "this market unit"
    return (
        f"{disposition}: {where}. {included} verified compan{'y' if included == 1 else 'ies'}, "
        f"{evidence.get('sufficiency') or 'insufficient'} evidence ({evidence.get('quality') or 'no'} quality)."
    )


def companies_for_path(path_id: str, market_companies: list[Doc]) -> list[Doc]:
    """The market-company records that link to this path, with the path's own company disposition."""
    out: list[Doc] = []
    for c in market_companies:
        for link in c.get("links", []):
            if link.get("pathId") == path_id:
                out.append({**c, "disposition": link.get("disposition")})
                break
    return out


__all__ = ["RECOMMENDATION_SUPPORTS", "build_market_position", "commit_record", "companies_for_path",
           "position_key", "trajectory"]
