"""T033: Unit tests for bounded_repair in src/hipstraw_mm/market/repair.py."""

from __future__ import annotations


class TestBoundedRepair:
    def test_no_failures_no_repair_calls(self) -> None:
        from hipstraw_mm.market.repair import bounded_repair

        check_calls = []
        repair_calls = []

        def check(items):
            check_calls.append(items)
            return []  # no failures

        def repair(failures):
            repair_calls.append(failures)
            return {}  # no fixes

        result = bounded_repair(
            items={"dim1": {"status": "ok"}},
            check_fn=check,
            repair_fn=repair,
            max_attempts=3,
        )
        assert len(repair_calls) == 0
        assert result.unresolved == []

    def test_one_repair_fixes_all(self) -> None:
        from hipstraw_mm.market.repair import bounded_repair

        attempt = [0]

        def check(items):
            if attempt[0] == 0:
                return [{"key": "dim1", "reason": "basis_not_in_objective"}]
            return []

        def repair(failures):
            attempt[0] += 1
            return {"dim1": {"status": "fixed"}}

        result = bounded_repair(
            items={"dim1": {"status": "bad"}},
            check_fn=check,
            repair_fn=repair,
            max_attempts=3,
        )
        assert result.unresolved == []
        assert result.attempts == 1

    def test_max_3_attempts(self) -> None:
        from hipstraw_mm.market.repair import bounded_repair

        repair_calls = []

        def check(items):
            return [{"key": "dim1", "reason": "still_bad"}]

        def repair(failures):
            repair_calls.append(failures)
            return {"dim1": {"status": "still_bad"}}

        result = bounded_repair(
            items={"dim1": {"status": "bad"}},
            check_fn=check,
            repair_fn=repair,
            max_attempts=3,
        )
        assert len(repair_calls) == 3
        assert len(result.unresolved) >= 1
        assert result.unresolved[0]["reason"] == "repair exhausted"

    def test_covers_all_failing_in_one_call(self) -> None:
        from hipstraw_mm.market.repair import bounded_repair

        repair_calls = []

        def check(items):
            return [
                {"key": "dim1", "reason": "bad"},
                {"key": "dim2", "reason": "bad"},
            ]

        def repair(failures):
            repair_calls.append(failures)
            return {}

        bounded_repair(
            items={"dim1": {}, "dim2": {}},
            check_fn=check,
            repair_fn=repair,
            max_attempts=3,
        )
        # Each repair call should receive all failing items
        for call in repair_calls:
            keys = [f["key"] for f in call]
            assert "dim1" in keys
            assert "dim2" in keys

    def test_both_checks_rerun_after_each_attempt(self) -> None:
        from hipstraw_mm.market.repair import bounded_repair

        check_calls = []
        attempt = [0]

        def check(items):
            check_calls.append(attempt[0])
            if attempt[0] < 2:
                return [{"key": "dim1", "reason": "bad"}]
            return []

        def repair(failures):
            attempt[0] += 1
            return {"dim1": {"status": "fixed"}}

        bounded_repair(
            items={"dim1": {}},
            check_fn=check,
            repair_fn=repair,
            max_attempts=3,
        )
        # Check is called at least once per attempt
        assert len(check_calls) >= 2

    def test_new_failure_counts_as_failed_attempt(self) -> None:
        from hipstraw_mm.market.repair import bounded_repair

        attempt = [0]

        def check(items):
            if attempt[0] == 0:
                return [{"key": "dim1", "reason": "original_problem"}]
            elif attempt[0] == 1:
                return [{"key": "dim1", "reason": "new_problem"}]
            return []

        def repair(failures):
            attempt[0] += 1
            return {"dim1": {"status": "attempted"}}

        result = bounded_repair(
            items={"dim1": {}},
            check_fn=check,
            repair_fn=repair,
            max_attempts=3,
        )
        # A new failure type still counts as a failed attempt
        assert result.attempts >= 2

    def test_unresolved_items_not_dropped(self) -> None:
        from hipstraw_mm.market.repair import bounded_repair

        def check(items):
            return [
                {"key": "dim1", "reason": "unfixable"},
                {"key": "dim2", "reason": "unfixable"},
            ]

        def repair(failures):
            return {}

        result = bounded_repair(
            items={"dim1": {}, "dim2": {}},
            check_fn=check,
            repair_fn=repair,
            max_attempts=3,
        )
        unresolved_keys = [u["key"] for u in result.unresolved]
        assert "dim1" in unresolved_keys
        assert "dim2" in unresolved_keys
        for u in result.unresolved:
            assert u["reason"] == "repair exhausted"
