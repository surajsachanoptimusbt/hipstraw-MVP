"""T069: Unit tests for src/hipstraw_mm/market/assess.py."""

from __future__ import annotations

from typing import Any

import pytest

KEYS = [
    "value_proposition", "demand_signals", "adoption_readiness", "economics",
    "alternatives", "risks", "dependencies",
]


def _entries(grammar: Any) -> list[dict[str, str]]:
    out = []
    for k in KEYS:
        dim = grammar.by_key(k)
        out.append({"dimensionKey": k, "state": dim.states[0], "rationale": "r"})
    return out


def test_seven_keys() -> None:
    from hipstraw_mm.market.assess import PER_PATH_KEYS

    assert list(PER_PATH_KEYS) == KEYS


def test_results_store_fields() -> None:
    from hipstraw_mm.market.assess import assess_records
    from hipstraw_mm.market.grammar import load_grammar

    grammar = load_grammar()
    results = assess_records(grammar, _entries(grammar))
    assert len(results) == 7
    for r in results:
        dim = grammar.by_key(r["dimensionKey"])
        assert dim is not None
        assert r["state"] == dim.states[0]
        assert r["rationale"] == "r"
        assert r["assessedBy"] == dim.assessedBy
        assert r["label"] == "hypothesis"


def test_state_not_in_grammar_rejected() -> None:
    from hipstraw_mm.market.assess import assess_records
    from hipstraw_mm.market.grammar import load_grammar

    grammar = load_grammar()
    entries = _entries(grammar)
    entries[0]["state"] = "nonsense"
    with pytest.raises(ValueError, match="not a valid state"):
        assess_records(grammar, entries)


def test_missing_key_rejected() -> None:
    from hipstraw_mm.market.assess import assess_records
    from hipstraw_mm.market.grammar import load_grammar

    grammar = load_grammar()
    with pytest.raises(ValueError, match="exactly the keys"):
        assess_records(grammar, _entries(grammar)[:-1])


def test_layer_and_right() -> None:
    from hipstraw_mm.market.assess import LAYER, RIGHT
    from hipstraw_mm.market.layers import load_layers

    assert LAYER == "position_evaluation"
    assert RIGHT == "assess_path"
    text = repr(load_layers())
    assert "assess_path" in text and "position_evaluation" in text
