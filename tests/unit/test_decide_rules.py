"""T084: Market Status rule table (research R15), over the Review's playbook Dispositions."""

from __future__ import annotations

from hipstraw_mm.market.decide import compute_market_status, unassessed_dimensions


def status(*dispositions: str, **extra: object) -> str:
    return str(compute_market_status([{"disposition": d, **extra} for d in dispositions])["state"])


class TestMarketStatus:
    def test_progressing_when_any_unit_advances(self) -> None:
        for d in ("ACTIVATE", "BUILD", "SCALE"):
            assert status(d, "STOP") == "progressing"

    def test_blocked_when_every_unit_stops_or_none_survive(self) -> None:
        assert status("STOP", "STOP") == "blocked"
        assert compute_market_status([])["state"] == "blocked"

    def test_at_risk(self) -> None:
        assert status("TEST", unresolvedAtSegmentOrBuyer=True) == "at-risk"

    def test_awaiting_evidence_for_explore_or_test(self) -> None:
        assert status("TEST") == "awaiting-evidence"
        assert status("EXPLORE", "PARK") == "awaiting-evidence"

    def test_needs_attention_for_park_or_reframe(self) -> None:
        assert status("PARK", "REFRAME") == "needs-attention"

    def test_stores_rule_reason_right(self) -> None:
        s = compute_market_status([{"disposition": "ACTIVATE"}])
        assert s["ruleFired"] and s["reason"] and s["right"] == "set_market_status"


def test_trajectory_transition_unassessed() -> None:
    items = unassessed_dimensions()
    assert {i["dimensionKey"] for i in items} == {"trajectory", "transition"}
    assert all(i["reason"] == "needs a comparison with an earlier run" for i in items)
