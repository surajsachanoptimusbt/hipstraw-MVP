"""The governed campaign console (constitution XIII, v2.0.0): the approved actions, each the same governed
operation as its CLI command, so the authority gate, trace and audit apply as on the command line."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hipstraw_mm.campaign.console import ACTIONS, CampaignConsole, ConsoleError
from hipstraw_mm.campaign.intake import submit_launch, submit_launch_data
from hipstraw_mm.campaign.models import AuditEvent, Correction, PositionSnapshot, ReviewRun
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError, UsageError
from tests.unit.campaign_moves_support import CONFIG, FIX, NOW
from tests.unit.test_campaign_viewer import reviewed

SPONSOR = {"by": "Kozmo GTM lead", "role": "sponsor"}
REVIEWER = {"by": "Hipstraw Reviewer", "role": "reviewer"}


def _raw(name: str = "launch_complete.yaml") -> dict:  # type: ignore[type-arg]
    return yaml.safe_load((FIX / name).read_text(encoding="utf-8"))


def console(db: Path) -> CampaignConsole:
    return CampaignConsole(str(db), CONFIG, now=lambda: NOW)


def test_only_the_approved_actions_exist() -> None:
    assert set(ACTIONS) == {"submit", "finding", "validate", "decide"}
    public = {n for n in dir(CampaignConsole) if not n.startswith("_")}
    assert public == {"act", "examples", "roles"}  # no Line choice, no run, no dispatch


def test_a_submission_as_data_is_the_same_launch_as_the_file() -> None:
    by_file, by_data = SqliteCampaignStore(":memory:"), SqliteCampaignStore(":memory:")
    a = submit_launch(by_file, CONFIG, FIX / "launch_complete.yaml", by="S", role="sponsor", now=NOW)
    b = submit_launch_data(by_data, CONFIG, _raw(), source="console form", by="S", role="sponsor", now=NOW)
    pa, pb = by_file.head_position(a.launchId), by_data.head_position(b.launchId)
    assert pa is not None and pb is not None
    assert [(i.itemId, i.kind, i.text) for i in pa.items] == [(i.itemId, i.kind, i.text) for i in pb.items]
    [step] = [s for s in by_data.list_trace_steps(b.launchId) if s["operation"] == "open_launch"]
    assert step["inputs"]["file"] == "console form" and len(step["inputs"]["sha256"]) == 64


def test_a_metrics_export_still_comes_as_a_file() -> None:
    raw = _raw("launch_live.yaml")
    with pytest.raises(UsageError, match="metrics export"):
        submit_launch_data(SqliteCampaignStore(":memory:"), CONFIG, raw, source="console form", by="S",
                           role="sponsor", now=NOW)


def test_the_console_submits_through_the_gate_and_audits(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    out = console(db).act("submit", {"launch": _raw(), **SPONSOR})
    store = SqliteCampaignStore(str(db))
    assert out["positionVersion"] == 1 and store.head_position(out["launchId"]) is not None
    events = store.list_for_launch(AuditEvent, out["launchId"])
    assert [(e.action, e.actor, e.outcome) for e in events] == [("submit_launch", "Kozmo GTM lead", "allowed")]


def test_a_role_without_the_right_is_refused_and_the_refusal_audited(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    with pytest.raises(PreconditionError, match="may not submit_launch"):
        console(db).act("submit", {"launch": _raw(), **REVIEWER})
    refused = [e for e in SqliteCampaignStore(str(db)).list_all(AuditEvent) if e.outcome == "refused"]
    assert len(refused) == 1 and refused[0].actor == "Hipstraw Reviewer"


def test_the_reviewer_and_the_sponsor_decide_in_the_console(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    launch_id = reviewed(db, accept=False)
    store = SqliteCampaignStore(str(db))
    review = store.list_for_launch(ReviewRun, launch_id)[0]
    page = console(db)
    with pytest.raises(PreconditionError, match="may not review_finding"):
        page.act("finding", {"reviewId": review.reviewId, "findingId": "F01", "action": "accept", "reason": "ok",
                             **SPONSOR})
    first, *rest = review.findings
    out = page.act("finding", {"reviewId": review.reviewId, "findingId": first.findingId, "action": "correct",
                               "text": "Two different offers.", "verdict": "not_met", "reason": "pages disagree",
                               **REVIEWER})
    assert out["reviewState"] == "corrected"
    for f in rest:
        page.act("finding", {"reviewId": review.reviewId, "findingId": f.findingId, "action": "accept",
                             "reason": "checked", **REVIEWER})
    assert page.act("validate", {"reviewId": review.reviewId, **REVIEWER})["state"] == "validated"
    decided = page.act("decide", {"reviewId": review.reviewId, "decision": "accept", **SPONSOR})
    assert decided == {"reviewId": review.reviewId, "state": "accepted", "positionVersion": 2}
    store = SqliteCampaignStore(str(db))
    assert store.get(PositionSnapshot, f"pos_{launch_id}_v2") is not None
    [correction] = [c for c in store.list_for_launch(Correction, launch_id) if c.action == "correct"]
    assert (correction.by, correction.newVerdict, correction.reason) == ("Hipstraw Reviewer", "not_met",
                                                                         "pages disagree")


@pytest.mark.parametrize("body, message", [
    ({"reviewId": "r", "findingId": "F01", "action": "approve", "reason": "x"}, "action must be"),
    ({"reviewId": "r", "findingId": "F01", "action": "correct", "verdict": "great", "reason": "x"}, "verdict must"),
    ({"reviewId": "r", "findingId": "F01", "action": "accept"}, "reason is required"),
])
def test_requests_are_checked_before_anything_runs(tmp_path: Path, body: dict, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(UsageError, match=message):
        console(tmp_path / "c.db").act("finding", {**body, **REVIEWER})


def test_an_unknown_action_or_a_missing_actor_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConsoleError, match="unknown action"):
        console(tmp_path / "c.db").act("run_line", {**REVIEWER})
    with pytest.raises(UsageError, match="by is required"):
        console(tmp_path / "c.db").act("validate", {"reviewId": "r", "role": "reviewer"})


def test_the_form_can_start_from_the_scenarios(tmp_path: Path) -> None:
    examples = console(tmp_path / "c.db").examples()
    assert [e["name"] for e in examples] == ["kozmo_email_us.yaml", "kozmo_three_channels_us.yaml"]
    assert examples[0]["launch"]["dayZero"] == "2026-11-10"  # dates as text, ready for the form
