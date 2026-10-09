"""T084: rule tables of research R15."""

from __future__ import annotations


def _path(**over):
    base = {"companies": [], "sufficiency": "insufficient", "canStillFill": False}
    base.update(over)
    return base


class TestPathDecision:
    def test_pursue(self) -> None:
        from hipstraw_mm.market.decide import decide_path

        d = decide_path(_path(companies=[{"disposition": "include", "verified": True}], sufficiency="sufficient"))
        assert d["decision"] == "pursue"

    def test_included_but_partial_needs_more(self) -> None:
        from hipstraw_mm.market.decide import decide_path

        d = decide_path(_path(companies=[{"disposition": "include", "verified": True}], sufficiency="partial"))
        assert d["decision"] == "needs more evidence"

    def test_drop(self) -> None:
        from hipstraw_mm.market.decide import decide_path

        d = decide_path(_path(companies=[{"disposition": "exclude", "verified": False}]))
        assert d["decision"] == "drop"

    def test_fillable_gap_not_dropped(self) -> None:
        from hipstraw_mm.market.decide import decide_path

        assert decide_path(_path(canStillFill=True))["decision"] == "needs more evidence"

    def test_stores_rule_reason_right(self) -> None:
        from hipstraw_mm.market.decide import decide_path

        for p in (_path(), _path(canStillFill=True)):
            d = decide_path(p)
            assert d["ruleFired"] and d["reason"] and d["right"] == "decide_path"


class TestMarketStatus:
    def test_progressing(self) -> None:
        from hipstraw_mm.market.decide import compute_market_status

        assert compute_market_status([{"decision": "pursue"}, {"decision": "drop"}])["state"] == "progressing"

    def test_blocked_all_drop_or_empty(self) -> None:
        from hipstraw_mm.market.decide import compute_market_status

        assert compute_market_status([{"decision": "drop"}])["state"] == "blocked"
        assert compute_market_status([])["state"] == "blocked"

    def test_at_risk(self) -> None:
        from hipstraw_mm.market.decide import compute_market_status

        s = compute_market_status([{"decision": "needs more evidence", "unresolvedAtSegmentOrBuyer": True}])
        assert s["state"] == "at-risk"

    def test_awaiting_evidence(self) -> None:
        from hipstraw_mm.market.decide import compute_market_status

        assert compute_market_status([{"decision": "needs more evidence"}])["state"] == "awaiting-evidence"

    def test_needs_attention(self) -> None:
        from hipstraw_mm.market.decide import compute_market_status

        assert compute_market_status([{"decision": "other"}])["state"] == "needs-attention"

    def test_stores_rule_reason_right(self) -> None:
        from hipstraw_mm.market.decide import compute_market_status

        s = compute_market_status([{"decision": "pursue"}])
        assert s["ruleFired"] and s["reason"] and s["right"] == "set_market_status"


def test_trajectory_transition_unassessed() -> None:
    from hipstraw_mm.market.decide import unassessed_dimensions

    items = unassessed_dimensions()
    assert {i["dimensionKey"] for i in items} == {"trajectory", "transition"}
    assert all(i["reason"] == "needs a comparison with an earlier run" for i in items)
