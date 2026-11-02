"""Changes applied to a live campaign (Nov 2 meeting: give a running campaign direction, then show what the
change did). Hipstraw dispatches nothing in G0: the Sponsor applies a recommended change on their own
platform and records here that, and when, it was applied. M11 then compares the direction's measure over the
days before with the days since. The record changes no Position item itself; the next Review does.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from hipstraw_mm.campaign.audit import record_audit
from hipstraw_mm.campaign.config import load_roles
from hipstraw_mm.campaign.gate import authorize
from hipstraw_mm.campaign.models import ChangeRecord
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.errors import PreconditionError, UsageError

APPLICABLE = ("proposed", "planned", "running")


def record_change(store: CampaignStore, config_dir: Path, launch_id: str, hypothesis_item_id: str, *,
                  applied_on: date, what: str, by: str, role: str, now: datetime) -> ChangeRecord:
    at = now.isoformat()
    authorize(store, load_roles(config_dir), launch_id=launch_id, actor=by, role=role, action="record_change",
              at=at)
    if not what.strip():
        raise UsageError("say what was changed")
    position = store.head_position(launch_id)
    if position is None:
        raise PreconditionError(f"launch {launch_id} not found")
    item = next((i for i in position.items if i.itemId == hypothesis_item_id), None)
    if item is None or item.kind != "hypothesis":
        raise PreconditionError(f"{hypothesis_item_id} is not a hypothesis in Position v{position.version}")
    if item.state not in APPLICABLE:
        raise PreconditionError(f"{hypothesis_item_id} is {item.state}; a change applies to a proposed, planned or "
                                "running hypothesis")
    if applied_on > now.date():
        raise UsageError(f"applied on {applied_on.isoformat()} is in the future")
    record = ChangeRecord(
        changeId=f"chg_{launch_id}_{len(store.list_for_launch(ChangeRecord, launch_id)) + 1}", launchId=launch_id,
        hypothesisItemId=hypothesis_item_id, appliedOn=applied_on, what=what.strip(), by=by, role=role,
        recordedAt=at,
    )
    tracer = campaign_tracer(store, config_dir, launch_id)
    with tracer.step("campaign_manager", "launch_desk", "record_change", right="record_change") as step:
        step.set_inputs({"hypothesis": hypothesis_item_id, "appliedOn": applied_on.isoformat(), "what": record.what,
                         "by": by})
        store.insert(record)
        step.set_outputs({"changeId": record.changeId})
        step.set_decision("recorded", "applied by the Sponsor outside Hipstraw; M11 measures from this date")
    record_audit(store, launch_id=launch_id, at=at, actor=by, role=role, action="record_change",
                 right="record_change", before=hypothesis_item_id, after=record.changeId, reason=record.what)
    return record
