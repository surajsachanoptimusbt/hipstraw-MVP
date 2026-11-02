"""Live performance (Nov 2 meeting): daily metrics exports, M14's diagnosis against sourced benchmarks, the
Sponsor's applied change, and M11's before-and-after Delta, all through the governed operations."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from hipstraw_mm.campaign.intake import ingest_metrics, submit_launch
from hipstraw_mm.campaign.live import record_change
from hipstraw_mm.campaign.models import (
    AuditEvent,
    ChangeRecord,
    Delta,
    Direction,
    Escalation,
    EvidenceRecord,
    LineRun,
    ReviewRun,
)
from hipstraw_mm.campaign.performance import (
    channel_state,
    compute,
    daily_metrics,
    holds,
    load_performance_rules,
)
from hipstraw_mm.campaign.review import accept_review, review_finding, validate_review
from hipstraw_mm.campaign.runner import run_line
from hipstraw_mm.campaign.selection import choose_line, recommend_for_launch
from hipstraw_mm.campaign.simulation import write_export
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError, UsageError
from tests.unit.campaign_moves_support import CONFIG

LAUNCH = Path("input/campaign/simulations/kozmo_atlanta_it_services.yaml")
RULES = load_performance_rules(CONFIG)
CM = {"by": "Hipstraw CM", "role": "campaign_manager"}


def at(day: int, hour: int = 21) -> datetime:
    return datetime(2026, 11, 9 + day, hour, tzinfo=timezone.utc)  # day 1 is Day Zero, 2026-11-10


def launched(tmp_path: Path) -> tuple[SqliteCampaignStore, str]:
    store = SqliteCampaignStore(str(tmp_path / "c.db"))
    launch_id = submit_launch(store, CONFIG, LAUNCH, by="Kozmo GTM lead", role="sponsor", now=at(-2, 9)).launchId
    return store, launch_id


def export(store: SqliteCampaignStore, tmp_path: Path, launch_id: str, day: int,
           numbers: dict[str, dict[str, float]]) -> None:
    path = tmp_path / f"day{day}.csv"
    write_export(path, at(day).date(), numbers)
    ingest_metrics(store, CONFIG, launch_id, path, now=at(day), simulated=True, **CM)


def daily_review(store: SqliteCampaignStore, launch_id: str, day: int) -> ReviewRun:
    run = choose_line(store, CONFIG, launch_id, "L06", reason=f"day {day}", now=at(day, 22), **CM)
    run_line(store, CONFIG, run.lineRunId, now=at(day, 22), **CM)
    finished = store.get(LineRun, run.lineRunId)
    review = store.get(ReviewRun, finished.reviewId if finished else "")
    assert review is not None
    return review


def accept_all(store: SqliteCampaignStore, review: ReviewRun, day: int) -> ReviewRun:
    for f in review.findings:
        review_finding(store, CONFIG, review.reviewId, f.findingId, action="accept", reason="checked",
                       by="Hipstraw Reviewer", role="reviewer", now=at(day, 23))
    validate_review(store, CONFIG, review.reviewId, by="Hipstraw Reviewer", role="reviewer", now=at(day, 23))
    return accept_review(store, CONFIG, review.reviewId, by="Kozmo GTM lead", role="sponsor", now=at(day, 23))


BAD_EMAIL = {"email": {"sent": 1200, "delivered": 1160, "clicks": 12, "complaints": 6, "unsubscribes": 8,
                       "applications": 1, "qualified_applications": 1}}
LINKEDIN = {"impressions": 3600, "clicks": 21, "spend": 310.0, "applications": 0, "qualified_applications": 0,
            "frequency": 0.3}


# -- the rules ---------------------------------------------------------------------------------------------


def test_every_benchmark_and_rule_names_its_source() -> None:
    for channel, measures in RULES.measures.items():
        for name, d in measures.items():
            if d.benchmark is not None:
                assert d.benchmarkSource, f"{channel}.{name}"
    assert all(r.source and "PENDING" not in r.source for r in RULES.rules)
    assert [r.id for r in RULES.rules][:2] == ["DX01", "DX07"]  # delivery first, worn-out creative before weak copy


def test_measures_are_computed_from_counts_and_wait_for_enough_data() -> None:
    ctr = RULES.measures["linkedin_ads"]["ctr"]
    assert compute(ctr, [{"impressions": 1000, "clicks": 9}]).waiting == "not enough data yet: impressions 1000 of 2000"
    assert compute(ctr, [{"impressions": 1500, "clicks": 9}, {"impressions": 1500, "clicks": 6}]).value == 0.005
    spend = RULES.measures["linkedin_ads"]["daily_spend"]
    assert compute(spend, [{"spend": 100.0}, {"spend": 300.0}]).value == 200.0


def test_creative_fatigue_needs_a_fall_from_the_best_and_repeated_exposure() -> None:
    days = {date(2026, 11, d): {"impressions": 4000, "clicks": c, "frequency": f}
            for d, c, f in ((10, 24, 1.0), (11, 24, 1.5), (12, 24, 2.0), (13, 15, 2.6), (14, 12, 3.1), (15, 11, 3.5))}
    state = channel_state(RULES, "linkedin_ads", days, date(2026, 11, 15))
    fatigue = next(r for r in RULES.rules if r.id == "DX07")
    assert all(holds(c, state, RULES, {}) for c in fatigue.when)
    early = channel_state(RULES, "linkedin_ads", days, date(2026, 11, 13))
    assert not all(holds(c, early, RULES, {}) for c in fatigue.when)


# -- the metrics feed and the Sponsor's change -------------------------------------------------------------


def test_a_metrics_export_is_governed_evidence_labelled_simulated(tmp_path: Path) -> None:
    store, launch_id = launched(tmp_path)
    before = store.head_position(launch_id)
    export(store, tmp_path, launch_id, 1, BAD_EMAIL)
    metrics = [e for e in store.list_for_launch(EvidenceRecord, launch_id) if e.kind == "metric"]
    assert len(metrics) == 7 and all(e.source == "simulation" and "simulated" in e.uncertainty for e in metrics)
    assert daily_metrics(metrics)["email"][date(2026, 11, 10)]["complaints"] == 6
    assert store.head_position(launch_id) == before  # evidence only; a Line reads it
    with pytest.raises(PreconditionError, match="may not ingest_metrics"):
        ingest_metrics(store, CONFIG, launch_id, tmp_path / "day1.csv", by="R", role="reviewer", now=at(1))
    refused = [a for a in store.list_for_launch(AuditEvent, launch_id) if a.outcome == "refused"]
    assert refused and refused[-1].action == "ingest_metrics"


def test_the_daily_line_fits_only_a_live_launch_with_metrics(tmp_path: Path) -> None:
    store, launch_id = launched(tmp_path)
    excluded = {c.lineId for c in recommend_for_launch(store, CONFIG, launch_id, at(-2)).excluded}
    assert "L06" in excluded
    export(store, tmp_path, launch_id, 1, BAD_EMAIL)
    eligible = {c.lineId for c in recommend_for_launch(store, CONFIG, launch_id, at(1, 22)).eligible}
    assert "L06" in eligible


def test_a_delivery_defect_is_a_blocker_and_a_direction_with_its_measure(tmp_path: Path) -> None:
    store, launch_id = launched(tmp_path)
    export(store, tmp_path, launch_id, 1, {**BAD_EMAIL, "linkedin_ads": LINKEDIN})
    review = daily_review(store, launch_id, 1)
    kinds = [(f.kind, f.channel) for f in review.findings]
    assert ("blocker", "email") in kinds and ("proposal", "email") in kinds
    direction = next(f for f in review.findings if f.kind == "proposal" and f.channel == "email")
    assert direction.text.startswith("Direction: Email: Stop sending") and "Gmail's 0.30% limit" in direction.text
    [record] = store.list_for_launch(Direction, launch_id)
    assert (record.ruleId, record.measure, record.expected) == ("DX01", "complaint_rate", "decrease")
    assert record.baseline == pytest.approx(6 / 1160)
    gap = next(f for f in review.findings if f.kind == "gap")
    assert "LinkedIn ads cost per click" in gap.text and "no diagnosis rule reads this measure" in gap.text


def test_the_sponsor_applies_a_change_and_m11_measures_before_and_after(tmp_path: Path) -> None:
    store, launch_id = launched(tmp_path)
    export(store, tmp_path, launch_id, 1, BAD_EMAIL)
    accept_all(store, daily_review(store, launch_id, 1), 1)
    [direction] = store.list_for_launch(Direction, launch_id)
    with pytest.raises(PreconditionError, match="may not record_change"):
        record_change(store, CONFIG, launch_id, direction.hypothesisItemId, applied_on=date(2026, 11, 11),
                      what="cleaned", now=at(2, 8), **CM)
    with pytest.raises(UsageError, match="future"):
        record_change(store, CONFIG, launch_id, direction.hypothesisItemId, applied_on=date(2026, 11, 20),
                      what="cleaned", by="Kozmo GTM lead", role="sponsor", now=at(2, 8))
    record_change(store, CONFIG, launch_id, direction.hypothesisItemId, applied_on=date(2026, 11, 11),
                  what="List cleaned to opted-in contacts; one-click unsubscribe", by="Kozmo GTM lead",
                  role="sponsor", now=at(2, 8))
    review = accept_all(store, daily_review(store, launch_id, 2), 2)
    assert any(f.kind == "delta" and f.text.startswith("Change applied by the Sponsor") for f in review.findings)
    head = store.head_position(launch_id)
    assert head is not None
    assert next(i for i in head.items if i.itemId == direction.hypothesisItemId).state == "running"

    export(store, tmp_path, launch_id, 5, {"email": {"sent": 780, "delivered": 760, "clicks": 24, "complaints": 0,
                                                     "unsubscribes": 1, "applications": 3,
                                                     "qualified_applications": 2}})
    review = accept_all(store, daily_review(store, launch_id, 5), 5)  # 3 days after the change
    [delta] = store.list_for_launch(Delta, launch_id)
    assert (delta.measure, delta.result, delta.causal) == ("complaint_rate", "supported", False)
    assert delta.before == pytest.approx(6 / 1160) and delta.after == 0.0
    finding = next(f for f in review.findings if f.kind == "delta" and f.text.startswith("Delta"))
    assert "0.52% before" in finding.text and "0.00% since" in finding.text and "observational" in finding.text
    cleared = [f for f in review.findings if f.kind == "blocker" and f.text.startswith("Cleared")]
    assert cleared  # the complaint rate recovered, so the blocker clears
    assert len(store.list_for_launch(ChangeRecord, launch_id)) == 1


def test_m12_does_not_escalate_the_same_item_twice(tmp_path: Path) -> None:
    store, launch_id = launched(tmp_path)
    export(store, tmp_path, launch_id, 1, BAD_EMAIL)
    accept_all(store, daily_review(store, launch_id, 1), 1)
    export(store, tmp_path, launch_id, 2, {"linkedin_ads": LINKEDIN})
    accept_all(store, daily_review(store, launch_id, 2), 2)
    escalations = store.list_for_launch(Escalation, launch_id)
    refs = [r for e in escalations for r in e.itemRefs]
    assert len(refs) == len(set(refs))
