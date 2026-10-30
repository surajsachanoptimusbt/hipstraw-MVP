"""The market tracer, pointed at the campaign store and the campaign layers (research R3)."""

from __future__ import annotations

from pathlib import Path

from hipstraw_mm.campaign.config import load_campaign_layers
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer


def campaign_tracer(store: CampaignStore, config_dir: Path, run_id: str) -> Tracer:
    """One trace run per launch; every campaign step for the launch shares its sequence."""
    store.open_trace_run(run_id)
    return Tracer(
        store=store.trace_sink(), layers=load_campaign_layers(config_dir),
        settings=load_pipeline_settings(config_dir), run_id=run_id,
    )
