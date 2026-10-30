"""T058/T059: Review assembly from a Line run, and the review queue (US3 end, US4)."""

from __future__ import annotations

import pytest

from hipstraw_mm.campaign.models import AuditEvent, Correction, LineRun, PositionSnapshot, ReviewRun
from hipstraw_mm.campaign.moves.common import PageRead
from hipstraw_mm.campaign.review import accept_review, reject_review, review_finding, validate_review
from hipstraw_mm.campaign.runner import deviate, run_line, stop_line
from hipstraw_mm.campaign.selection import choose_line
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError
from tests.unit.campaign_moves_support import CONFIG, NOW, launch

CM = {"by": "Demo CM", "role": "campaign_manager", "now": NOW}
REVIEWER = {"by": "Demo Reviewer", "role": "reviewer", "now": NOW}
SPONSOR = {"by": "Demo Sponsor", "role": "sponsor", "now": NOW}


def _reviewed_l01(name: str = "launch_missing_landing.yaml") -> tuple[SqliteCampaignStore, str, ReviewRun]:
    store, launch_id = launch(name)
    run = choose_line(store, CONFIG, launch_id, "L01", reason="Day Zero close", **CM)
    run_line(store, CONFIG, run.lineRunId, **CM)
    finished = store.get(LineRun, run.lineRunId)
    assert finished is not None and finished.reviewId is not None
    review = store.get(ReviewRun, finished.reviewId)
    assert review is not None
    return store, launch_id, review


# -- assembly (T058) -----------------------------------------------------------------------------------


def test_l01_review_is_drafted_with_findings_from_the_moves() -> None:
    store, launch_id, review = _reviewed_l01()
    assert review.state == "drafted" and review.basePositionVersion == 1
    assert "does not run campaigns" in review.scopeStatement
    assert review.mechanismStamp.criteriaVersion == "readiness-criteria.v0.2"
    kinds = [(f.kind, f.sourceMove) for f in review.findings]
    assert ("blocker", "M04") in kinds and ("escalation", "M12") in kinds
    blocker = next(f for f in review.findings if f.kind == "blocker")
    assert blocker.area == "readiness" and "Landing page" in blocker.text and blocker.itemRefs
    assert all(f.reviewState == "pending" and f.uncertainty for f in review.findings)
    assert all(f.evidenceRefs or f.itemRefs for f in review.findings)
    assert [f.findingId for f in review.findings] == [f"F{n:02d}" for n in range(1, len(review.findings) + 1)]


def test_open_items_already_in_the_position_are_reported_too() -> None:
    _, _, review = _reviewed_l01()
    unknown = [f for f in review.findings if f.kind == "unknown"]
    assert unknown and "Landing page not provided" in unknown[0].text and unknown[0].sourceMove is None


def test_the_proposed_successor_is_the_working_position() -> None:
    _, _, review = _reviewed_l01()
    blockers = [i for i in review.proposedItems if i.kind == "blocker"]
    assert [b.key for b in blockers] == ["RC01"]


def test_a_stopped_line_drafts_a_review_on_what_ran() -> None:
    store, launch_id = launch()
    run = choose_line(store, CONFIG, launch_id, "L01", reason="x", **CM)
    deviate(store, CONFIG, run.lineRunId, skip="M01", reason="assets already checked", **CM)
    stopped = stop_line(store, CONFIG, run.lineRunId, reason="Sponsor paused", **CM)
    review = store.get(ReviewRun, stopped.reviewId or "")
    assert review is not None and review.state == "drafted"


# -- queue (T059) --------------------------------------------------------------------------------------


def test_correct_keeps_the_original_and_the_reason() -> None:
    store, launch_id, review = _reviewed_l01()
    review = review_finding(store, CONFIG, review.reviewId, "F01", action="correct",
                            text="Landing page exists but is not linked from the ads", reason="checked with the team",
                            **REVIEWER)
    f01 = review.findings[0]
    assert f01.reviewState == "corrected" and f01.currentText.startswith("Landing page exists")
    assert f01.text != f01.currentText
    corrections = store.list_for_launch(Correction, launch_id)
    assert [(c.action, c.originalText, c.reason) for c in corrections] == [
        ("correct", f01.text, "checked with the team")]


def test_validate_is_refused_while_a_finding_is_pending() -> None:
    store, _, review = _reviewed_l01()
    with pytest.raises(PreconditionError, match="pending"):
        validate_review(store, CONFIG, review.reviewId, **REVIEWER)


def test_accept_before_validate_is_refused() -> None:
    store, _, review = _reviewed_l01()
    with pytest.raises(PreconditionError, match="drafted"):
        accept_review(store, CONFIG, review.reviewId, **SPONSOR)


def test_reviewer_cannot_accept() -> None:
    store, _, review = _reviewed_l01()
    with pytest.raises(PreconditionError, match="accept_review"):
        accept_review(store, CONFIG, review.reviewId, **REVIEWER)


def test_sponsor_cannot_review_findings() -> None:
    store, _, review = _reviewed_l01()
    with pytest.raises(PreconditionError, match="review_finding"):
        review_finding(store, CONFIG, review.reviewId, "F01", action="accept", reason="x", **SPONSOR)


def _validated(store: SqliteCampaignStore, review: ReviewRun, reject: str | None = None) -> ReviewRun:
    for f in review.findings:
        action = "reject" if f.findingId == reject else "accept"
        review = review_finding(store, CONFIG, review.reviewId, f.findingId, action=action, reason="checked",
                                **REVIEWER)
    return validate_review(store, CONFIG, review.reviewId, **REVIEWER)


def test_accept_commits_the_successor_and_supersedes_the_base() -> None:
    store, launch_id, review = _reviewed_l01()
    validated = _validated(store, review)
    assert validated.state == "validated" and validated.validatedBy == "Demo Reviewer"
    accepted = accept_review(store, CONFIG, review.reviewId, reason="agreed", **SPONSOR)
    assert accepted.state == "accepted" and accepted.committedPositionVersion == 2
    head = store.head_position(launch_id)
    assert head is not None and (head.version, head.state, head.origin) == (2, "accepted", review.reviewId)
    assert any(i.kind == "blocker" and i.key == "RC01" for i in head.items)
    v1 = store.get(PositionSnapshot, f"pos_{launch_id}_v1")
    assert v1 is not None and v1.state == "superseded"
    actions = [(e.action, e.role) for e in store.list_for_launch(AuditEvent, launch_id)]
    assert ("validate_review", "reviewer") in actions and ("accept_review", "sponsor") in actions
    ops = [s["operation"] for s in store.list_trace_steps(launch_id)]
    assert "commit_position" in ops


def test_a_rejected_finding_is_left_out_of_the_successor() -> None:
    store, launch_id, review = _reviewed_l01()
    blocker = next(f for f in review.findings if f.kind == "blocker")
    _validated(store, review, reject=blocker.findingId)
    accept_review(store, CONFIG, review.reviewId, **SPONSOR)
    head = store.head_position(launch_id)
    assert head is not None and not any(i.kind == "blocker" for i in head.items)


def test_a_second_review_on_the_old_base_is_refused_as_stale() -> None:
    store, launch_id, review = _reviewed_l01()
    second_run = choose_line(store, CONFIG, launch_id, "L05", reason="unknowns", **CM)
    run_line(store, CONFIG, second_run.lineRunId, fetch=lambda url: PageRead(url=url, ok=False, reason="offline"),
             **CM)
    second = store.get(ReviewRun, store.get(LineRun, second_run.lineRunId).reviewId)  # type: ignore[union-attr,arg-type]
    assert second is not None and second.basePositionVersion == 1
    _validated(store, review)
    accept_review(store, CONFIG, review.reviewId, **SPONSOR)
    _validated(store, second)
    with pytest.raises(PreconditionError, match="stale"):
        accept_review(store, CONFIG, second.reviewId, **SPONSOR)
    still = store.get(ReviewRun, second.reviewId)
    assert still is not None and still.state == "validated"


def test_reject_closes_the_review_and_keeps_the_position() -> None:
    store, launch_id, review = _reviewed_l01()
    _validated(store, review)
    rejected = reject_review(store, CONFIG, review.reviewId, reason="re-run after the new brief", **SPONSOR)
    assert rejected.state == "rejected" and rejected.decisionReason == "re-run after the new brief"
    head = store.head_position(launch_id)
    assert head is not None and head.version == 1


def _l02_review() -> tuple[SqliteCampaignStore, str, ReviewRun]:
    from tests.integration.test_campaign_line_run import _synthesis, _variants
    from tests.unit.campaign_fake_model import CannedClient, CannedModels

    store, launch_id = launch()
    run = choose_line(store, CONFIG, launch_id, "L02", reason="x", **CM)
    run_line(store, CONFIG, run.lineRunId, fetch=lambda url: PageRead(url=url, ok=True, text="Book a free 90-day "
             "invoice audit."), model=CannedModels(llm=CannedClient({"Synthesis": _synthesis,
                                                                      "Variants": _variants})), **CM)
    finished = store.get(LineRun, run.lineRunId)
    review = store.get(ReviewRun, finished.reviewId if finished else "")
    assert review is not None
    return store, launch_id, review


def test_a_reviewer_can_correct_a_rubric_verdict() -> None:
    store, launch_id, review = _l02_review()
    cr03 = next(f for f in review.findings if f.questionId == "CR03" and f.channel == "email")
    review = review_finding(store, CONFIG, review.reviewId, cr03.findingId, action="correct", verdict="not_met",
                            text="Two different offers.", reason="pages disagree", **REVIEWER)
    corrected = next(f for f in review.findings if f.findingId == cr03.findingId)
    assert (corrected.verdict, corrected.reviewState) == ("not_met", "corrected")
    correction = store.list_for_launch(Correction, launch_id)[-1]
    assert (correction.originalVerdict, correction.newVerdict) == ("partly", "not_met")


def test_a_verdict_belongs_only_to_rubric_findings() -> None:
    from hipstraw_mm.errors import UsageError

    store, _, review = _reviewed_l01()
    with pytest.raises(UsageError, match="rubric"):
        review_finding(store, CONFIG, review.reviewId, "F01", action="correct", verdict="met", text="x",
                       reason="x", **REVIEWER)


def test_only_moves_that_called_a_model_are_stamped() -> None:
    _, _, review = _l02_review()
    assert review.mechanismStamp.promptVersions == ["campaign_synthesis.v2", "campaign_variants.v1"]
