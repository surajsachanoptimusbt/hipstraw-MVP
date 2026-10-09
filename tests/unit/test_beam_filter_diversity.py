"""T081: beam filter, diversity, keep-top, and final-path selection."""

from __future__ import annotations


def _c(path_id, score, segment="s1", problem="pr1", node_id="n1"):
    return {"pathId": path_id, "searchScore": score, "segment": segment, "problem": problem, "nodeId": node_id}


class TestFilter:
    def test_drops_constraint_breaker_with_reason(self) -> None:
        from hipstraw_mm.market.beam import filter_beam

        graph = {"nodes": {"n1": {"label": "A", "sizeBand": "small"}, "n2": {"label": "B", "sizeBand": "enterprise"}}}
        passed, dropped = filter_beam(
            [_c("p1", 0.5, node_id="n1"), _c("p2", 0.6, node_id="n2")],
            {"forbiddenSizeBands": ["enterprise"]},
            graph,
        )
        assert [c["pathId"] for c in passed] == ["p1"]
        assert dropped[0]["pathId"] == "p2"
        assert dropped[0]["filter"]["reason"]
        assert dropped[0]["outcome"] == "pruned"
        assert "pathsBelow" in dropped[0]


class TestDiversity:
    def test_one_per_segment_problem_from_problem_level(self) -> None:
        from hipstraw_mm.market.beam import diversity_filter

        kept, removed = diversity_filter([_c("p1", 0.5), _c("p2", 0.9), _c("p3", 0.4, problem="pr2")], "problem")
        assert {c["pathId"] for c in kept} == {"p2", "p3"}
        assert removed[0]["pathId"] == "p1"
        assert removed[0]["diversity"]["duplicateOf"] == "p2"

    def test_no_check_before_problem_level(self) -> None:
        from hipstraw_mm.market.beam import diversity_filter

        kept, removed = diversity_filter([_c("p1", 0.5, problem=None), _c("p2", 0.9, problem=None)], "archetype")
        assert len(kept) == 2 and removed == []


class TestKeepTop:
    def test_top_width_by_score(self) -> None:
        from hipstraw_mm.market.beam import keep_top

        kept, pruned = keep_top([_c(f"p{i}", i / 10) for i in range(1, 8)], 5)
        assert [c["pathId"] for c in kept] == ["p7", "p6", "p5", "p4", "p3"]
        assert {c["pathId"] for c in pruned} == {"p1", "p2"}

    def test_ties_break_by_path_id(self) -> None:
        from hipstraw_mm.market.beam import keep_top

        kept, pruned = keep_top([_c("pb", 0.5), _c("pc", 0.5), _c("pa", 0.5)], 2)
        assert [c["pathId"] for c in kept] == ["pa", "pb"]
        assert pruned[0]["pathId"] == "pc"

    def test_fewer_than_width_all_kept(self) -> None:
        from hipstraw_mm.market.beam import keep_top

        kept, pruned = keep_top([_c("p1", 0.1), _c("p2", 0.2)], 5)
        assert len(kept) == 2 and pruned == []

    def test_every_candidate_has_outcome_reason_paths_below(self) -> None:
        from hipstraw_mm.market.beam import keep_top, select_final

        kept, pruned = keep_top([_c(f"p{i}", i / 10) for i in range(1, 6)], 4)
        _, deferred, _ = select_final(kept, 3)
        for c in kept + pruned + deferred:
            assert c["outcome"] in {"kept", "pruned", "deferred"}
            assert c["reason"]
            assert "pathsBelow" in c
        assert deferred[0]["reason"] == "below the final-path limit"


class TestShortfall:
    def test_none_survive(self) -> None:
        from hipstraw_mm.market.beam import select_final
        from hipstraw_mm.market.decide import compute_market_status

        final, deferred, shortfall = select_final([], 3)
        assert final == [] and deferred == []
        assert shortfall == {"wanted": 3, "found": 0, "reason": "no path survived the beam"}
        assert compute_market_status([])["state"] == "blocked"

    def test_fewer_than_final(self) -> None:
        from hipstraw_mm.market.beam import select_final

        final, _, shortfall = select_final([_c("p1", 0.5)], 3)
        assert len(final) == 1
        assert shortfall is not None and shortfall["found"] == 1

    def test_enough_no_shortfall(self) -> None:
        from hipstraw_mm.market.beam import select_final

        _, _, shortfall = select_final([_c(f"p{i}", 0.5) for i in range(3)], 3)
        assert shortfall is None
