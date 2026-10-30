"""Append-only audit of decisions (HA C5): who did what, under which right, and from which state to which."""

from __future__ import annotations

import uuid
from typing import Literal

from hipstraw_mm.campaign.models import AuditEvent
from hipstraw_mm.campaign.store import CampaignStore


def record_audit(
    store: CampaignStore,
    *,
    launch_id: str | None,
    at: str,
    actor: str,
    role: str,
    action: str,
    right: str | None = None,
    outcome: Literal["allowed", "refused"] = "allowed",
    before: str | None = None,
    after: str | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    event_id = f"au_{uuid.uuid4().hex[:16]}"
    event = AuditEvent(
        eventId=event_id, launchId=launch_id, at=at, actor=actor, role=role, action=action, right=right,
        outcome=outcome, beforeRef=before, afterRef=after, reason=reason, correlationId=correlation_id or event_id,
    )
    store.insert(event)
    return event
