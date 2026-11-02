"""The live campaign simulation end to end (Nov 2 meeting): 14 simulated days of the Atlanta IT-services
campaign through the daily review, with the walk-through Ashish asked for. Each problem the scenario holds is
found from the numbers alone, the Sponsor applies the direction, and the Delta shows what changed."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hipstraw_mm.campaign.models import Delta, Direction, EvidenceRecord
from hipstraw_mm.campaign.report import render_report
from hipstraw_mm.campaign.simulation import SimulationResult, run_simulation
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.campaign.viewer import CampaignView
from tests.unit.campaign_moves_support import CONFIG

SCENARIO = Path("input/campaign/simulations/kozmo_atlanta_14_days.yaml")


@pytest.fixture(scope="module")
def simulated(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, SimulationResult]]:
    root = tmp_path_factory.mktemp("sim")
    store = SqliteCampaignStore(str(root / "c.db"))
    result = run_simulation(store, CONFIG, SCENARIO, exports_dir=root / "exports")
    store.close()
    yield root, result


def test_each_problem_is_found_and_each_change_is_measured(simulated: tuple[Path, SimulationResult]) -> None:
    root, result = simulated
    store = SqliteCampaignStore(str(root / "c.db"))
    found = {(d.ruleId, d.cause) for d in store.list_for_launch(Direction, result.launchId)}
    assert found == {("DX01", "complaint_rate"), ("DX05", "audience_mismatch"), ("DX04", "landing_mismatch"),
                     ("DX07", "creative_fatigue")}
    deltas = {d.measure: d for d in store.list_for_launch(Delta, result.launchId)}
    assert {m: d.result for m, d in deltas.items()} == {
        "complaint_rate": "supported", "cost_per_qualified": "supported", "conversion_rate": "supported",
        "ctr": "supported"}
    assert all(d.causal is False and d.attributionNotes.startswith("observational") for d in deltas.values())
    assert "also changed in the same days" in deltas["complaint_rate"].attributionNotes  # named, not hidden


def test_the_walk_through_reads_day_by_day(simulated: tuple[Path, SimulationResult]) -> None:
    _, result = simulated
    first = {e.kind: e.day for e in reversed(result.events)}
    assert first["submitted"] == -2 and first["direction"] == 1 and first["applied"] == 2
    assert [e.day for e in result.events if e.kind == "delta"] == [5, 5, 6, 13]
    gaps = [e.text for e in result.events if e.kind == "gap"]
    assert gaps and all("no diagnosis rule reads this measure" in g for g in gaps)
    blockers = [e.text for e in result.events if e.kind == "blocker"]
    assert blockers[0].startswith("Email: spam complaint rate") and blockers[-1].startswith("Cleared: Email")


def test_every_metric_says_it_is_simulated(simulated: tuple[Path, SimulationResult]) -> None:
    root, result = simulated
    store = SqliteCampaignStore(str(root / "c.db"))
    metrics = [e for e in store.list_for_launch(EvidenceRecord, result.launchId) if e.kind == "metric"]
    assert metrics and all(e.source == "simulation" and "simulated" in e.uncertainty for e in metrics)
    assert all(str(e.content["definition"]).startswith("SIMULATED") for e in metrics)  # type: ignore[index]


def test_the_page_and_the_report_show_the_live_campaign(simulated: tuple[Path, SimulationResult]) -> None:
    root, result = simulated
    performance = CampaignView(str(root / "c.db"), CONFIG).launch(result.launchId)["performance"]  # type: ignore[index]
    assert performance["simulated"] is True and len(performance["days"]) == 14
    assert {c["channel"] for c in performance["channels"]} == {"email", "linkedin_ads", "instagram_ads"}
    instagram = next(c for c in performance["channels"] if c["channel"] == "instagram_ads")
    assert instagram["stopped"] is True  # paused on day 2, its budget moved to LinkedIn
    assert {e["kind"] for e in performance["events"]} == {"direction", "applied", "delta", "gap"}
    store = SqliteCampaignStore(str(root / "c.db"))
    record = render_report(store, CONFIG, result.launchId, datetime(2026, 11, 24, tzinfo=timezone.utc),
                           root / "report.md")
    text = (root / "report.md").read_text(encoding="utf-8")
    assert record.positionVersion > 10 and "## Live performance" in text and "**Simulation:**" in text
    assert "| 2026-11-10 | Instagram ads |" in text
