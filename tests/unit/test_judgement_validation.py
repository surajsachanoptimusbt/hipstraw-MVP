"""Turning a judgement into a disposition (research R9, contracts/llm-outputs.md §5).

Started in Phase 3 for the rule "include needs at least one passing evidence document"; T080 adds the
cited-ID cases (for T065), and T060 the remaining ones.
"""

from __future__ import annotations

from hipstraw_mm.llm_schemas import ReviewJudgement
from hipstraw_mm.steps.review import judged_disposition

FITS = ReviewJudgement(falsifierMet=False, fitHolds=True, citedEvidenceIds=[], reason="Fits the position.")


def test_include_when_the_fit_holds_and_passing_evidence_exists():
    disposition, reason = judged_disposition(FITS, ["ev_run_1_0001", "ev_run_1_0002"])
    assert disposition == "include"
    assert reason


def test_include_without_passing_evidence_becomes_needs_verification():
    disposition, reason = judged_disposition(FITS, [])
    assert disposition == "needs_verification"
    assert "no passing evidence" in reason


def test_falsifier_met_excludes_even_without_evidence():
    judgement = FITS.model_copy(update={"falsifierMet": True, "reason": "Owned by a large enterprise."})
    disposition, _ = judged_disposition(judgement, ["ev_run_1_0001"])
    assert disposition == "exclude"


def test_fit_not_holding_is_needs_verification():
    judgement = FITS.model_copy(update={"fitHolds": False, "reason": "No sign of the problem."})
    disposition, _ = judged_disposition(judgement, ["ev_run_1_0001"])
    assert disposition == "needs_verification"


# T080 (for T065, moved to Phase 4 on 2026-10-07): the judgement's cited IDs must all be passing
# evidence of this record (contracts/llm-outputs.md §5).


def test_a_judgement_citing_unknown_evidence_needs_verification():
    judgement = FITS.model_copy(update={"citedEvidenceIds": ["ev_run_1_0001", "ev_run_1_9999"]})
    disposition, reason = judged_disposition(judgement, ["ev_run_1_0001", "ev_run_1_0002"])
    assert disposition == "needs_verification"
    assert "judgement cited unknown evidence" in reason


def test_a_judgement_citing_only_passing_evidence_can_include():
    judgement = FITS.model_copy(update={"citedEvidenceIds": ["ev_run_1_0002"]})
    disposition, _ = judged_disposition(judgement, ["ev_run_1_0001", "ev_run_1_0002"])
    assert disposition == "include"
