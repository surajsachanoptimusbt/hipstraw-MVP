"""Position & Evaluation Sub-controller rules (P&E spec v0.4, sections 4-7).

Pure functions over stored records: the evaluation-case lifecycle, confidence (never a model
self-rating), the Position Transition Rubric, research/validation requirements, the candidate
comparison, and matching a micro market to the program's earlier positions. Every rubric carries a
version so a recommendation can be reproduced from its inputs.
"""

from __future__ import annotations

import re
from typing import Any

Doc = dict[str, Any]

CONFIDENCE_RUBRIC = "confidence.v1"
TRANSITION_RUBRIC = "position_transition.v1"

# Appendix B lifecycle
CASE_STATES = ("RECEIVED", "QUEUED", "EVALUATING", "NEEDS_RESEARCH", "WAITING", "DECIDING", "READY",
               "ESCALATED", "CLOSED")

# 5.6 recommendation states -> the Market Manager decision each one supports
RECOMMENDATION_SUPPORTS = {
    "Recommend Transition": "pursue",
    "Strengthen": "pursue",
    "Maintain": "pursue",
    "Validate": "needs more evidence",
    "Investigate Further": "needs more evidence",
    "Defer": "needs more evidence",
    "Challenge": "needs more evidence",
    "Weaken": "needs more evidence",
    "Recommend Retirement": "drop",
}

_SUFFICIENT = {"sufficient", "decision-ready"}
_BANDS = ("Low", "Medium", "High")


def _cap(band: str, ceiling: str) -> str:
    return band if _BANDS.index(band) <= _BANDS.index(ceiling) else ceiling


def economic_midpoint(estimate: Doc | None) -> float | None:
    if not estimate:
        return None
    return (float(estimate["valuePoolUsdLow"]) + float(estimate["valuePoolUsdHigh"])) / 2


def economics_sensitive(estimate: Doc | None) -> bool:
    """A wide range (high > 4x low) or any high-impact sensitivity makes the estimate fragile."""
    if not estimate:
        return False
    low, high = float(estimate["valuePoolUsdLow"]), float(estimate["valuePoolUsdHigh"])
    wide = low <= 0 or high / low > 4
    return wide or any(s.get("impact") == "high" for s in estimate.get("sensitivities", []))


def assess_confidence(evidence: Doc, packet: Doc, estimate: Doc | None) -> Doc:
    """Confidence band with limiting factors (rubric confidence.v1). Starts from evidence quality,
    then caps for missing verified companies, contradictions, open minimum proofs, and fragile economics."""
    quality = str(evidence.get("quality") or "weak")
    band = {"high-confidence": "High", "strong": "High", "mixed": "Medium"}.get(quality, "Low")
    limiting: list[str] = []
    if quality in ("weak", "contradictory"):
        limiting.append(f"evidence quality is {quality}")
    if not packet.get("included"):
        band = _cap(band, "Low")
        limiting.append("no verified (included) company yet")
    if packet.get("contradictions") or quality == "contradictory":
        band = _cap(band, "Low")
        limiting.append("contradictory evidence is unresolved")
    if evidence.get("criticalUnknowns") == "open":
        band = _cap(band, "Medium")
        limiting.append("minimum proofs (HQ, size, interest signal) still unknown for some companies")
    if estimate is None:
        limiting.append("no economic assessment")
    elif economics_sensitive(estimate):
        band = _cap(band, "Medium")
        limiting.append("economic estimate is highly sensitive to its assumptions")
    if packet.get("error"):
        band = _cap(band, "Low")
        limiting.append("company research failed (a process failure, not evidence against the market)")
    return {"band": band, "limitingFactors": limiting, "rubric": CONFIDENCE_RUBRIC}


def research_requirements(path: Doc, packet: Doc, confidence: Doc, estimate: Doc | None) -> list[Doc]:
    """Research / Validation Requirements (Appendix D.1) for the gaps that could change the recommendation."""
    labels = " > ".join(path.get("nodeLabels", [])) or path["pathId"]
    out: list[Doc] = []

    def add(gap: str, why: str, evidence: str, priority: str) -> None:
        out.append({
            "decisionBlocked": f"Whether to advance the Market Position for {labels}",
            "evidenceGap": gap,
            "whyMaterial": why,
            "requiredEvidence": evidence,
            "priority": priority,
            "stopCondition": "Evidence sufficient to classify the gap, or an evidence ceiling is reached",
            "returnFormat": "Updated Research Evidence Packet with supporting and contradicting evidence",
            "status": "issued",
        })

    if packet.get("error") or not packet.get("found"):
        add("No company could be researched for this micro market",
            "Absence of companies may be a search or constraint problem, not absence of a market",
            "Company listings for this segment and archetype within the metros and size limits", "High")
    elif not packet.get("included"):
        add("No company passed every Review rule",
            "Without one verified company the path cannot be advanced",
            "Cited HQ, size and interest-signal evidence for the needs-verification companies", "High")
    for gap in packet.get("gaps", [])[:3]:
        add(f"{gap['field']} unknown for {gap['companies']} compan{'y' if gap['companies'] == 1 else 'ies'}",
            "A missing minimum proof keeps evidence sufficiency below decision-ready",
            f"Authoritative, recent evidence for {gap['field']}", "Medium")
    if packet.get("contradictions"):
        add(f"Contradictory evidence for {', '.join(packet['contradictions'])}",
            "Contradictions must be resolved, not averaged away",
            "Independent sources that confirm or refute the conflicting claims", "High")
    if estimate is not None and economics_sensitive(estimate):
        drivers = [s["factor"] for s in estimate.get("sensitivities", []) if s.get("impact") == "high"]
        add("Economic estimate rests on fragile assumptions" + (f" ({', '.join(drivers)})" if drivers else ""),
            "The value-pool range is wide enough to change the priority of this micro market",
            "Evidence for the highest-impact assumptions (spend levels, leakage rates, company counts)", "Medium")
    if confidence["band"] == "Low" and not out:
        add("Confidence is low", "; ".join(confidence["limitingFactors"]) or "evidence is thin",
            "Corroborating evidence from independent sources", "Medium")
    return out


def recommend(path: Doc, packet: Doc, evidence: Doc, confidence: Doc, prior: Doc | None) -> Doc:
    """Position Transition Rubric (position_transition.v1). Returns the recommendation and the rule fired."""
    included = int(packet.get("included") or 0)
    pending = int(packet.get("needsVerification") or 0)
    sufficient = evidence.get("sufficiency") in _SUFFICIENT
    prior_status = (prior or {}).get("status")

    def out(rec: str, rule: str, why: str) -> Doc:
        return {"recommendation": rec, "ruleFired": rule, "rationale": why, "rubric": TRANSITION_RUBRIC,
                "supportsDecision": RECOMMENDATION_SUPPORTS[rec]}

    if packet.get("error"):
        return out("Investigate Further", "research_failed",
                   "Company research failed; a process failure is not evidence against this market.")
    if not packet.get("found"):
        return out("Investigate Further", "no_companies_found",
                   "No company was found; absence of evidence is not evidence of absence.")
    if packet.get("contradictions"):
        return out("Validate", "contradiction_present", "Contradictory evidence must be validated first.")
    if not included and not pending:
        if prior_status == "Pursue":
            return out("Weaken", "prior_pursue_now_unsupported",
                       "Every company was excluded; the earlier Pursue position is no longer supported.")
        return out("Recommend Retirement", "all_companies_excluded",
                   "Every company found was excluded by Review; nothing more evidence could fill.")
    if included and sufficient and confidence["band"] != "Low":
        if prior_status == "Pursue":
            if _BANDS.index(confidence["band"]) > _BANDS.index((prior or {}).get("confidence", "Low")):
                return out("Strengthen", "prior_pursue_confidence_up",
                           "Evidence raises confidence in a Pursue position.")
            return out("Maintain", "prior_pursue_still_supported", "The Pursue position remains supported.")
        if prior_status:
            return out("Strengthen", "evidence_now_sufficient",
                       f"Evidence is now {evidence.get('sufficiency')} with {included} verified compan"
                       f"{'y' if included == 1 else 'ies'}.")
        return out("Recommend Transition", "new_candidate_supported",
                   f"{included} verified compan{'y' if included == 1 else 'ies'} and {evidence.get('sufficiency')} "
                   "evidence support advancing to selective testing.")
    if included:
        if prior_status == "Pursue":
            return out("Weaken", "prior_pursue_evidence_thinner", "Evidence no longer meets the Pursue bar.")
        return out("Validate", "verified_but_insufficient",
                   f"{included} verified compan{'y' if included == 1 else 'ies'}, but evidence is "
                   f"{evidence.get('sufficiency')} with {confidence['band'].lower()} confidence.")
    return out("Investigate Further", "only_unverified_companies",
               f"{pending} compan{'y needs' if pending == 1 else 'ies need'} verification before any recommendation.")


def assurance_level(recommendation: str, confidence: str) -> Doc:
    """7.5 assurance by consequence: transitions and retirements are high consequence."""
    if recommendation in ("Recommend Transition", "Recommend Retirement"):
        level = "High"
    elif recommendation in ("Strengthen", "Weaken", "Validate", "Challenge"):
        level = "Moderate"
    else:
        level = "Low"
    gap = level == "High"
    return {
        "level": level,
        "challengerRun": False,
        "note": "High-consequence recommendation: Market Manager Review is required and no challenger "
                "evaluation ran in this pass." if gap else None,
        "lowConfidenceTransition": level == "High" and confidence == "Low",
    }


def compare_candidates(cases: list[Doc]) -> Doc:
    """A common-basis comparison (5.3, Appendix F): leaders per dimension, trade-offs and near-ties.
    It never forces a single winner from a composite score."""
    rows = [{
        "pathId": c["pathId"],
        "labels": c["labels"],
        "searchScore": c.get("searchScore"),
        "valueMid": economic_midpoint(c.get("economics")),
        "sufficiency": c["evidence"].get("sufficiency"),
        "confidence": c["confidence"]["band"],
        "included": c["packet"].get("included", 0),
        "openGaps": len(c["packet"].get("gaps", [])),
        "recommendation": c["recommendation"]["recommendation"],
    } for c in cases]
    suff_rank = {"insufficient": 0, "partial": 1, "sufficient": 2, "decision-ready": 3}

    def lead(key: Any) -> str | None:
        scored = [(key(r), r["pathId"]) for r in rows if key(r) is not None]
        if not scored:
            return None
        best = max(v for v, _ in scored)
        winners = [p for v, p in scored if v == best]
        return winners[0] if len(winners) == 1 else None

    leaders = {
        "economics": lead(lambda r: r["valueMid"]),
        "evidence": lead(lambda r: (suff_rank.get(r["sufficiency"], 0), r["included"])),
        "confidence": lead(lambda r: _BANDS.index(r["confidence"])),
        "searchScore": lead(lambda r: r["searchScore"]),
    }
    trade_offs, near_ties = [], []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            ea, eb = a["valueMid"] or 0, b["valueMid"] or 0
            va = (suff_rank.get(a["sufficiency"], 0), _BANDS.index(a["confidence"]))
            vb = (suff_rank.get(b["sufficiency"], 0), _BANDS.index(b["confidence"]))
            if (ea > eb and va < vb) or (eb > ea and vb < va):
                richer, stronger = (a, b) if ea > eb else (b, a)
                trade_offs.append({
                    "higherEconomics": richer["pathId"], "strongerEvidence": stronger["pathId"],
                    "note": "Higher estimated economics with weaker evidence versus lower economics with "
                            "stronger evidence; resolve with targeted research, not a composite score.",
                })
            top = max(ea, eb)
            if top and abs(ea - eb) <= 0.15 * top and a["confidence"] == b["confidence"]:
                near_ties.append({"paths": [a["pathId"], b["pathId"]],
                                  "note": "Economics within 15% at the same confidence: a near tie."})
    dominant = [
        r["pathId"] for r in rows
        if leaders["economics"] == r["pathId"] and leaders["evidence"] == r["pathId"]
        and leaders["confidence"] in (r["pathId"], None)
    ]
    return {"rows": rows, "leaders": leaders, "tradeOffs": trade_offs, "nearTies": near_ties,
            "dominant": dominant[0] if dominant and not near_ties else None}


_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"and", "the", "of", "for", "with", "in", "a", "an", "to", "or", "by", "on"}


def label_tokens(labels: list[str]) -> set[str]:
    return {t for t in _TOKEN.findall(" ".join(labels).lower()) if t not in _STOP}


def similarity(a: list[str], b: list[str]) -> float:
    ta, tb = label_tokens(a), label_tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def match_prior(labels: list[str], candidates: list[Doc], threshold: float = 0.6) -> Doc | None:
    """The candidate (with `labels`) most similar to `labels`, if it clears the threshold."""
    best, best_score = None, 0.0
    for c in candidates:
        score = similarity(labels, c.get("labels", []))
        if score > best_score:
            best, best_score = c, score
    return {**best, "similarity": round(best_score, 3)} if best is not None and best_score >= threshold else None


def latest_positions(positions: list[Doc]) -> list[Doc]:
    """Latest version of each canonical position key."""
    latest: dict[str, Doc] = {}
    for p in positions:
        key = p["positionKey"]
        if key not in latest or int(p["version"]) > int(latest[key]["version"]):
            latest[key] = p
    return list(latest.values())
