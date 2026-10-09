"""T036: Unit tests for GraphLevelProposal schema (contracts/llm-outputs.md §4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def _node(label="node1", *, parent_labels=None, metro_ids=None, size_band=None, source_item_ids=None):
    return {
        "label": label,
        "description": f"desc for {label}",
        "parentLabels": parent_labels or [],
        "metroIds": metro_ids or [],
        "sizeBand": size_band,
        "sourceItemIds": source_item_ids or ["item_1"],
    }


class TestGraphLevelProposal:
    def test_valid_segment(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "segment",
            "nodes": [_node("seg1", metro_ids=["dallas"])],
        }
        obj = GraphLevelProposal.model_validate(data)
        assert obj.level == "segment"
        assert len(obj.nodes) == 1

    def test_segment_requires_non_empty_metro_ids(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "segment",
            "nodes": [_node("seg1", metro_ids=[])],
        }
        with pytest.raises(ValidationError):
            GraphLevelProposal.model_validate(data)

    def test_non_segment_requires_empty_metro_ids(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "archetype",
            "nodes": [_node("arch1", metro_ids=["dallas"], size_band="small",
                           parent_labels=["seg1"])],
        }
        with pytest.raises(ValidationError):
            GraphLevelProposal.model_validate(data)

    def test_archetype_requires_size_band(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "archetype",
            "nodes": [_node("arch1", size_band=None, parent_labels=["seg1"])],
        }
        with pytest.raises(ValidationError):
            GraphLevelProposal.model_validate(data)

    def test_non_archetype_requires_null_size_band(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "problem",
            "nodes": [_node("prob1", size_band="small", parent_labels=["arch1"])],
        }
        with pytest.raises(ValidationError):
            GraphLevelProposal.model_validate(data)

    def test_valid_archetype(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "archetype",
            "nodes": [_node("arch1", size_band="startup", parent_labels=["seg1"])],
        }
        obj = GraphLevelProposal.model_validate(data)
        assert obj.nodes[0].sizeBand == "startup"

    def test_extra_field_rejected(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "segment",
            "nodes": [_node("seg1", metro_ids=["dallas"])],
            "extraField": True,
        }
        with pytest.raises(ValidationError):
            GraphLevelProposal.model_validate(data)

    def test_valid_levels(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        for level in ("segment", "archetype", "problem", "trigger", "buyerRole", "useCase"):
            node = _node(f"{level}_1")
            if level == "segment":
                node["metroIds"] = ["dallas"]
            elif level == "archetype":
                node["sizeBand"] = "small"
                node["parentLabels"] = ["seg1"]
            else:
                node["parentLabels"] = ["parent1"]
            data = {"level": level, "nodes": [node]}
            GraphLevelProposal.model_validate(data)

    def test_source_item_ids_present(self) -> None:
        from hipstraw_mm.market.schemas import GraphLevelProposal

        data = {
            "level": "segment",
            "nodes": [_node("seg1", metro_ids=["dallas"], source_item_ids=["item_1", "item_2"])],
        }
        obj = GraphLevelProposal.model_validate(data)
        assert obj.nodes[0].sourceItemIds == ["item_1", "item_2"]
