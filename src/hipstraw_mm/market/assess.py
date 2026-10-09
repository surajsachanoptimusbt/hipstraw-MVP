"""Path assessment helpers (Position & Evaluation, right `assess_path`)."""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market.grammar import Grammar

Doc = dict[str, Any]

PER_PATH_KEYS = (
    "value_proposition",
    "demand_signals",
    "adoption_readiness",
    "economics",
    "alternatives",
    "risks",
    "dependencies",
)

LAYER = "position_evaluation"
RIGHT = "assess_path"


def assessment_record(grammar: Grammar, entry: Doc) -> Doc:
    """Validate one dimension assessment against the grammar and build its stored result."""
    key = entry["dimensionKey"]
    if key not in PER_PATH_KEYS:
        raise ValueError(f"{key!r} is not a per-path dimension")
    dim = grammar.by_key(key)
    if dim is None:
        raise ValueError(f"dimension {key!r} not in grammar")
    if entry["state"] not in dim.states:
        raise ValueError(f"state {entry['state']!r} is not a valid state for {key!r}")
    return {
        "dimensionKey": key,
        "state": entry["state"],
        "rationale": entry["rationale"],
        "assessedBy": dim.assessedBy,
        "label": "hypothesis",
    }


def assess_records(grammar: Grammar, dimensions: list[Doc]) -> list[Doc]:
    """Require exactly the seven keys, once each, and return stored results."""
    keys = [d["dimensionKey"] for d in dimensions]
    if sorted(keys) != sorted(PER_PATH_KEYS):
        raise ValueError(f"assessment must contain exactly the keys {list(PER_PATH_KEYS)}, got {keys}")
    return [assessment_record(grammar, d) for d in dimensions]
