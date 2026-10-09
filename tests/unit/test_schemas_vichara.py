"""T031: Unit tests for DimensionDeliberation, CoverageJudgement, DimensionRepair schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestDimensionDeliberation:
    def test_valid_answered(self) -> None:
        from hipstraw_mm.market.schemas import DimensionDeliberation

        data = {
            "dimensionKey": "market_scope",
            "items": [
                {"question": "Is market defined?", "status": "answered",
                 "answer": "Yes, focused on SMBs", "basis": ["focused on SMBs"], "reason": None}
            ],
        }
        obj = DimensionDeliberation.model_validate(data)
        assert obj.dimensionKey == "market_scope"
        assert len(obj.items) == 1

    def test_valid_unresolved(self) -> None:
        from hipstraw_mm.market.schemas import DimensionDeliberation

        data = {
            "dimensionKey": "risks",
            "items": [
                {"question": "What risks?", "status": "unresolved",
                 "answer": None, "basis": [], "reason": "no information in the objective"}
            ],
        }
        obj = DimensionDeliberation.model_validate(data)
        assert obj.items[0].status == "unresolved"

    def test_extra_field_rejected(self) -> None:
        from hipstraw_mm.market.schemas import DimensionDeliberation

        data = {
            "dimensionKey": "market_scope",
            "items": [
                {"question": "q", "status": "answered", "answer": "a",
                 "basis": ["x"], "reason": None, "extraField": True}
            ],
        }
        with pytest.raises(ValidationError):
            DimensionDeliberation.model_validate(data)

    def test_answered_needs_answer_and_basis(self) -> None:
        from hipstraw_mm.market.schemas import DimensionDeliberation

        data = {
            "dimensionKey": "market_scope",
            "items": [
                {"question": "q", "status": "answered", "answer": None,
                 "basis": [], "reason": None}
            ],
        }
        with pytest.raises(ValidationError):
            DimensionDeliberation.model_validate(data)

    def test_unresolved_needs_reason_empty_basis(self) -> None:
        from hipstraw_mm.market.schemas import DimensionDeliberation

        data = {
            "dimensionKey": "risks",
            "items": [
                {"question": "q", "status": "unresolved", "answer": None,
                 "basis": ["something"], "reason": "no info"}
            ],
        }
        with pytest.raises(ValidationError):
            DimensionDeliberation.model_validate(data)

    def test_items_min_1(self) -> None:
        from hipstraw_mm.market.schemas import DimensionDeliberation

        data = {"dimensionKey": "market_scope", "items": []}
        with pytest.raises(ValidationError):
            DimensionDeliberation.model_validate(data)

    def test_no_person_fields(self) -> None:
        from hipstraw_mm.market.schemas import DimensionDeliberation

        fields = set()
        for f in DimensionDeliberation.model_fields:
            fields.add(f)
        for bad in ("name", "email", "phone", "firstName", "lastName"):
            assert bad not in fields


class TestCoverageJudgement:
    def test_valid(self) -> None:
        from hipstraw_mm.market.schemas import CoverageJudgement

        data = {
            "dimensions": [
                {"dimensionKey": "market_scope", "addressesDimension": True, "reason": "covers it"},
            ],
        }
        obj = CoverageJudgement.model_validate(data)
        assert len(obj.dimensions) == 1

    def test_extra_field_rejected(self) -> None:
        from hipstraw_mm.market.schemas import CoverageJudgement

        data = {
            "dimensions": [
                {"dimensionKey": "market_scope", "addressesDimension": True,
                 "reason": "ok", "bonus": 1},
            ],
        }
        with pytest.raises(ValidationError):
            CoverageJudgement.model_validate(data)

    def test_false_addresses(self) -> None:
        from hipstraw_mm.market.schemas import CoverageJudgement

        data = {
            "dimensions": [
                {"dimensionKey": "timing", "addressesDimension": False, "reason": "not addressed"},
            ],
        }
        obj = CoverageJudgement.model_validate(data)
        assert obj.dimensions[0].addressesDimension is False


class TestDimensionRepair:
    def test_valid(self) -> None:
        from hipstraw_mm.market.schemas import DimensionRepair

        data = {
            "dimensions": [
                {
                    "dimensionKey": "timing",
                    "items": [
                        {"question": "When?", "status": "answered",
                         "answer": "Q4 2026", "basis": ["Q4 2026"], "reason": None}
                    ],
                },
            ],
        }
        obj = DimensionRepair.model_validate(data)
        assert len(obj.dimensions) == 1

    def test_extra_field_rejected(self) -> None:
        from hipstraw_mm.market.schemas import DimensionRepair

        data = {
            "dimensions": [
                {
                    "dimensionKey": "timing",
                    "items": [
                        {"question": "q", "status": "answered", "answer": "a",
                         "basis": ["a"], "reason": None}
                    ],
                    "extraField": True,
                },
            ],
        }
        with pytest.raises(ValidationError):
            DimensionRepair.model_validate(data)
