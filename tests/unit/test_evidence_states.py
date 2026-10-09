"""T083: FR-020 rule tables of research R16."""

from __future__ import annotations

SETTINGS = {"sufficiencyHalf": 0.5, "decisionReadyMinCompanies": 3, "qualityMixedFloor": 0.5, "qualityStrongFloor": 0.8}
FULL = {"existence": True, "location": True, "size": True, "interest_signal": True}


def _co(full=True, conf=0.9, **extra):
    proofs = dict(FULL) if full else {**FULL, "size": None}
    return {"proofs": proofs, "evidenceConfidence": conf, **extra}


class TestSufficiency:
    def test_insufficient(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_sufficiency

        assert compute_sufficiency([], SETTINGS) == "insufficient"
        assert compute_sufficiency([_co(False)], SETTINGS) == "insufficient"

    def test_partial(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_sufficiency

        assert compute_sufficiency([_co(), _co(False), _co(False)], SETTINGS) == "partial"

    def test_sufficient_at_half(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_sufficiency

        assert compute_sufficiency([_co(), _co(False)], SETTINGS) == "sufficient"

    def test_decision_ready(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_sufficiency

        assert compute_sufficiency([_co(), _co(), _co()], SETTINGS) == "decision-ready"

    def test_all_but_too_few_is_sufficient(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_sufficiency

        assert compute_sufficiency([_co(), _co()], SETTINGS) == "sufficient"


class TestQuality:
    def test_contradictory(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_quality

        assert compute_quality([_co(conflict=True)], SETTINGS) == "contradictory"

    def test_bands(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_quality

        assert compute_quality([_co(conf=0.49)], SETTINGS) == "weak"
        assert compute_quality([_co(conf=0.5)], SETTINGS) == "mixed"
        assert compute_quality([_co(conf=0.79)], SETTINGS) == "mixed"
        assert compute_quality([_co(conf=0.8, needsVerification=True)], SETTINGS) == "strong"

    def test_high_confidence(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_quality

        assert compute_quality([_co(conf=0.9), _co(conf=0.85)], SETTINGS) == "high-confidence"

    def test_stale_not_produced(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_quality

        assert compute_quality([_co()], SETTINGS) != "stale"


class TestCriticalUnknowns:
    def test_unidentified(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_critical_unknowns

        assert compute_critical_unknowns([]) == "unidentified"

    def test_open(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_critical_unknowns

        assert compute_critical_unknowns([_co(), _co(False)]) == "open"

    def test_reduced(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_critical_unknowns

        assert compute_critical_unknowns([_co(unknowns=["buyer"])]) == "reduced"

    def test_resolved(self) -> None:
        from hipstraw_mm.market.evidence_states import compute_critical_unknowns

        assert compute_critical_unknowns([_co()]) == "resolved"


def test_states_come_from_grammar() -> None:
    from hipstraw_mm.market.evidence_states import (
        compute_critical_unknowns,
        compute_quality,
        compute_sufficiency,
    )
    from hipstraw_mm.market.grammar import load_grammar

    dims = load_grammar().dimensions
    suff = next(d for d in dims if "sufficiency" in d.key)
    qual = next(d for d in dims if "quality" in d.key)
    unk = next(d for d in dims if "unknown" in d.key)
    cos = [_co(), _co(False)]
    assert compute_sufficiency(cos, SETTINGS) in suff.states
    assert compute_quality(cos, SETTINGS) in qual.states
    assert compute_critical_unknowns(cos) in unk.states
    for d in (suff, qual, unk):
        assert d.assessedBy
