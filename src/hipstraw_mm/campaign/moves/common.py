"""What every Move handler receives and returns.

A handler reads a `MoveContext` (the mandate, the Line run's working Position as it stood at the start of
the stage, the evidence) and returns a `MoveOutcome`: transitions on existing items, new items, records
it produced and proposals. It never writes the Position: the runner keeps outcomes in the tactic record,
and only an accepted Review turns them into a new Position version (constitution VI).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from hipstraw_mm.campaign.config import CampaignSettings, load_settings
from hipstraw_mm.campaign.models import (
    Area,
    Asset,
    EvidenceRecord,
    ExecutionStatus,
    Launch,
    Mandate,
    PositionItem,
    Provenance,
    Transition,
    content_hash,
)
from hipstraw_mm.campaign.repertoire import MoveDef, Repertoire, load_repertoire
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.market.trace import Tracer

ITEM_PREFIX = {"claim": "C", "assumption": "A", "blocker": "B", "unknown": "U", "hypothesis": "H", "observation": "O"}


@dataclass
class PageRead:
    url: str
    ok: bool
    text: str | None = None
    reason: str | None = None


Fetch = Callable[[str], PageRead]


class ItemAllocator:
    """Next item IDs (B03, U02, ...) for one stage, shared by its Moves so their new items never collide."""

    def __init__(self, items: list[PositionItem]) -> None:
        self._next: dict[str, int] = {}
        for i in items:
            prefix, number = i.itemId[:1], i.itemId[1:]
            if number.isdigit():
                self._next[prefix] = max(self._next.get(prefix, 1), int(number) + 1)

    def allocate(self, kind: str) -> str:
        prefix = ITEM_PREFIX[kind]
        n = self._next.get(prefix, 1)
        self._next[prefix] = n + 1
        return f"{prefix}{n:02d}"


@dataclass
class MoveOutcome:
    status: ExecutionStatus = "succeeded"
    transitions: list[Transition] = field(default_factory=list)
    newItems: list[PositionItem] = field(default_factory=list)
    produced: list[str] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class MoveContext:
    store: CampaignStore
    config_dir: Path
    launch_id: str
    line_run_id: str
    move: MoveDef
    repertoire: Repertoire
    mandate: Mandate
    items: list[PositionItem]
    evidence: list[EvidenceRecord]
    settings: CampaignSettings
    now: datetime
    tracer: Tracer
    ids: ItemAllocator
    fetch: Fetch | None = None
    model: Any = None  # the E2 Moves' model context (Unit 5)

    # -- reading ---------------------------------------------------------------------------------------

    def owner(self) -> str:
        if self.mandate.approver:
            return self.mandate.approver
        launch = self.store.get(Launch, self.launch_id)
        return launch.owner if launch else "Sponsor"

    def brief_ref(self) -> list[str]:
        """The evidence for the current mandate's brief, which every mandate-derived item cites."""
        best: tuple[int, str] | None = None
        for e in self.evidence:
            if e.sourceRef.startswith("mandate:v") and e.sourceRef.endswith("#brief"):
                version = int(e.sourceRef[len("mandate:v"):-len("#brief")])
                if version <= self.mandate.version and (best is None or version > best[0]):
                    best = (version, e.evidenceId)
        return [best[1]] if best else []

    def asset_evidence(self, asset: Asset, content: str) -> EvidenceRecord | None:
        """The evidence already holding this asset's content. Asset IDs follow the order of the launch file, so an
        amendment that adds an asset can renumber the others; the same content is still the same evidence."""
        matches = [e for e in self.evidence if "#asset:" in e.sourceRef and e.content == content]
        same_id = [e for e in matches if e.sourceRef.endswith(f"#asset:{asset.assetId}")]
        return (same_id or matches)[-1] if matches else None

    def open_item(self, kind: str, key: str) -> PositionItem | None:
        open_states = {"blocker": "open", "unknown": "open"}
        for i in self.items:
            if i.kind == kind and i.key == key and i.state == open_states.get(kind, i.state):
                return i
        return None

    # -- writing ---------------------------------------------------------------------------------------

    def new_item(self, kind: str, area: Area, text: str, state: str, refs: list[str], *,
                 key: str | None = None, note: str | None = None, core: bool = False,
                 channel: str | None = None) -> PositionItem:
        return PositionItem(itemId=self.ids.allocate(kind), kind=kind, area=area,  # type: ignore[arg-type]
                            text=text, state=state, evidenceRefs=refs, setBy=self.move.id, key=key, note=note,
                            core=core, channel=channel)

    def add_evidence(self, **fields: Any) -> EvidenceRecord:
        n = len(self.store.list_for_launch(EvidenceRecord, self.launch_id)) + 1
        record = EvidenceRecord(
            evidenceId=f"ev_{self.launch_id}_{n}", launchId=self.launch_id, capturedAt=self.now.isoformat(),
            provenance=Provenance(by=self.move.id, method=self.move.name, moveId=self.move.id),
            contentHash=content_hash(fields["content"]), **fields,
        )
        self.store.insert(record)
        self.evidence.append(record)
        return record

    def record_id(self, prefix: str) -> str:
        return f"{prefix}_{self.launch_id}_{uuid.uuid4().hex[:8]}"


def build_move_context(
    store: CampaignStore, config_dir: Path, launch_id: str, move_id: str, now: datetime, *,
    line_run_id: str, items: list[PositionItem] | None = None, mandate: Mandate | None = None,
    fetch: Fetch | None = None, model: Any = None, ids: ItemAllocator | None = None,
    tracer: Tracer | None = None, repertoire: Repertoire | None = None,
) -> MoveContext:
    rep = repertoire or load_repertoire(config_dir)
    move = rep.moves.get(move_id)
    current = mandate or store.latest_mandate(launch_id)
    position = store.head_position(launch_id)
    if move is None:
        raise PreconditionError(f"unknown Move {move_id}")
    if current is None or position is None:
        raise PreconditionError(f"launch {launch_id} not found")
    working = list(items if items is not None else position.items)
    return MoveContext(
        store=store, config_dir=config_dir, launch_id=launch_id, line_run_id=line_run_id, move=move,
        repertoire=rep, mandate=current, items=working, evidence=store.list_for_launch(EvidenceRecord, launch_id),
        settings=load_settings(config_dir), now=now, tracer=tracer or campaign_tracer(store, config_dir, launch_id),
        ids=ids or ItemAllocator(working), fetch=fetch, model=model,
    )
