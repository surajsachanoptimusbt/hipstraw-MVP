"""T082: search score is a weighted mean of four factors, stored apart from every confidence."""

from __future__ import annotations

import pytest

FACTORS = {
    n: {"value": v, "rationale": "r"}
    for n, v in [("relevance", 0.8), ("feasibility", 0.4), ("timing", 0.6), ("cost", 0.2)]
}


def test_equal_weights_mean() -> None:
    from hipstraw_mm.market.beam import compute_search_score

    assert compute_search_score(FACTORS, {}) == pytest.approx(0.5)


def test_weights_normalized() -> None:
    from hipstraw_mm.market.beam import compute_search_score

    a = compute_search_score(FACTORS, {"relevance": 1, "feasibility": 1, "timing": 1, "cost": 1})
    b = compute_search_score(FACTORS, {"relevance": 10, "feasibility": 10, "timing": 10, "cost": 10})
    assert a == pytest.approx(b)


def test_changed_weight_changes_result() -> None:
    from hipstraw_mm.market.beam import compute_search_score

    base = compute_search_score(FACTORS, {})
    heavy = compute_search_score(FACTORS, {"relevance": 5, "feasibility": 1, "timing": 1, "cost": 1})
    assert heavy > base
    assert heavy == pytest.approx((0.8 * 5 + 0.4 + 0.6 + 0.2) / 8)


def test_plain_float_factors() -> None:
    from hipstraw_mm.market.beam import compute_search_score

    assert compute_search_score({"relevance": 1.0, "cost": 0.0}, {}) == pytest.approx(0.5)


def test_stored_record_has_no_confidence_field() -> None:
    from hipstraw_mm.market.beam import build_scored_record

    rec = build_scored_record("p1", FACTORS, {}, mean_link_confidence=0.9)
    assert rec["searchScore"] == pytest.approx(0.5)
    assert set(rec["factors"]) == {"relevance", "feasibility", "timing", "cost"}
    for f in rec["factors"].values():
        assert {"value", "rationale", "weight"} <= set(f)
    assert not {"confidence", "linkConfidence", "evidenceConfidence"} & set(rec)
    assert rec["meanLinkConfidence"] == 0.9


def test_mean_link_confidence_does_not_affect_score() -> None:
    from hipstraw_mm.market.beam import build_scored_record

    lo = build_scored_record("p1", FACTORS, {}, mean_link_confidence=0.1)
    hi = build_scored_record("p1", FACTORS, {}, mean_link_confidence=0.99)
    assert lo["searchScore"] == hi["searchScore"]
