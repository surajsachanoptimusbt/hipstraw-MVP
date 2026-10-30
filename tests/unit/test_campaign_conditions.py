"""T032: facts computed from the head Position and mandate, and condition evaluation with reasons."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from hipstraw_mm.campaign.conditions import Check, Condition, compute_facts, evaluate
from hipstraw_mm.campaign.intake import submit_launch
from hipstraw_mm.campaign.store import SqliteCampaignStore

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
FIX = Path("tests/fixtures/campaign")


def _facts(name: str) -> dict[str, object]:
    store = SqliteCampaignStore(":memory:")
    launch_id = submit_launch(store, Path("config"), FIX / name, by="S", role="sponsor", now=NOW).launchId
    mandate, position = store.latest_mandate(launch_id), store.head_position(launch_id)
    assert mandate is not None and position is not None
    return compute_facts(mandate, position, NOW.date())


def test_facts_for_a_launch_ten_days_out() -> None:
    facts = _facts("launch_complete.yaml")
    assert facts == {
        "daysToDayZero": 10, "isLive": False, "hasMetrics": False, "openBlockers": 0,
        "openReadinessBlockers": 0, "unverifiedCoreAssumptions": 4, "contestedClaims": 0, "unknowns": 0,
        "openHypotheses": 0, "authorizedTestChannel": False, "testPlanBudgetSet": False,
    }


def test_facts_for_a_live_launch_with_metrics() -> None:
    facts = _facts("launch_live.yaml")
    assert facts["daysToDayZero"] == -12 and facts["isLive"] is True and facts["hasMetrics"] is True


def test_day_zero_today_counts_as_live() -> None:
    facts = _facts("launch_complete.yaml")
    assert facts["isLive"] is False
    store = SqliteCampaignStore(":memory:")
    launch_id = submit_launch(store, Path("config"), FIX / "launch_complete.yaml", by="S", role="sponsor",
                              now=NOW).launchId
    mandate, position = store.latest_mandate(launch_id), store.head_position(launch_id)
    assert mandate is not None and position is not None
    assert compute_facts(mandate, position, date(2026, 11, 11))["isLive"] is True


def test_missing_landing_page_counts_as_an_unknown() -> None:
    assert _facts("launch_missing_landing.yaml")["unknowns"] == 1


@pytest.mark.parametrize("combinator,expected", [("all", False), ("any", True)])
def test_all_and_any(combinator: str, expected: bool) -> None:
    checks = [Check(fact="daysToDayZero", op="<=", value=14), Check(fact="isLive", op="==", value=True)]
    holds, reasons = evaluate(Condition(**{combinator: checks}), {"daysToDayZero": 10, "isLive": False})
    assert holds is expected
    assert reasons == ["days to Day Zero = 10 (needs <= 14): met", "campaign is live = no (needs == yes): not met"]
