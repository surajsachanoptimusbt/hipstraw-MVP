"""T066: Unit tests for LinkVerification and PathAssessment schemas."""

from __future__ import annotations

import pytest

PER_PATH = [
    "value_proposition", "demand_signals", "adoption_readiness", "economics",
    "alternatives", "risks", "dependencies",
]


def _link(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {"fromNodeId": "a", "toNodeId": "b", "rationale": "r", "linkConfidence": 0.7}
    base.update(kw)
    return base


def _dim(key: str, state: str = "plausible", **kw: object) -> dict[str, object]:
    base: dict[str, object] = {"dimensionKey": key, "state": state, "rationale": "r", "label": "hypothesis"}
    base.update(kw)
    return base


class TestLinkVerification:
    def test_valid(self) -> None:
        from hipstraw_mm.market.schemas import LinkVerification

        lv = LinkVerification.model_validate({"links": [_link()]})
        assert lv.links[0].linkConfidence == 0.7

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_confidence_range(self, value: float) -> None:
        from pydantic import ValidationError

        from hipstraw_mm.market.schemas import LinkVerification

        with pytest.raises(ValidationError):
            LinkVerification.model_validate({"links": [_link(linkConfidence=value)]})

    @pytest.mark.parametrize("value", [0.0, 1.0])
    def test_confidence_bounds_allowed(self, value: float) -> None:
        from hipstraw_mm.market.schemas import LinkVerification

        LinkVerification.model_validate({"links": [_link(linkConfidence=value)]})

    def test_extra_rejected(self) -> None:
        from pydantic import ValidationError

        from hipstraw_mm.market.schemas import LinkVerification

        with pytest.raises(ValidationError):
            LinkVerification.model_validate({"links": [_link(extra=1)]})
        with pytest.raises(ValidationError):
            LinkVerification.model_validate({"links": [], "extra": 1})

    def test_every_input_link_appears_exactly_once(self) -> None:
        from hipstraw_mm.market.links import check_link_coverage

        inputs = [{"fromNodeId": "a", "toNodeId": "b"}, {"fromNodeId": "a", "toNodeId": "c"}]
        check_link_coverage(inputs, [_link(toNodeId="b"), _link(toNodeId="c")])
        with pytest.raises(ValueError, match="missing"):
            check_link_coverage(inputs, [_link(toNodeId="b")])
        with pytest.raises(ValueError, match="repeats"):
            check_link_coverage(inputs, [_link(toNodeId="b"), _link(toNodeId="b"), _link(toNodeId="c")])


class TestPathAssessment:
    def test_valid_seven(self) -> None:
        from hipstraw_mm.market.schemas import PathAssessment

        pa = PathAssessment.model_validate({"dimensions": [_dim(k) for k in PER_PATH]})
        assert [d.dimensionKey for d in pa.dimensions] == PER_PATH

    def test_non_per_path_key_rejected(self) -> None:
        from pydantic import ValidationError

        from hipstraw_mm.market.schemas import PathAssessment

        with pytest.raises(ValidationError):
            PathAssessment.model_validate({"dimensions": [_dim("timing")]})

    def test_label_must_be_hypothesis(self) -> None:
        from pydantic import ValidationError

        from hipstraw_mm.market.schemas import PathAssessment

        with pytest.raises(ValidationError):
            PathAssessment.model_validate({"dimensions": [_dim("risks", label="fact")]})

    def test_no_person_fields(self) -> None:
        from pydantic import ValidationError

        from hipstraw_mm.market.schemas import PathAssessment

        with pytest.raises(ValidationError):
            PathAssessment.model_validate({"dimensions": [_dim("risks", personName="x")]})

    def test_state_must_be_in_grammar_states(self) -> None:
        from hipstraw_mm.market.assess import assessment_record
        from hipstraw_mm.market.grammar import load_grammar

        grammar = load_grammar()
        for key in PER_PATH:
            dim = grammar.by_key(key)
            assert dim is not None
            assessment_record(grammar, _dim(key, dim.states[0]))
            with pytest.raises(ValueError, match="not a valid state"):
                assessment_record(grammar, _dim(key, "bogus"))
