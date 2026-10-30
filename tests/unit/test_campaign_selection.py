"""T033/T034: Line recommendation from typed facts, and the human choice that opens the tactic record."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from hipstraw_mm.campaign import moves
from hipstraw_mm.campaign.conditions import compute_facts
from hipstraw_mm.campaign.intake import submit_launch
from hipstraw_mm.campaign.models import AuditEvent, LineRun, PositionItem
from hipstraw_mm.campaign.repertoire import load_repertoire
from hipstraw_mm.campaign.selection import choose_line, recommend_lines
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError, UsageError

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
FIX = Path("tests/fixtures/campaign")
CONFIG = Path("config")
REP = load_repertoire(CONFIG)


def _launch(name: str = "launch_complete.yaml") -> tuple[SqliteCampaignStore, str]:
    store = SqliteCampaignStore(":memory:")
    return store, submit_launch(store, CONFIG, FIX / name, by="S", role="sponsor", now=NOW).launchId


def _recommend(name: str) -> tuple[set[str], set[str], dict[str, list[str]]]:
    store, launch_id = _launch(name)
    mandate, position = store.latest_mandate(launch_id), store.head_position(launch_id)
    assert mandate is not None and position is not None
    rec = recommend_lines(REP, compute_facts(mandate, position, NOW.date()), position.version)
    reasons = {c.lineId: c.reasons for c in [*rec.eligible, *rec.excluded]}
    return {c.lineId for c in rec.eligible}, {c.lineId for c in rec.excluded}, reasons


def test_ten_days_out_without_test_channels() -> None:
    eligible, excluded, reasons = _recommend("launch_complete.yaml")
    assert eligible == {"L01", "L02"}
    assert excluded == {"L03", "L04", "L05"}
    assert any("authorized test channel" in r for r in reasons["L03"])
    assert any("live" in r for r in reasons["L04"])
    assert any("days to Day Zero = 10" in r for r in reasons["L01"])


def test_live_launch_with_metrics() -> None:
    eligible, excluded, reasons = _recommend("launch_live.yaml")
    assert "L04" in eligible and "L01" in excluded
    assert any("live" in r for r in reasons["L01"])


def test_unknowns_make_contested_evidence_eligible() -> None:
    eligible, _, _ = _recommend("launch_missing_landing.yaml")
    assert "L05" in eligible


def test_a_contested_claim_makes_contested_evidence_eligible() -> None:
    store, launch_id = _launch()
    mandate, position = store.latest_mandate(launch_id), store.head_position(launch_id)
    assert mandate is not None and position is not None
    contested = PositionItem(itemId="C99", kind="claim", area="strategy", text="Audience disputed",
                             state="contested", evidenceRefs=["ev_x"], setBy="M02")
    position = position.model_copy(update={"items": [*position.items, contested]})
    rec = recommend_lines(REP, compute_facts(mandate, position, NOW.date()), position.version)
    assert "L05" in {c.lineId for c in rec.eligible}


def test_choice_opens_the_tactic_record() -> None:
    store, launch_id = _launch()
    run = choose_line(store, CONFIG, launch_id, "L01", by="Demo CM", role="campaign_manager",
                      reason="Day Zero in 10 days", now=NOW)
    stored = store.get(LineRun, run.lineRunId)
    assert stored == run
    assert run.lineRunId == f"lrun_{launch_id}_1"
    assert (run.lineId, run.lineVersion, run.repertoireVersion) == ("L01", 2, "campaign-repertoire.v0.2")
    assert (run.chosenBy, run.chosenRole, run.reason, run.chosenAt) == (
        "Demo CM", "campaign_manager", "Day Zero in 10 days", NOW.isoformat())
    assert run.state == "opened" and run.nextStage == 0 and run.basePositionVersion == 1
    assert run.plannedStages == [["M01"], ["M04", "M05", "M13"], ["M12"]]
    assert {c.lineId for c in run.recommendation.eligible} == {"L01", "L02"}
    events = [e for e in store.list_for_launch(AuditEvent, launch_id) if e.action == "choose_line"]
    assert len(events) == 1 and events[0].afterRef == run.lineRunId and events[0].reason == "Day Zero in 10 days"
    ops = [s["operation"] for s in store.list_trace_steps(launch_id)]
    assert ops[-2:] == ["recommend_lines", "choose_line"]


def test_an_excluded_line_cannot_be_chosen() -> None:
    store, launch_id = _launch()
    with pytest.raises(PreconditionError, match="L04.*excluded.*live"):
        choose_line(store, CONFIG, launch_id, "L04", by="Demo CM", role="campaign_manager", reason="x", now=NOW)


def test_unknown_line() -> None:
    store, launch_id = _launch()
    with pytest.raises(UsageError, match="L77"):
        choose_line(store, CONFIG, launch_id, "L77", by="Demo CM", role="campaign_manager", reason="x", now=NOW)


def test_a_line_with_a_withdrawn_handler_cannot_be_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    store, launch_id = _launch()
    handlers = dict(moves.HANDLERS)
    handlers.pop("readiness.day_zero_dependencies")
    monkeypatch.setattr(moves, "HANDLERS", handlers)
    with pytest.raises(PreconditionError, match="M05.*withdrawn"):
        choose_line(store, CONFIG, launch_id, "L01", by="Demo CM", role="campaign_manager", reason="x", now=NOW,
                    repertoire=REP)


def test_only_the_campaign_manager_chooses() -> None:
    store, launch_id = _launch()
    with pytest.raises(PreconditionError, match="choose_line"):
        choose_line(store, CONFIG, launch_id, "L01", by="Demo Sponsor", role="sponsor", reason="x", now=NOW)
