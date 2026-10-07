"""T047: size signals, ranges, conflicts, and the parent-company check (research R6)."""

from __future__ import annotations

import pytest

from hipstraw_mm.evidence.size import evaluate_parent, evaluate_size, parse_size

MAX_EMPLOYEES = 500
MAX_REVENUE = 100_000_000


def _status(*claims: tuple[str, str], max_employees: int = MAX_EMPLOYEES, max_revenue: int = MAX_REVENUE) -> str:
    signals = [(kind, value, f"ev{i}") for i, (kind, value) in enumerate(claims, start=1)]
    return str(evaluate_size(signals, max_employees, max_revenue)["status"])


class TestParseSize:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("120", (120, 120)),
            ("51-200", (51, 200)),
            ("51–200", (51, 200)),
            ("5,000+", (5000, None)),
            ("more than 1,000", (1000, None)),
            ("fewer than 50", (None, 50)),
            ("$20 million", (20_000_000, 20_000_000)),
            ("$10-20 million", (10_000_000, 20_000_000)),
            ("$2 billion", (2_000_000_000, 2_000_000_000)),
            ("12,000", (12_000, 12_000)),
        ],
    )
    def test_values(self, value, expected):
        assert parse_size(value) == expected

    def test_no_number(self):
        assert parse_size("a small team") is None


class TestEvaluateSize:
    def test_thresholds_are_strict_less_than(self):
        assert _status(("employees", "499")) == "under"
        assert _status(("employees", "500")) == "over"
        assert _status(("revenue", "$99 million")) == "under"
        assert _status(("revenue", "$100 million")) == "over"

    def test_thresholds_come_from_the_caller_not_the_code(self):
        assert _status(("employees", "450")) == "under"
        assert _status(("employees", "450"), max_employees=400) == "over"
        assert _status(("revenue", "$50 million"), max_revenue=40_000_000) == "over"

    def test_a_range_uses_its_upper_bound_for_under_and_lower_bound_for_over(self):
        assert _status(("employees", "51-200")) == "under"
        assert _status(("employees", "51-200"), max_employees=150) == "unknown"
        assert _status(("employees", "51-200"), max_employees=40) == "over"

    def test_conflicting_counts_across_the_threshold_are_a_conflict_and_both_are_kept(self):
        size = evaluate_size([("employees", "450", "ev1"), ("employees", "620", "ev2")], MAX_EMPLOYEES, MAX_REVENUE)
        assert size["status"] == "conflict"
        assert [(s["low"], s["evidenceId"]) for s in size["signals"]] == [(450, "ev1"), (620, "ev2")]

    def test_only_over_evidence_is_over(self):
        assert _status(("employees", "5,000+")) == "over"

    def test_no_signals_is_unknown(self):
        assert _status() == "unknown"

    def test_an_unparseable_value_is_not_a_signal(self):
        size = evaluate_size([("employees", "a small team", "ev1")], MAX_EMPLOYEES, MAX_REVENUE)
        assert size == {"signals": [], "status": "unknown"}


class TestEvaluateParent:
    def _parent(self, parents, sizes=(), large=()):
        return evaluate_parent(
            parents=list(parents),
            parent_sizes=list(sizes),
            large_parents=list(large),
            max_employees=MAX_EMPLOYEES,
            max_revenue_usd=MAX_REVENUE,
        )

    def test_no_parent_claim_means_no_parent(self):
        assert self._parent([]) is None

    def test_a_parent_on_the_configured_list_is_large(self):
        parent = self._parent([("Omega Conglomerate", "ev1")], large=["Omega Conglomerate"])
        assert parent == {"name": "Omega Conglomerate", "evidenceIds": ["ev1"], "status": "large"}

    def test_the_configured_list_is_compared_by_normalized_name(self):
        parent = self._parent([("Omega Conglomerate, Inc.", "ev1")], large=["omega conglomerate"])
        assert parent is not None and parent["status"] == "large"

    def test_a_parent_shown_over_the_employee_threshold_is_large(self):
        parent = self._parent([("Heron Holdings", "ev1")], sizes=[("employees", "12,000", "ev2")])
        assert parent == {"name": "Heron Holdings", "evidenceIds": ["ev1", "ev2"], "status": "large"}

    def test_a_parent_shown_over_the_revenue_threshold_is_large(self):
        parent = self._parent([("Heron Holdings", "ev1")], sizes=[("revenue", "$2 billion", "ev2")])
        assert parent is not None and parent["status"] == "large"

    def test_a_parent_shown_under_both_thresholds_is_small(self):
        parent = self._parent([("Wren Partners", "ev1")], sizes=[("employees", "40", "ev2")])
        assert parent is not None and parent["status"] == "small"

    def test_a_parent_of_unknown_size_is_unknown_size(self):
        parent = self._parent([("Pelican Group", "ev1")])
        assert parent == {"name": "Pelican Group", "evidenceIds": ["ev1"], "status": "unknown_size"}
