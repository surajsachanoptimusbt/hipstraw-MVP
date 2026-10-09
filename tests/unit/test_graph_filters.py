"""T035: Unit tests for graph generation filter and cap helpers in src/hipstraw_mm/market/graph.py."""

from __future__ import annotations


def _make_node(label, level, *, metro_ids=None, size_band=None, parent_labels=None, source_item_ids=None):
    return {
        "label": label,
        "description": f"Description for {label}",
        "parentLabels": parent_labels or [],
        "metroIds": metro_ids or [],
        "sizeBand": size_band,
        "sourceItemIds": source_item_ids or ["item_1"],
    }


class TestMetroFilter:
    def test_segment_with_valid_metros_kept(self) -> None:
        from hipstraw_mm.market.graph import apply_filters

        nodes = [_make_node("seg1", "segment", metro_ids=["dallas"])]
        run_metros = ["dallas", "fort_worth"]
        kept, excluded = apply_filters(nodes, "segment", run_metros)
        assert len(kept) == 1
        assert len(excluded) == 0

    def test_segment_with_invalid_metro_removed(self) -> None:
        from hipstraw_mm.market.graph import apply_filters

        nodes = [_make_node("seg1", "segment", metro_ids=["houston"])]
        run_metros = ["dallas", "fort_worth"]
        kept, excluded = apply_filters(nodes, "segment", run_metros)
        assert len(kept) == 0
        assert len(excluded) == 1
        assert excluded[0]["filterId"] == "metro_in_force"

    def test_segment_with_empty_metros_removed(self) -> None:
        from hipstraw_mm.market.graph import apply_filters

        nodes = [_make_node("seg1", "segment", metro_ids=[])]
        run_metros = ["dallas"]
        kept, excluded = apply_filters(nodes, "segment", run_metros)
        assert len(kept) == 0


class TestEnterpriseFilter:
    def test_enterprise_archetype_removed(self) -> None:
        from hipstraw_mm.market.graph import apply_filters

        nodes = [_make_node("arch1", "archetype", size_band="enterprise")]
        kept, excluded = apply_filters(nodes, "archetype", [])
        assert len(kept) == 0
        assert len(excluded) == 1
        assert excluded[0]["filterId"] == "no_enterprise"

    def test_small_archetype_kept(self) -> None:
        from hipstraw_mm.market.graph import apply_filters

        nodes = [_make_node("arch1", "archetype", size_band="small")]
        kept, excluded = apply_filters(nodes, "archetype", [])
        assert len(kept) == 1

    def test_valid_size_bands(self) -> None:
        from hipstraw_mm.market.graph import apply_filters

        for band in ("startup", "small", "mid_market"):
            nodes = [_make_node(f"arch_{band}", "archetype", size_band=band)]
            kept, _ = apply_filters(nodes, "archetype", [])
            assert len(kept) == 1


class TestCaps:
    def test_nodes_over_cap_dropped(self) -> None:
        from hipstraw_mm.market.graph import apply_caps

        nodes = [_make_node(f"n{i}", "problem") for i in range(8)]
        kept, over = apply_caps(nodes, max_nodes=5)
        assert len(kept) == 5
        assert len(over) == 3

    def test_parents_over_cap_dropped(self) -> None:
        from hipstraw_mm.market.graph import apply_parent_cap

        node = _make_node("n1", "problem", parent_labels=["p1", "p2", "p3", "p4"])
        capped = apply_parent_cap(node, max_parents=2)
        assert len(capped["parentLabels"]) == 2

    def test_dropped_in_model_order(self) -> None:
        """Nodes are dropped from the end (model's order preserved for kept)."""
        from hipstraw_mm.market.graph import apply_caps

        nodes = [_make_node(f"n{i}", "problem") for i in range(5)]
        kept, over = apply_caps(nodes, max_nodes=3)
        kept_labels = [n["label"] for n in kept]
        assert kept_labels == ["n0", "n1", "n2"]


class TestParentValidation:
    def test_invalid_parent_rejected(self) -> None:
        from hipstraw_mm.market.graph import validate_parents

        nodes = [_make_node("child", "problem", parent_labels=["nonexistent"])]
        prev_labels = {"existing_parent"}
        valid, invalid = validate_parents(nodes, prev_labels)
        assert len(valid) == 0
        assert len(invalid) == 1

    def test_valid_parent_accepted(self) -> None:
        from hipstraw_mm.market.graph import validate_parents

        nodes = [_make_node("child", "problem", parent_labels=["existing"])]
        prev_labels = {"existing"}
        valid, invalid = validate_parents(nodes, prev_labels)
        assert len(valid) == 1
        assert len(invalid) == 0


class TestEmptyLevel:
    def test_filtering_empties_level_produces_unresolved(self) -> None:
        from hipstraw_mm.market.graph import apply_filters

        nodes = [
            _make_node("seg1", "segment", metro_ids=["houston"]),
            _make_node("seg2", "segment", metro_ids=["austin"]),
        ]
        run_metros = ["dallas"]
        kept, excluded = apply_filters(nodes, "segment", run_metros)
        assert len(kept) == 0
        assert len(excluded) == 2


class TestNodeIds:
    def test_system_assigns_ids(self) -> None:
        from hipstraw_mm.market.graph import assign_node_ids

        nodes = [_make_node("seg1", "segment"), _make_node("seg2", "segment")]
        assigned = assign_node_ids(nodes, "segment", 1)
        for node in assigned:
            assert "nodeId" in node
            assert node["nodeId"].startswith("segment_")
        ids = [n["nodeId"] for n in assigned]
        assert len(set(ids)) == len(ids)
