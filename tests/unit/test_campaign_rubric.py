"""Campaign rubric (Session 2026-10-29, FR-049 to FR-051) and the structured outputs of M06 and M07
(contracts/llm-outputs.md), with their honesty checks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hipstraw_mm.campaign.llm_outputs import (
    Judgement,
    QuoteOut,
    Synthesis,
    Variant,
    Variants,
    evidence_text,
    synthesis_checks,
    variants_checks,
)
from hipstraw_mm.campaign.rubric import load_rubric
from tests.unit.campaign_factories import evidence
from tests.unit.campaign_moves_support import CONFIG

RUBRIC = load_rubric(CONFIG)
EV = evidence(1)  # content "asset text 1"
CHANNELS = ["email"]


def _judgements(**override: Judgement) -> list[Judgement]:
    """One judgement per (question, channel); an override replaces that question's judgement."""
    out = [Judgement(questionId=q, channel=c, verdict="unknown", reason="no evidence", quotes=[], fix="ask the Sponsor")
           for q, c in RUBRIC.expected(CHANNELS)]
    return [override.get(j.questionId, j) for j in out]


def test_rubric_loads_with_plain_questions_and_anchors() -> None:
    assert RUBRIC.version == "campaign-rubric.v0.2"
    assert [q.id for q in RUBRIC.questions] == [f"CR{n:02d}" for n in range(1, 10)]
    for q in RUBRIC.questions:
        assert q.question.endswith("?") and q.met and q.partly and q.notMet and q.fix


def test_the_first_question_is_whether_the_message_fits_the_audience_on_each_channel() -> None:
    first = RUBRIC.questions[0]
    assert (first.id, first.title, first.scope) == ("CR01", "Message fits the audience", "channel")
    assert [q.id for q in RUBRIC.questions if q.scope == "channel"] == ["CR01", "CR02", "CR03", "CR04", "CR05"]
    assert RUBRIC.expected(["email", "linkedin_ads"])[:3] == [("CR01", "email"), ("CR01", "linkedin_ads"),
                                                              ("CR02", "email")]
    assert ("CR06", "") in RUBRIC.expected(["email", "linkedin_ads"])
    assert len(RUBRIC.expected(["email", "linkedin_ads"])) == 5 * 2 + 4


def test_outputs_reject_unknown_keys_and_verdicts() -> None:
    with pytest.raises(ValidationError):
        Judgement(questionId="CR01", channel="email", verdict="great", reason="r", quotes=[],  # type: ignore[arg-type]
                  fix="f")
    with pytest.raises(ValidationError):
        Synthesis.model_validate({"judgements": [], "assumptions": [], "gaps": [], "score": 7})


def test_evidence_text_flattens_structured_content() -> None:
    assert "Stop paying" in evidence_text({"strategy": {"message": "Stop paying wrong invoices"}, "n": 3})


def test_a_complete_honest_synthesis_passes() -> None:
    good = Judgement(questionId="CR01", channel="email", verdict="partly", reason="names the problem",
                     quotes=[QuoteOut(evidenceId=EV.evidenceId, quote="asset  TEXT")], fix="say it in AP terms")
    checks = synthesis_checks(Synthesis(judgements=_judgements(CR01=good), assumptions=[], gaps=[]), RUBRIC, [EV],
                              channels=CHANNELS)
    assert all(c.passed for c in checks), [c.reason for c in checks if not c.passed]


def test_a_quote_not_in_the_evidence_fails() -> None:
    bad = Judgement(questionId="CR01", channel="email", verdict="met", reason="r",
                    quotes=[QuoteOut(evidenceId=EV.evidenceId, quote="cuts invoice errors by 90%")], fix="f")
    checks = {c.name: c for c in synthesis_checks(Synthesis(judgements=_judgements(CR01=bad), assumptions=[],
                                                             gaps=[]), RUBRIC, [EV], channels=CHANNELS)}
    assert not checks["quotes"].passed and "CR01/email" in checks["quotes"].reason


def test_met_without_a_quote_fails() -> None:
    bare = Judgement(questionId="CR07", channel="", verdict="met", reason="r", quotes=[], fix="f")
    checks = {c.name: c for c in synthesis_checks(Synthesis(judgements=_judgements(CR07=bare), assumptions=[],
                                                             gaps=[]), RUBRIC, [EV], channels=CHANNELS)}
    assert not checks["verdict_support"].passed and "CR07" in checks["verdict_support"].reason


def test_every_question_judged_exactly_once() -> None:
    judged = _judgements()[1:]
    checks = {c.name: c for c in synthesis_checks(Synthesis(judgements=judged, assumptions=[], gaps=[]),
                                                  RUBRIC, [EV], channels=CHANNELS)}
    assert not checks["coverage"].passed and "missing CR01/email" in checks["coverage"].reason


def test_a_channel_question_must_be_judged_for_every_channel() -> None:
    judged = _judgements()  # judged for email only
    checks = {c.name: c for c in synthesis_checks(Synthesis(judgements=judged, assumptions=[], gaps=[]),
                                                  RUBRIC, [EV], channels=["email", "linkedin_ads"])}
    assert not checks["coverage"].passed and "CR01/linkedin_ads" in checks["coverage"].reason
    stray = Judgement(questionId="CR06", channel="email", verdict="unknown", reason="r", quotes=[], fix="f")
    checks = {c.name: c for c in synthesis_checks(Synthesis(judgements=[*_judgements(), stray], assumptions=[],
                                                            gaps=[]), RUBRIC, [EV], channels=CHANNELS)}
    assert not checks["coverage"].passed and "CR06/email" in checks["coverage"].reason


def test_unknown_evidence_ids_fail() -> None:
    ghost = Judgement(questionId="CR08", channel="", verdict="partly", reason="r",
                      quotes=[QuoteOut(evidenceId="ev_ghost", quote="x")], fix="f")
    checks = {c.name: c for c in synthesis_checks(Synthesis(judgements=_judgements(CR08=ghost), assumptions=[],
                                                             gaps=[]), RUBRIC, [EV], channels=CHANNELS)}
    assert not checks["evidence_ids"].passed and "ev_ghost" in checks["evidence_ids"].reason


def test_too_many_variants_fail() -> None:
    v = Variant(dimension="message", text="t", rationale="r", evidenceRefs=[EV.evidenceId], hypothesis="h")
    checks = {c.name: c for c in variants_checks(Variants(variants=[v] * 4), max_variants=3, evidence=[EV])}
    assert not checks["count"].passed
    assert all(c.passed for c in variants_checks(Variants(variants=[v]), max_variants=3, evidence=[EV]))


def test_a_quote_cut_short_with_an_added_full_stop_still_matches() -> None:
    from hipstraw_mm.campaign.llm_outputs import quote_found

    page = evidence(1).model_copy(update={"content": "Teams maintain the obligation continuously - across contracts."})
    assert quote_found("Teams maintain the obligation continuously.", page)
    assert quote_found("“maintain the obligation”", page)
    assert not quote_found("Teams maintain obligations continuously.", page)
