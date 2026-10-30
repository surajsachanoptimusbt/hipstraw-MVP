"""M12: escalate open blockers, contested claims and open unknowns to the Sponsor (E0)."""

from __future__ import annotations

from hipstraw_mm.campaign.models import Escalation
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome

_OPEN = {("blocker", "open"), ("claim", "contested"), ("unknown", "open")}


@register("escalation.escalate")
def escalate(ctx: MoveContext) -> MoveOutcome:
    out = MoveOutcome()
    items = [i for i in ctx.items if (i.kind, i.state) in _OPEN]
    if not items:
        out.note = "nothing to escalate"
        return out
    escalation = Escalation(
        escalationId=ctx.record_id("esc"), launchId=ctx.launch_id, itemRefs=[i.itemId for i in items],
        reason=f"{len(items)} open items need the Sponsor's decision: " + "; ".join(i.text for i in items),
        to=ctx.owner(), createdAt=ctx.now.isoformat(),
    )
    ctx.store.insert(escalation)
    out.produced.append(escalation.escalationId)
    out.note = f"escalated {len(items)} items"
    return out
