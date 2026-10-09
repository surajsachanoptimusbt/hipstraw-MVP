"""T053: pure structural validation rules for the seed graph."""

from __future__ import annotations

import copy
import random
from pathlib import Path

import pytest

LEVELS = ["segment", "archetype", "problem", "trigger", "buyerRole", "useCase"]


@pytest.fixture
def meaning():
    from hipstraw_mm.market.meaning import load_graph_meaning

    return load_graph_meaning(Path("config"))


def _good_graph() -> dict:
    nodes = []
    for lv in LEVELS:
        n = {"nodeId": f"{lv}_0001", "level": lv, "label": lv}
        if lv == "segment":
            n["metroIds"] = ["m1"]
        if lv == "archetype":
            n["sizeBand"] = "small"
        nodes.append(n)
    edges = [
        {"fromNodeId": f"{LEVELS[i]}_0001", "toNodeId": f"{LEVELS[i + 1]}_0001"}
        for i in range(len(LEVELS) - 1)
    ]
    return {"nodes": nodes, "edges": edges, "unresolved": [], "metrosInForce": ["m1"]}


def _rules(vs):
    return {v["rule"] for v in vs}


def _validate(g, meaning):
    from hipstraw_mm.market.validate import validate_graph_structure

    return validate_graph_structure(g, meaning)


class TestValidateStructure:
    def test_good_graph_has_no_violations(self, meaning):
        assert _validate(_good_graph(), meaning) == []

    def test_orphan_node(self, meaning):
        g = _good_graph()
        g["nodes"].append({"nodeId": "problem_0002", "level": "problem"})
        vs = _validate(g, meaning)
        assert [(v["nodeId"], v["rule"]) for v in vs] == [("problem_0002", "orphan_node")]

    def test_dangling_edge(self, meaning):
        g = _good_graph()
        g["edges"].append({"fromNodeId": "segment_0001", "toNodeId": "archetype_9999"})
        vs = _validate(g, meaning)
        assert _rules(vs) == {"dangling_edge"}
        assert vs[0]["edgeId"] == "segment_0001->archetype_9999"

    def test_undefined_level(self, meaning):
        g = _good_graph()
        g["nodes"].append({"nodeId": "x_1", "level": "galaxy"})
        g["edges"].append({"fromNodeId": "useCase_0001", "toNodeId": "x_1"})
        vs = _validate(g, meaning)
        assert [(v["nodeId"], v["rule"]) for v in vs] == [("x_1", "undefined_level")]

    def test_skipped_level(self, meaning):
        g = _good_graph()
        g["edges"].append({"fromNodeId": "segment_0001", "toNodeId": "problem_0001"})
        vs = _validate(g, meaning)
        assert _rules(vs) == {"skipped_level"}
        assert "edgeId" in vs[0]

    def test_reversed_level(self, meaning):
        g = _good_graph()
        g["edges"].append({"fromNodeId": "problem_0001", "toNodeId": "archetype_0001"})
        vs = _validate(g, meaning)
        assert _rules(vs) == {"reversed_level"}

    def test_duplicate_node_id(self, meaning):
        g = _good_graph()
        g["nodes"].append({"nodeId": "problem_0001", "level": "problem"})
        vs = _validate(g, meaning)
        assert [(v["nodeId"], v["rule"]) for v in vs] == [("problem_0001", "duplicate_node_id")]

    def test_node_outside_mandatory_filter(self, meaning):
        g = _good_graph()
        g["nodes"][0]["metroIds"] = ["elsewhere"]
        g["nodes"][1]["sizeBand"] = "enterprise"
        vs = _validate(g, meaning)
        assert {(v["nodeId"], v["rule"]) for v in vs} == {
            ("segment_0001", "metro_in_force"),
            ("archetype_0001", "no_enterprise"),
        }

    def test_empty_level_without_unresolved(self, meaning):
        g = _good_graph()
        g["nodes"] = [n for n in g["nodes"] if n["level"] != "useCase"]
        g["edges"] = g["edges"][:-1]
        vs = _validate(g, meaning)
        assert _rules(vs) == {"empty_level"}
        assert vs[0]["level"] == "useCase"

    def test_empty_level_with_unresolved_is_fine(self, meaning):
        g = _good_graph()
        g["nodes"] = [n for n in g["nodes"] if n["level"] != "useCase"]
        g["edges"] = g["edges"][:-1]
        g["unresolved"] = [{"level": "useCase", "reason": "no evidence"}]
        assert _validate(g, meaning) == []

    def test_several_parents_is_not_a_violation(self, meaning):
        g = _good_graph()
        g["nodes"].append({"nodeId": "segment_0002", "level": "segment", "metroIds": ["m1"]})
        g["edges"].append({"fromNodeId": "segment_0002", "toNodeId": "archetype_0001"})
        assert _validate(g, meaning) == []

    def test_each_violation_names_target_and_rule(self, meaning):
        g = _good_graph()
        g["nodes"].append({"nodeId": "problem_0002", "level": "problem"})
        g["edges"].append({"fromNodeId": "segment_0001", "toNodeId": "problem_0001"})
        g["edges"].append({"fromNodeId": "a", "toNodeId": "b"})
        vs = _validate(g, meaning)
        assert vs
        for v in vs:
            assert v.get("nodeId") or v.get("edgeId")
            assert v["rule"]
            assert v["reason"]

    def test_deterministic_over_100_calls(self, meaning):
        g = _good_graph()
        g["nodes"].append({"nodeId": "problem_0002", "level": "problem"})
        first = _validate(g, meaning)
        assert all(_validate(g, meaning) == first for _ in range(100))

    def test_order_independent(self, meaning):
        g = _good_graph()
        g["nodes"].append({"nodeId": "problem_0002", "level": "problem"})
        g["edges"].append({"fromNodeId": "segment_0001", "toNodeId": "problem_0001"})
        expected = _validate(g, meaning)
        rng = random.Random(1)
        for _ in range(10):
            h = copy.deepcopy(g)
            rng.shuffle(h["nodes"])
            rng.shuffle(h["edges"])
            assert _validate(h, meaning) == expected
