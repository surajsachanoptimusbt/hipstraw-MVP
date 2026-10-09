"""T032: Unit tests for vichara basis grounding against the objective bundle."""

from __future__ import annotations

OBJECTIVE_TEXT = (
    "Our invoice accuracy platform targets small and mid-market companies "
    "in the Dallas-Fort Worth metro area. We focus on continuous obligation "
    "intelligence for accounts payable teams processing over 10,000 invoices "
    "per month. Q4 2026 launch planned."
)


class TestBasisGrounding:
    def test_exact_excerpt_accepted(self) -> None:
        from hipstraw_mm.market.vichara import check_basis_grounding

        result = check_basis_grounding("small and mid-market companies", OBJECTIVE_TEXT)
        assert result.status == "pass"

    def test_normalized_excerpt_accepted(self) -> None:
        """Case, dashes, quotes, spacing normalized before matching."""
        from hipstraw_mm.market.vichara import check_basis_grounding

        result = check_basis_grounding("Dallas-Fort Worth", OBJECTIVE_TEXT)
        assert result.status == "pass"

    def test_paraphrase_fails(self) -> None:
        from hipstraw_mm.market.vichara import check_basis_grounding

        result = check_basis_grounding("SMB organizations in Texas", OBJECTIVE_TEXT)
        assert result.status == "fail"
        assert result.reason == "basis_not_in_objective"

    def test_empty_basis_fails(self) -> None:
        from hipstraw_mm.market.vichara import check_basis_grounding

        result = check_basis_grounding("", OBJECTIVE_TEXT)
        assert result.status == "fail"

    def test_case_insensitive_match(self) -> None:
        from hipstraw_mm.market.vichara import check_basis_grounding

        result = check_basis_grounding("CONTINUOUS OBLIGATION INTELLIGENCE", OBJECTIVE_TEXT)
        assert result.status == "pass"

    def test_collapsed_whitespace(self) -> None:
        from hipstraw_mm.market.vichara import check_basis_grounding

        result = check_basis_grounding("accounts  payable  teams", OBJECTIVE_TEXT)
        assert result.status == "pass"


class TestItemGroundingCheck:
    def test_answered_with_bad_basis_fails(self) -> None:
        from hipstraw_mm.market.vichara import check_item_grounding

        item = {
            "question": "q", "status": "answered", "answer": "a",
            "basis": ["completely fabricated text"], "reason": None,
        }
        results = check_item_grounding(item, OBJECTIVE_TEXT)
        failing = [r for r in results if r["status"] == "fail"]
        assert len(failing) >= 1
        assert failing[0]["reason"] == "basis_not_in_objective"

    def test_answered_with_good_basis_passes(self) -> None:
        from hipstraw_mm.market.vichara import check_item_grounding

        item = {
            "question": "q", "status": "answered", "answer": "a",
            "basis": ["Q4 2026 launch planned"], "reason": None,
        }
        results = check_item_grounding(item, OBJECTIVE_TEXT)
        failing = [r for r in results if r["status"] == "fail"]
        assert len(failing) == 0

    def test_unresolved_not_checked(self) -> None:
        from hipstraw_mm.market.vichara import check_item_grounding

        item = {
            "question": "q", "status": "unresolved", "answer": None,
            "basis": [], "reason": "no information in the objective",
        }
        results = check_item_grounding(item, OBJECTIVE_TEXT)
        assert len(results) == 0
