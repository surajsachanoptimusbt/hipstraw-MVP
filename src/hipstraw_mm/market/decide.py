"""Market Manager rule table for Market Status (research R15), over the Review's Dispositions.

The manager never traverses the graph: this takes only the Disposition of each final market unit and
the run summary. Each result stores the rule that fired, the reason, and the right used.
"""

from __future__ import annotations

from typing import Any

ADVANCING = ("ACTIVATE", "BUILD", "SCALE")
NEEDS_EVIDENCE = ("EXPLORE", "TEST")


def compute_market_status(units: list[dict[str, Any]]) -> dict[str, Any]:
    """`units`: each {disposition, unresolvedAtSegmentOrBuyer?}. Rules apply in order."""
    dispositions = [u.get("disposition") for u in units]

    def result(state: str, rule: str, reason: str) -> dict[str, Any]:
        return {"state": state, "ruleFired": rule, "reason": reason, "right": "set_market_status"}

    if any(d in ADVANCING for d in dispositions):
        return result("progressing", "status_progressing", "at least one market unit is ACTIVATE, BUILD or SCALE")
    if not units:
        return result("blocked", "status_blocked", "no market unit survived opportunity ranking")
    if all(d == "STOP" for d in dispositions):
        return result("blocked", "status_blocked", "every market unit is STOP")
    if any(u.get("unresolvedAtSegmentOrBuyer") for u in units):
        return result("at-risk", "status_at_risk", "an unresolved item remains at the segment or buyer level")
    if any(d in NEEDS_EVIDENCE for d in dispositions):
        return result("awaiting-evidence", "status_awaiting_evidence",
                      "no market unit is advancing and at least one is EXPLORE or TEST")
    return result("needs-attention", "status_needs_attention", "every market unit is PARK, REFRAME or STOP")


def unassessed_dimensions() -> list[dict[str, str]]:
    reason = "needs a comparison with an earlier run"
    return [
        {"dimensionKey": "trajectory", "reason": reason},
        {"dimensionKey": "transition", "reason": reason},
    ]
