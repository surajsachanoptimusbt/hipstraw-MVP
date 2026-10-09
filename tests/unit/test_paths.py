"""T068: Unit tests for src/hipstraw_mm/market/paths.py."""

from __future__ import annotations

import hashlib
import time

import pytest

LEVELS = ["segment", "archetype", "problem", "trigger", "buyerRole", "useCase"]


def _graph(width: int = 5) -> tuple[list[dict[str, str]], dict[str, str]]:
    node_levels = {f"{lvl}{i}": lvl for lvl in LEVELS for i in range(width)}
    edges = [
        {"fromNodeId": f"{a}{i}", "toNodeId": f"{b}{j}"}
        for a, b in zip(LEVELS, LEVELS[1:], strict=False)
        for i in range(width)
        for j in range(width)
    ]
    return edges, node_levels


class TestPathId:
    def test_deterministic_hash(self) -> None:
        from hipstraw_mm.market.paths import path_id

        ids = ["a", "b", "c"]
        assert path_id(ids) == path_id(list(ids))
        assert path_id(ids) == hashlib.sha256(b"a>b>c").hexdigest()[:8]
        assert len(path_id(ids)) == 8

    def test_order_matters(self) -> None:
        from hipstraw_mm.market.paths import path_id

        assert path_id(["a", "b"]) != path_id(["b", "a"])


class TestPathsBelow:
    def test_full_graph_count_fast(self) -> None:
        from hipstraw_mm.market.paths import paths_below

        edges, node_levels = _graph()
        targets = {f"segment{i}" for i in range(5)}
        start = time.perf_counter()
        n = paths_below(edges, LEVELS, node_levels, targets)
        elapsed = time.perf_counter() - start
        assert n == 15625
        assert elapsed < 0.05

    def test_single_node(self) -> None:
        from hipstraw_mm.market.paths import paths_below

        edges, node_levels = _graph()
        assert paths_below(edges, LEVELS, node_levels, {"archetype0"}) == 5**4

    def test_dead_end_counts_zero(self) -> None:
        from hipstraw_mm.market.paths import paths_below

        edges, node_levels = _graph(2)
        edges = [e for e in edges if e["fromNodeId"] != "trigger0"]
        assert paths_below(edges, LEVELS, node_levels, {"trigger0"}) == 0


class TestConstraints:
    def _path(self) -> list[dict[str, object]]:
        return [
            {"nodeId": "s1", "level": "segment", "label": "S", "metroIds": ["m1"]},
            {"nodeId": "a1", "level": "archetype", "label": "Clinic", "sizeBand": "small"},
        ]

    def test_good_path(self) -> None:
        from hipstraw_mm.market.paths import check_path_constraints

        c = {"excludedArchetypes": ["enterprise"], "allowedMetroIds": ["m1"], "allowedSizeBands": ["small"]}
        assert check_path_constraints(self._path(), c) is None

    def test_enterprise_archetype(self) -> None:
        from hipstraw_mm.market.paths import check_path_constraints

        path = self._path()
        path[1]["label"] = "Enterprise"
        v = check_path_constraints(path, {"excludedArchetypes": ["enterprise"]})
        assert v == {"constraint": "excludedArchetypes", "nodeId": "a1"}

    def test_segment_outside_metros(self) -> None:
        from hipstraw_mm.market.paths import check_path_constraints

        v = check_path_constraints(self._path(), {"allowedMetroIds": ["m9"]})
        assert v == {"constraint": "allowedMetroIds", "nodeId": "s1"}

    def test_size_limit(self) -> None:
        from hipstraw_mm.market.paths import check_path_constraints

        v = check_path_constraints(self._path(), {"allowedSizeBands": ["large"]})
        assert v == {"constraint": "allowedSizeBands", "nodeId": "a1"}


class TestStatus:
    def test_evidence_status(self) -> None:
        from hipstraw_mm.market.paths import evidence_status

        assert evidence_status(True, 0) == "no_evidence_found"
        assert evidence_status(False, 0) is None
        assert evidence_status(True, 1) == "has_evidence"
        assert evidence_status(False, 2) == "has_evidence"

    def test_final_never_back_to_kept(self) -> None:
        from hipstraw_mm.market.paths import transition_path

        p = transition_path({"status": "kept"}, "final", "top", "useCase", "t1", "s1")
        with pytest.raises(ValueError, match="never goes back"):
            transition_path(p, "kept", "x", None, "t2", "s2")

    def test_no_evidence_only_for_final(self) -> None:
        from hipstraw_mm.market.paths import transition_path

        with pytest.raises(ValueError, match="only to a final"):
            transition_path({"status": "kept"}, "no_evidence_found", "x", None, "t", "s")

    def test_history_appends(self) -> None:
        from hipstraw_mm.market.paths import transition_path

        p = transition_path({"status": "kept", "statusHistory": []}, "final", "top", "useCase", "t1", "s1")
        p = transition_path(p, "no_evidence_found", "none", None, "t2", "s2")
        assert [h["status"] for h in p["statusHistory"]] == ["final", "no_evidence_found"]
        assert p["statusHistory"][0] == {
            "status": "final", "reason": "top", "level": "useCase", "at": "t1", "stepId": "s1",
        }
