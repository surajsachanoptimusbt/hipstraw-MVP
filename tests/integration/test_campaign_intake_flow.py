"""T027: intake is traced in the campaign_manager layer and audited (constitution XII, HA C5)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hipstraw_mm.campaign.intake import submit_launch
from hipstraw_mm.campaign.models import AuditEvent
from hipstraw_mm.campaign.store import SqliteCampaignStore

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


def test_submit_writes_trace_steps_and_an_audit_event() -> None:
    store = SqliteCampaignStore(":memory:")
    launch_id = submit_launch(
        store, Path("config"), Path("tests/fixtures/campaign/launch_complete.yaml"),
        by="Demo Sponsor", role="sponsor", now=NOW,
    ).launchId

    steps = store.list_trace_steps(launch_id)
    assert [(s["layer"], s["actor"], s["operation"], s["right"]) for s in steps] == [
        ("campaign_manager", "launch_desk", "open_launch", "open_launch"),
        ("campaign_manager", "launch_desk", "propose_position", "propose_position"),
    ]
    assert all(s["status"] == "ok" for s in steps)
    assert steps[0]["inputs"]["file"].endswith("launch_complete.yaml")
    assert steps[0]["outputs"]["mandateVersion"] == 1 and steps[0]["outputs"]["evidence"] == 4
    assert steps[1]["outputs"]["positionVersion"] == 1
    assert steps[1]["decision"] == "proposed"

    events = store.list_for_launch(AuditEvent, launch_id)
    assert [(e.actor, e.role, e.action, e.outcome) for e in events] == [
        ("Demo Sponsor", "sponsor", "submit_launch", "allowed"),
    ]
    assert events[0].afterRef == f"pos_{launch_id}_v1"
