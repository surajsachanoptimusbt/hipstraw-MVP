"""Helpers for the Move handler tests: a submitted launch and a MoveContext for one Move."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hipstraw_mm.campaign.intake import submit_launch
from hipstraw_mm.campaign.models import Mandate, PositionItem
from hipstraw_mm.campaign.moves import HANDLERS
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome, PageRead, build_move_context
from hipstraw_mm.campaign.store import SqliteCampaignStore

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
CONFIG = Path("config")
FIX = Path("tests/fixtures/campaign")


def launch(name: str = "launch_complete.yaml") -> tuple[SqliteCampaignStore, str]:
    store = SqliteCampaignStore(":memory:")
    return store, submit_launch(store, CONFIG, FIX / name, by="Demo Sponsor", role="sponsor", now=NOW).launchId


def context(
    store: SqliteCampaignStore, launch_id: str, move_id: str, *,
    items: list[PositionItem] | None = None, mandate: Mandate | None = None,
    fetch: Callable[[str], PageRead] | None = None, model: Any = None,
) -> MoveContext:
    return build_move_context(store, CONFIG, launch_id, move_id, NOW, line_run_id=f"lrun_{launch_id}_t",
                              items=items, mandate=mandate, fetch=fetch, model=model)


def run(ctx: MoveContext) -> MoveOutcome:
    return HANDLERS[ctx.move.handler](ctx)  # type: ignore[no-any-return]


def item(item_id: str, kind: str, state: str, text: str = "x", **extra: Any) -> PositionItem:
    return PositionItem(itemId=item_id, kind=kind, area=extra.pop("area", "strategy"),  # type: ignore[arg-type]
                        text=text, state=state, evidenceRefs=extra.pop("refs", ["ev_x"]), setBy="test", **extra)
