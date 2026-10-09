"""T080: BeamScoring and BuyerRoles schemas (contracts/llm-outputs.md section 8 and 10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def _factor(v=0.5):
    return {"value": v, "rationale": "because"}


def _cand(path_id="p1", **over):
    base = {
        "pathId": path_id,
        "relevance": _factor(),
        "feasibility": _factor(),
        "timing": _factor(),
        "cost": _factor(),
    }
    base.update(over)
    return base


def _role(**over):
    base = {
        "pathId": "p1",
        "role": "Head of Finance",
        "authority": "owns_budget",
        "evidenceIds": ["ev1"],
        "rationale": "cited",
    }
    base.update(over)
    return base


class TestBeamScoring:
    def test_valid(self) -> None:
        from hipstraw_mm.market.schemas import BeamScoring

        assert len(BeamScoring.model_validate({"candidates": [_cand("a"), _cand("b")]}).candidates) == 2

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_value_out_of_range(self, value) -> None:
        from hipstraw_mm.market.schemas import BeamScoring

        with pytest.raises(ValidationError):
            BeamScoring.model_validate({"candidates": [_cand(cost=_factor(value))]})

    def test_missing_factor_rejected(self) -> None:
        from hipstraw_mm.market.schemas import BeamScoring

        c = _cand()
        del c["timing"]
        with pytest.raises(ValidationError):
            BeamScoring.model_validate({"candidates": [c]})

    def test_extra_rejected(self) -> None:
        from hipstraw_mm.market.schemas import BeamScoring

        with pytest.raises(ValidationError):
            BeamScoring.model_validate({"candidates": [_cand(confidence=0.9)]})

    def test_duplicate_path_rejected(self) -> None:
        from hipstraw_mm.market.schemas import BeamScoring

        with pytest.raises(ValidationError):
            BeamScoring.model_validate({"candidates": [_cand("a"), _cand("a")]})

    def test_no_person_fields(self) -> None:
        from hipstraw_mm.market.schemas import BeamCandidateScore

        assert not {"name", "email", "phone"} & set(BeamCandidateScore.model_fields)


class TestBuyerRoles:
    def test_valid(self) -> None:
        from hipstraw_mm.market.schemas import BuyerRoles

        assert BuyerRoles.model_validate({"roles": [_role()]}).roles[0].authority == "owns_budget"

    def test_bad_authority(self) -> None:
        from hipstraw_mm.market.schemas import BuyerRoles

        with pytest.raises(ValidationError):
            BuyerRoles.model_validate({"roles": [_role(authority="boss")]})

    def test_empty_evidence_rejected(self) -> None:
        from hipstraw_mm.market.schemas import BuyerRoles

        with pytest.raises(ValidationError):
            BuyerRoles.model_validate({"roles": [_role(evidenceIds=[])]})

    @pytest.mark.parametrize("field", ["name", "email", "phone"])
    def test_person_fields_rejected(self, field) -> None:
        from hipstraw_mm.market.schemas import BuyerRoles

        with pytest.raises(ValidationError):
            BuyerRoles.model_validate({"roles": [_role(**{field: "x"})]})
