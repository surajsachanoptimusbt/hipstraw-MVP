"""T039/T042: M04 and M05 are deterministic checks against config/campaign/criteria.yaml."""

from __future__ import annotations

from datetime import date

from hipstraw_mm.campaign.moves.readiness import CRITERION_CHECKS, RULE_CHECKS, load_criteria
from tests.unit.campaign_moves_support import CONFIG, context, item, launch, run


def test_criteria_load_and_every_check_exists() -> None:
    criteria = load_criteria(CONFIG)
    assert criteria.version == "readiness-criteria.v0.2"
    assert {c.check for c in criteria.criteria} <= set(CRITERION_CHECKS)
    assert {r.check for r in criteria.dependencyRules} <= set(RULE_CHECKS)


def test_complete_launch_opens_no_blocker() -> None:
    store, launch_id = launch()
    out = run(context(store, launch_id, "M04"))
    assert out.status == "succeeded" and out.newItems == [] and out.transitions == []


def test_missing_landing_page_opens_a_readiness_blocker() -> None:
    store, launch_id = launch("launch_missing_landing.yaml")
    out = run(context(store, launch_id, "M04"))
    blockers = [i for i in out.newItems if i.kind == "blocker"]
    assert [(b.key, b.state, b.area, b.setBy) for b in blockers] == [("RC01", "open", "readiness", "M04")]
    assert "Landing page" in blockers[0].text and blockers[0].evidenceRefs


def test_a_blocker_clears_once_the_criterion_is_met() -> None:
    store, launch_id = launch()
    position = store.head_position(launch_id)
    assert position is not None
    open_blocker = item("B01", "blocker", "open", "Landing page address given: not met", area="readiness", key="RC01")
    out = run(context(store, launch_id, "M04", items=[*position.items, open_blocker]))
    assert [(t.itemId, t.fromState, t.toState) for t in out.transitions] == [("B01", "open", "cleared")]
    assert out.newItems == []


def test_an_open_blocker_is_not_opened_twice() -> None:
    store, launch_id = launch("launch_missing_landing.yaml")
    position = store.head_position(launch_id)
    assert position is not None
    existing = item("B01", "blocker", "open", "Landing page", area="readiness", key="RC01")
    out = run(context(store, launch_id, "M04", items=[*position.items, existing]))
    assert out.newItems == [] and out.transitions == []


def test_assets_ready_on_time_open_no_dependency_blocker() -> None:
    store, launch_id = launch()
    out = run(context(store, launch_id, "M05"))
    assert out.newItems == []


def test_an_asset_ready_inside_the_lead_time_opens_a_blocker() -> None:
    store, launch_id = launch()
    mandate = store.latest_mandate(launch_id)
    assert mandate is not None
    late = [a.model_copy(update={"readyDate": date(2026, 11, 10)}) if a.kind == "ad_copy" else a
            for a in mandate.assets]
    out = run(context(store, launch_id, "M05", mandate=mandate.model_copy(update={"assets": late})))
    blockers = [i for i in out.newItems if i.kind == "blocker"]
    assert [b.key for b in blockers] == ["DZ02:A3"]
    assert "2026-11-10" in blockers[0].text and "2026-11-08" in blockers[0].text
