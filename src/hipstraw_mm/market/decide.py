"""Market Manager rule tables (research R15): path decisions and Market Status.

The manager never traverses the graph: these functions take only final paths, their evaluations,
and the run summary. Each result stores the rule that fired, the reason, and the right used.
"""

from __future__ import annotations

from typing import Any

SUFFICIENCY_RANK = {"insufficient": 0, "partial": 1, "sufficient": 2, "decision-ready": 3}


def decide_path(path: dict[str, Any]) -> dict[str, Any]:
    """`path`: {companies [{disposition, verified}], sufficiency, canStillFill}."""
    companies = path.get("companies", [])
    included = [c for c in companies if c.get("disposition") == "include"]
    sufficiency = path.get("sufficiency", "insufficient")
    if included and SUFFICIENCY_RANK.get(sufficiency, 0) >= SUFFICIENCY_RANK["sufficient"]:
        return {
            "decision": "pursue",
            "ruleFired": "pursue_included_and_sufficient",
            "reason": f"{len(included)} included company(ies) and evidence sufficiency is {sufficiency}",
            "right": "decide_path",
        }
    if not any(c.get("verified") for c in companies) and not path.get("canStillFill"):
        return {
            "decision": "drop",
            "ruleFired": "drop_no_verified_company",
            "reason": "no verified company and no missing citation that more evidence could fill",
            "right": "decide_path",
        }
    return {
        "decision": "needs more evidence",
        "ruleFired": "needs_more_evidence_default",
        "reason": "neither the pursue nor the drop rule applies",
        "right": "decide_path",
    }


def compute_market_status(paths: list[dict[str, Any]]) -> dict[str, Any]:
    """`paths`: decisions, each {decision, unresolvedAtSegmentOrBuyer?}. Rules apply in order."""
    decisions = [p.get("decision") for p in paths]

    def result(state: str, rule: str, reason: str) -> dict[str, Any]:
        return {"state": state, "ruleFired": rule, "reason": reason, "right": "set_market_status"}

    if "pursue" in decisions:
        return result("progressing", "status_progressing", "at least one path is pursue")
    if not paths:
        return result("blocked", "status_blocked", "no path survived the beam")
    if all(d == "drop" for d in decisions):
        return result("blocked", "status_blocked", "every path is drop")
    if any(p.get("unresolvedAtSegmentOrBuyer") for p in paths):
        return result("at-risk", "status_at_risk", "an unresolved item remains at the segment or buyer level")
    if "needs more evidence" in decisions:
        return result(
            "awaiting-evidence", "status_awaiting_evidence", "no path is pursue and one needs more evidence"
        )
    return result("needs-attention", "status_needs_attention", "no other rule applies")


def unassessed_dimensions() -> list[dict[str, str]]:
    reason = "needs a comparison with an earlier run"
    return [
        {"dimensionKey": "trajectory", "reason": reason},
        {"dimensionKey": "transition", "reason": reason},
    ]
