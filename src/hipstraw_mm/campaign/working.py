"""A Line run's working Position: its base snapshot plus every succeeded Move's outcome, in order."""

from __future__ import annotations

from hipstraw_mm.campaign.models import MoveExecution, PositionItem


def working_items(base: list[PositionItem], executions: list[MoveExecution]) -> list[PositionItem]:
    items = {i.itemId: i for i in base}
    for execution in executions:
        if execution.status != "succeeded":
            continue
        for new in execution.newItems:
            items[new.itemId] = new
        for t in execution.transitions:
            current = items.get(t.itemId)
            if current is not None:
                refs = list(dict.fromkeys([*current.evidenceRefs, *t.evidenceRefs]))
                items[t.itemId] = current.model_copy(update={"state": t.toState, "evidenceRefs": refs})
    return list(items.values())
