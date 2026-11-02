"""M12: escalate open blockers, contested claims and open unknowns to the Sponsor (E0). An item already
escalated is not escalated again, so a daily Line raises only what is new."""

from __future__ import annotations

from hipstraw_mm.campaign.models import Escalation
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome

_OPEN = {("blocker", "open"), ("claim", "contested"), ("unknown", "open")}


@register("escalation.escalate")
def escalate(ctx: MoveContext) -> MoveOutcome:
    out = MoveOutcome()
    sent = {ref for e in ctx.store.list_for_launch(Escalation, ctx.launch_id) for ref in e.itemRefs}
    open_items = [i for i in ctx.items if (i.kind, i.state) in _OPEN]
    items = [i for i in open_items if i.itemId not in sent]
    if not items:
        out.note = f"nothing new to escalate ({len(open_items)} already with the Sponsor)" if open_items \
            else "nothing to escalate"
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
