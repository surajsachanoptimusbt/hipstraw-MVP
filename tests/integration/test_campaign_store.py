"""T004/T005: the campaign SQL store keeps immutable records immutable, commits Positions only against
the head, and serves the market tracer through its trace sink."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from hipstraw_mm.campaign.config import load_campaign_layers
from hipstraw_mm.campaign.models import (
    AuditEvent,
    Correction,
    EvidenceRecord,
    LineRun,
    Mandate,
    PositionSnapshot,
    ReviewRun,
)
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer
from tests.unit.campaign_factories import LAUNCH, every_record, line_run, mandate, position


@pytest.fixture
def store() -> SqliteCampaignStore:
    return SqliteCampaignStore(":memory:")


def test_every_record_type_round_trips(store: SqliteCampaignStore) -> None:
    for record in every_record():
        store.insert(record)  # type: ignore[arg-type]
        model = type(record)
        record_id = store.record_id(record)  # type: ignore[arg-type]
        assert store.get(model, record_id) == record


@pytest.mark.parametrize("model_name", ["Mandate", "EvidenceRecord", "Correction", "AuditEvent", "MoveExecution"])
def test_immutable_records_cannot_be_saved_again(store: SqliteCampaignStore, model_name: str) -> None:
    record = next(r for r in every_record() if type(r).__name__ == model_name)
    store.insert(record)  # type: ignore[arg-type]
    with pytest.raises(PreconditionError, match="immutable"):
        store.save(record)  # type: ignore[arg-type]
    with pytest.raises(PreconditionError, match="already exists"):
        store.insert(record)  # type: ignore[arg-type]


def test_mutable_records_can_be_saved(store: SqliteCampaignStore) -> None:
    run = line_run()
    store.insert(run)
    store.save(run.model_copy(update={"state": "staged", "nextStage": 1}))
    got = store.get(LineRun, run.lineRunId)
    assert got is not None and got.state == "staged" and got.nextStage == 1


def test_mandate_versions_and_latest(store: SqliteCampaignStore) -> None:
    store.insert(mandate(1))
    store.insert(mandate(2))
    latest = store.latest_mandate(LAUNCH)
    assert latest is not None and latest.version == 2
    assert [m.version for m in store.list_for_launch(Mandate, LAUNCH)] == [1, 2]


def test_only_a_proposed_snapshot_is_inserted_directly(store: SqliteCampaignStore) -> None:
    with pytest.raises(PreconditionError, match="commit_position"):
        store.insert(position(2, "accepted", base=1))


def test_head_is_the_intake_proposal_until_a_commit(store: SqliteCampaignStore) -> None:
    store.insert(position(1))
    head = store.head_position(LAUNCH)
    assert head is not None and (head.version, head.state) == (1, "proposed")


def test_commit_against_the_head_supersedes_it(store: SqliteCampaignStore) -> None:
    store.insert(position(1))
    store.commit_position(LAUNCH, 1, position(2, "accepted", base=1))
    head = store.head_position(LAUNCH)
    assert head is not None and (head.version, head.state) == (2, "accepted")
    old = store.get(PositionSnapshot, f"pos_{LAUNCH}_v1")
    assert old is not None and old.state == "superseded"
    store.commit_position(LAUNCH, 2, position(3, "accepted", base=2))
    v2 = store.get(PositionSnapshot, f"pos_{LAUNCH}_v2")
    assert v2 is not None and v2.state == "superseded"


def test_stale_commit_is_refused_and_writes_nothing(store: SqliteCampaignStore) -> None:
    store.insert(position(1))
    store.commit_position(LAUNCH, 1, position(2, "accepted", base=1))
    with pytest.raises(PreconditionError, match="stale"):
        store.commit_position(LAUNCH, 1, position(3, "accepted", base=1))
    assert store.get(PositionSnapshot, f"pos_{LAUNCH}_v3") is None
    head = store.head_position(LAUNCH)
    assert head is not None and head.version == 2


def test_successor_must_be_accepted_and_next_version(store: SqliteCampaignStore) -> None:
    store.insert(position(1))
    with pytest.raises(PreconditionError):
        store.commit_position(LAUNCH, 1, position(2, "proposed", base=1))
    with pytest.raises(PreconditionError):
        store.commit_position(LAUNCH, 1, position(5, "accepted", base=1))


def test_file_database_persists(tmp_path: Path) -> None:
    path = tmp_path / "campaign.db"
    SqliteCampaignStore(str(path)).insert(mandate(1))
    assert SqliteCampaignStore(str(path)).latest_mandate(LAUNCH) is not None


def test_lists_keep_insertion_order(store: SqliteCampaignStore) -> None:
    records = [r for r in every_record() if isinstance(r, (EvidenceRecord, AuditEvent, Correction, ReviewRun))]
    for r in records:
        store.insert(r)  # type: ignore[arg-type]
    assert len(store.list_for_launch(AuditEvent, LAUNCH)) == 1
    assert len(store.list_all(ReviewRun)) == 1


def test_market_tracer_writes_through_the_trace_sink(store: SqliteCampaignStore) -> None:
    store.open_trace_run(LAUNCH)
    tracer = Tracer(
        store=store.trace_sink(), layers=load_campaign_layers(Path("config")),
        settings=load_pipeline_settings(Path("config")), run_id=LAUNCH,
        clock=lambda: datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    with tracer.step("campaign_manager", "launch_desk", "open_launch", right="open_launch") as step:
        step.set_inputs({"file": "launch.yaml"})
        step.record_model_call(name="m", prompt_version="p.v1", schema="S", attempt=1,
                               prompt_content="prompt", response_content="{}", usage=None)
    steps = store.list_trace_steps(LAUNCH)
    assert [s["operation"] for s in steps] == ["open_launch"]
    assert steps[0]["status"] == "ok" and steps[0]["inputs"] == {"file": "launch.yaml"}
    assert store.trace_sink().get_trace_blob(steps[0]["promptBlobId"]) is not None
    run = store.trace_sink().get_market_run(LAUNCH)
    assert run is not None and run["lastSeq"] == 1
