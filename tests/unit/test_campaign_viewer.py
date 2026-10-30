"""The read-only campaign page's data (Constitution XIII): what `campaign view` shows, read from a database
opened read-only, with no score anywhere."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from hipstraw_mm.campaign.intake import submit_launch
from hipstraw_mm.campaign.models import LineRun, ReviewRun
from hipstraw_mm.campaign.moves.common import PageRead
from hipstraw_mm.campaign.review import accept_review, review_finding, validate_review
from hipstraw_mm.campaign.rubric import load_rubric
from hipstraw_mm.campaign.runner import run_line
from hipstraw_mm.campaign.selection import choose_line
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.campaign.viewer import CampaignView
from tests.integration.test_campaign_line_run import _synthesis, _variants
from tests.unit.campaign_fake_model import CannedClient, CannedModels
from tests.unit.campaign_moves_support import CONFIG, FIX, NOW

CM = {"by": "Demo CM", "role": "campaign_manager", "now": NOW}
TODAY = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
CORRECTED = "The landing page and the ads make different offers."


def submitted(db: Path) -> tuple[SqliteCampaignStore, str]:
    store = SqliteCampaignStore(str(db))
    launch_id = submit_launch(store, CONFIG, FIX / "launch_complete.yaml", by="Demo Sponsor", role="sponsor",
                              now=NOW).launchId
    return store, launch_id


def reviewed(db: Path, *, accept: bool = True) -> str:
    """L02 with a canned model; the reviewer corrects CR04 for email to not met, then the Sponsor accepts."""
    store, launch_id = submitted(db)
    run = choose_line(store, CONFIG, launch_id, "L02", reason="core assumptions unverified", **CM)
    run_line(store, CONFIG, run.lineRunId, fetch=lambda url: PageRead(url=url, ok=True, text="LedgerLoop flags "
             "invoice errors before payment. Book a free 90-day invoice audit."),
             model=CannedModels(llm=CannedClient({"Synthesis": _synthesis, "Variants": _variants})), **CM)
    finished = store.get(LineRun, run.lineRunId)
    review = store.get(ReviewRun, finished.reviewId if finished else "")
    assert review is not None
    if not accept:
        return launch_id
    for f in review.findings:
        if (f.questionId, f.channel) == ("CR04", "email"):
            review_finding(store, CONFIG, review.reviewId, f.findingId, action="correct", text=CORRECTED,
                           verdict="not_met", reason="pages disagree", by="Demo Reviewer", role="reviewer", now=NOW)
        else:
            review_finding(store, CONFIG, review.reviewId, f.findingId, action="accept", reason="checked",
                           by="Demo Reviewer", role="reviewer", now=NOW)
    validate_review(store, CONFIG, review.reviewId, by="Demo Reviewer", role="reviewer", now=NOW)
    accept_review(store, CONFIG, review.reviewId, by="Demo Sponsor", role="sponsor", now=NOW)
    return launch_id


@pytest.fixture(scope="module")
def accepted(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """One reviewed launch for the tests that only read it."""
    db = tmp_path_factory.mktemp("viewer") / "c.db"
    return db, reviewed(db)


def view(db: Path) -> CampaignView:
    return CampaignView(str(db), CONFIG, now=lambda: TODAY)


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_launches_list_the_head_position(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    [row] = view(db).launches()
    assert row["launchId"] == launch_id and row["market"] == "US"
    assert row["positionVersion"] == 2 and row["positionState"] == "accepted"
    assert row["dayZero"] == view(db).launch(launch_id)["mandate"]["dayZero"]  # type: ignore[index]


def test_a_missing_database_shows_no_launches_until_one_is_submitted(tmp_path: Path) -> None:
    db = tmp_path / "later.db"
    page = view(db)
    assert page.launches() == [] and page.launch("lch_x") is None and not db.exists()
    submitted(db)
    assert len(page.launches()) == 1


def test_unknown_launch_is_none(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    submitted(db)
    assert view(db).launch("lch_nope") is None


def test_header_counts_day_zero_from_today(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    _, launch_id = submitted(db)
    shown = view(db).launch(launch_id)
    assert shown is not None
    day_zero = date.fromisoformat(shown["mandate"]["dayZero"])
    assert shown["mandate"]["daysToDayZero"] == (day_zero - TODAY.date()).days
    assert shown["head"] == {"version": 1, "state": "proposed"}
    assert shown["counts"]["openAssumptions"] == 4
    assert shown["scopeStatement"]
    assert shown["rubric"] is None  # nothing judged before L02 runs


def _row(rubric: dict[str, Any], question_id: str, channel: str | None) -> dict[str, Any]:
    return next(q for q in rubric["questions"] if (q["id"], q["channel"]) == (question_id, channel))


def test_rubric_shows_every_question_per_channel_with_the_reviewers_correction(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    rubric = view(db).launch(launch_id)["rubric"]  # type: ignore[index]
    assert rubric["version"] == "campaign-rubric.v0.2" and rubric["reviewState"] == "accepted"
    assert [(q["id"], q["channel"] or "") for q in rubric["questions"]] == load_rubric(CONFIG).expected(
        ["email", "linkedin_ads"])
    cr03 = _row(rubric, "CR03", "email")
    assert cr03["verdict"] == "partly" and cr03["reason"] == "offer is concrete; next step is clear"
    assert cr03["quotes"][0]["quote"] == "Book a free 90-day invoice audit" and cr03["correction"] is None
    assert cr03["channelName"] == "Email" and cr03["scope"] == "channel"
    cr04 = _row(rubric, "CR04", "email")
    assert cr04["verdict"] == "not_met" and cr04["reason"] == CORRECTED and cr04["reviewState"] == "corrected"
    assert cr04["correction"]["modelVerdict"] == "unknown"
    assert cr04["correction"]["by"] == "Demo Reviewer" and cr04["correction"]["reason"] == "pages disagree"
    assert cr04["question"].endswith("?") and cr04["met"] and cr04["notMet"]
    assert _row(rubric, "CR04", "linkedin_ads")["correction"] is None
    assert _row(rubric, "CR06", None)["scope"] == "campaign"


def test_each_channel_carries_its_audience_assets_answers_and_rules(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    store, launch_id = submitted(db)
    email, linkedin = view(db).launch(launch_id)["channels"]  # type: ignore[index]
    assert (email["channel"], email["name"], linkedin["name"]) == ("email", "Email", "LinkedIn ads")
    assert email["audience"].startswith("1,800 AP managers") and email["reach"]["fitsPoorly"]
    assert email["setup"]["consent"] == "opt_in" and email["setupLabels"]["consent"]
    [asset] = email["assets"]
    assert asset["fields"]["subject"] and asset["evidenceId"] and email["fieldLabels"]["subject"] == "Subject line"
    assert email["standards"] is None and email["verdicts"] == []  # nothing checked or judged yet
    run = choose_line(store, CONFIG, launch_id, "L01", reason="Day Zero close", **CM)
    run_line(store, CONFIG, run.lineRunId, **CM)
    email, linkedin = view(db).launch(launch_id)["channels"]  # type: ignore[index]
    assert {r["checkId"] for r in email["standards"]} >= {"EM01", "EM03", "EM07"}
    assert all(r["status"] == "met" for r in email["standards"] if r["level"] == "must")
    assert {r["checkId"] for r in linkedin["standards"]} >= {"LI01", "LI06"}
    assert email["counts"] == {"blockers": 0, "unknowns": 0, "fixes": 0}


def test_the_reviewer_desk_lists_what_awaits_a_decision(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    launch_id = reviewed(db, accept=False)
    [queued] = view(db).launch(launch_id)["desk"]["queue"]  # type: ignore[index]
    assert queued["state"] == "drafted" and queued["lineId"] == "L02" and queued["done"] == 0
    assert len(queued["pending"]) == queued["total"] and queued["pending"][0]["findingId"] == "F01"
    assert view(db).launch(launch_id)["desk"]["decisions"] == []  # type: ignore[index]


def test_the_desk_keeps_every_decision_after_acceptance(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    desk = view(db).launch(launch_id)["desk"]  # type: ignore[index]
    assert desk["queue"] == []
    corrected = [c for c in desk["decisions"] if c["action"] == "correct"]
    assert len(corrected) == 1 and corrected[0]["newVerdict"] == "not_met"
    assert corrected[0]["reason"] == "pages disagree"


def test_a_drafted_rubric_is_shown_as_awaiting_review(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    launch_id = reviewed(db, accept=False)
    rubric = view(db).launch(launch_id)["rubric"]  # type: ignore[index]
    assert rubric["reviewState"] == "drafted"
    assert {q["reviewState"] for q in rubric["questions"]} == {"pending"}


def test_position_history_lists_what_each_version_changed(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    positions = view(db).launch(launch_id)["positions"]  # type: ignore[index]
    assert [(p["version"], p["state"]) for p in positions] == [(1, "superseded"), (2, "accepted")]
    assert positions[0]["changes"] == []
    added = [c for c in positions[1]["changes"] if c["change"] == "added"]
    assert any(c["kind"] == "hypothesis" for c in added)


def test_line_runs_carry_the_tactic_record(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    [run] = view(db).launch(launch_id)["lineRuns"]  # type: ignore[index]
    assert run["lineId"] == "L02" and run["lineName"] and run["chosenBy"] == "Demo CM"
    assert run["reason"] == "core assumptions unverified" and run["state"] == "completed"
    assert [e["moveId"] for e in run["executions"]] == ["M02", "M06", "M07", "M09"]
    assert all(e["moveName"] and e["gate"] for e in run["executions"])
    assert {c["lineId"] for c in run["recommendation"]["excluded"]} >= {"L04"}


def test_reviews_carry_findings_and_corrections(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    [review] = view(db).launch(launch_id)["reviews"]  # type: ignore[index]
    assert review["state"] == "accepted" and review["committedPositionVersion"] == 2
    assert review["validatedBy"] == "Demo Reviewer" and review["decidedBy"] == "Demo Sponsor"
    corrected = [f for f in review["findings"] if f["reviewState"] == "corrected"]
    assert len(corrected) == 1 and corrected[0]["correction"]["newVerdict"] == "not_met"


def test_trace_lists_gate_decisions_and_model_calls(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    steps = view(db).trace(launch_id)
    assert [s["seq"] for s in steps] == sorted(s["seq"] for s in steps)
    assert any(s["operation"] == "check_authority" for s in steps)
    calls = [s for s in steps if s["operation"] == "call_model"]
    assert len(calls) == 2 and all(s["model"] for s in calls)
    blob = next((s["promptBlobId"] for s in calls if s["promptBlobId"]), None)
    if blob:
        assert view(db).blob(blob)["content"]  # type: ignore[index]
    assert view(db).trace("lch_nope") == []


def test_no_score_probability_or_forecast_field(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    keys = {k.lower() for k in _keys(view(db).launch(launch_id)) | _keys(view(db).launches())}
    for word in ("score", "probability", "forecast", "likelihood", "successrate"):
        assert not any(word in k for k in keys), word


def test_reading_never_changes_the_database(accepted: tuple[Path, str]) -> None:
    db, launch_id = accepted
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    page = view(db)
    page.launches(), page.launch(launch_id), page.trace(launch_id)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_the_read_only_connection_refuses_writes(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    _, launch_id = submitted(db)
    reader = SqliteCampaignStore.read_only(str(db))
    assert reader.latest_mandate(launch_id) is not None
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        reader.open_trace_run("lch_write_attempt")


def test_the_page_object_exposes_no_write_method() -> None:
    public = {name for name in dir(CampaignView) if not name.startswith("_")}
    assert public == {"launches", "launch", "trace", "blob", "standards"}


def test_a_review_judged_with_an_earlier_rubric_keeps_its_own_questions(tmp_path: Path) -> None:
    from hipstraw_mm.campaign.review import rubric_title

    db = tmp_path / "c.db"
    launch_id = reviewed(db)
    store = SqliteCampaignStore(str(db))
    review = next(r for r in store.list_for_launch(ReviewRun, launch_id))
    first = next(f for f in review.findings if f.kind == "rubric")
    old = first.model_copy(update={"text": "CR07 One story across assets: not met. Two offers.",
                                   "currentText": "CR07 One story across assets: not met. Two offers.",
                                   "questionId": "CR07", "channel": None})
    assert rubric_title(old) == "One story across assets"
    assert rubric_title(first) == "Message fits the audience"  # "(Email)" is the channel, not the title
    stamp = review.mechanismStamp.model_copy(update={"rubricVersion": "campaign-rubric.v0.1"})
    store.save(review.model_copy(update={"mechanismStamp": stamp, "findings": [old]}))
    rubric = view(db).launch(launch_id)["rubric"]  # type: ignore[index]
    assert (rubric["version"], rubric["current"]) == ("campaign-rubric.v0.1", False)
    assert [(q["id"], q["title"], q["reason"]) for q in rubric["questions"]] == [
        ("CR07", "One story across assets", "Two offers.")]
