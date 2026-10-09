"""T054: GraphCoverage and GraphRepair schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def _node(**kw):
    base = {"label": "n", "description": "d", "level": "problem"}
    base.update(kw)
    return base


class TestGraphCoverage:
    def test_valid(self):
        from hipstraw_mm.market.schemas import GraphCoverage

        gc = GraphCoverage.model_validate(
            {"gaps": [{"dimensionKey": "d1", "covered": False, "reason": "missing"}]}
        )
        assert gc.gaps[0].covered is False

    def test_extra_forbidden(self):
        from hipstraw_mm.market.schemas import GraphCoverage

        with pytest.raises(ValidationError):
            GraphCoverage.model_validate({"gaps": [], "x": 1})
        with pytest.raises(ValidationError):
            GraphCoverage.model_validate(
                {"gaps": [{"dimensionKey": "d", "covered": True, "reason": "r", "x": 1}]}
            )

    def test_gap_requires_fields(self):
        from hipstraw_mm.market.schemas import GraphCoverage

        with pytest.raises(ValidationError):
            GraphCoverage.model_validate({"gaps": [{"dimensionKey": "d"}]})


class TestGraphRepair:
    def test_valid(self):
        from hipstraw_mm.market.schemas import GraphRepair

        r = GraphRepair.model_validate(
            {"addNodes": [_node(parentLabels=["p"], sourceItemIds=["i1"])], "removeNodeIds": []}
        )
        assert r.addNodes[0].level == "problem"

    def test_level_required_and_checked(self):
        from hipstraw_mm.market.schemas import GraphRepair

        with pytest.raises(ValidationError):
            GraphRepair.model_validate({"addNodes": [{"label": "n", "description": "d"}]})
        with pytest.raises(ValidationError):
            GraphRepair.model_validate({"addNodes": [_node(level="nope")]})

    def test_extra_forbidden(self):
        from hipstraw_mm.market.schemas import GraphRepair

        with pytest.raises(ValidationError):
            GraphRepair.model_validate({"addNodes": [], "extra": 1})
        with pytest.raises(ValidationError):
            GraphRepair.model_validate({"addNodes": [_node(bogus=1)]})

    def test_remove_must_be_empty(self):
        from hipstraw_mm.market.schemas import GraphRepair

        with pytest.raises(ValidationError):
            GraphRepair.model_validate({"addNodes": [], "removeNodeIds": ["a"]})


class TestCheckAdditive:
    def test_additive_ok(self):
        from hipstraw_mm.market.schemas import check_additive

        before = [{"nodeId": "a"}, {"nodeId": "b"}]
        assert check_additive(before, [*before, {"nodeId": "c"}]) is True

    def test_removed_node_fails(self):
        from hipstraw_mm.market.schemas import check_additive

        assert check_additive([{"nodeId": "a"}, {"nodeId": "b"}], [{"nodeId": "a"}]) is False
