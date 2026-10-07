"""T048: source reliability and confidence (research R8). Deterministic; the model produces no numbers."""

from __future__ import annotations

import pytest

from hipstraw_mm.evidence.confidence import compute_confidence, confidence_band
from hipstraw_mm.steps.common import reliability_for

WEIGHTS = {"high": 1.0, "medium": 0.7, "low": 0.4}


def _ev(evidence_id: str, reliability: str, status: str = "pass") -> dict:
    return {
        "evidenceId": evidence_id,
        "reliability": reliability,
        "check": {"status": status, "reason": None if status == "pass" else "excerpt_not_found"},
    }


def _record(existence=None, hq=(), size=(), signals=()) -> dict:
    return {
        "existenceEvidenceId": existence,
        "hq": {"evidenceIds": list(hq)},
        "size": {"signals": [{"evidenceId": e} for e in size]},
        "interestSignals": [{"kind": "pain", "statement": "s", "evidenceIds": list(signals)}] if signals else [],
    }


class TestReliability:
    def test_reliability_comes_from_the_source_policy(self, test_config):
        policy = test_config.source_policy
        assert reliability_for("registry", policy) == "high"
        assert reliability_for("company_site", policy) == "medium"
        assert reliability_for("job_board", policy) == "medium"
        assert reliability_for("news", policy) == "medium"
        assert reliability_for("directory", policy) == "low"

    def test_weights_come_from_the_source_policy(self, test_config):
        assert test_config.source_policy.reliabilityWeights == WEIGHTS


class TestConfidence:
    def test_mean_of_the_best_passing_citation_per_item(self):
        evidence = {
            "e1": _ev("e1", "medium"),
            "e2": _ev("e2", "low"),
            "e3": _ev("e3", "medium"),
            "e4": _ev("e4", "high"),
            "e5": _ev("e5", "low"),
        }
        record = _record(existence="e1", hq=["e2", "e3"], size=["e4"], signals=["e5"])
        # existence 0.7, location max(0.4, 0.7) = 0.7, size 1.0, interest signal 0.4
        assert compute_confidence(record, evidence, WEIGHTS) == {"value": pytest.approx(0.7), "band": "Medium"}

    def test_an_item_without_a_passing_citation_counts_zero(self):
        evidence = {"e1": _ev("e1", "high"), "e2": _ev("e2", "high", status="fail"), "e3": _ev("e3", "high")}
        record = _record(existence="e1", hq=["e2"], size=["e3"])
        # existence 1.0, location 0 (its only citation failed), size 1.0, interest signal 0
        assert compute_confidence(record, evidence, WEIGHTS) == {"value": pytest.approx(0.5), "band": "Medium"}

    def test_all_strong_items_are_high(self):
        evidence = {k: _ev(k, r) for k, r in [("e1", "high"), ("e2", "high"), ("e3", "medium"), ("e4", "medium")]}
        record = _record(existence="e1", hq=["e2"], size=["e3"], signals=["e4"])
        assert compute_confidence(record, evidence, WEIGHTS) == {"value": pytest.approx(0.85), "band": "High"}

    def test_registry_only_record_is_zero_and_low(self):
        record = _record()
        assert compute_confidence(record, {}, WEIGHTS) == {"value": 0.0, "band": "Low"}

    def test_value_is_rounded_to_two_decimals(self):
        evidence = {k: _ev(k, "medium") for k in ("e1", "e2", "e3")}
        record = _record(existence="e1", hq=["e2"], size=["e3"])
        weights = {"high": 1.0, "medium": 0.67, "low": 0.4}
        assert compute_confidence(record, evidence, weights)["value"] == 0.5  # 2.01 / 4 = 0.5025


class TestBands:
    @pytest.mark.parametrize(
        ("value", "band"),
        [(1.0, "High"), (0.8, "High"), (0.79, "Medium"), (0.5, "Medium"), (0.49, "Low"), (0.0, "Low")],
    )
    def test_bands(self, value, band):
        assert confidence_band(value) == band
