"""Live (or recorded) adapters for the campaign module: page reads, built only when a Move needs one."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hipstraw_mm.adapters.fetch import Fetcher
from hipstraw_mm.adapters.llm import LLMClient
from hipstraw_mm.adapters.replay import ReplayStore, mode_from_env
from hipstraw_mm.campaign.config import load_settings
from hipstraw_mm.campaign.moves.common import Fetch, PageRead
from hipstraw_mm.config import load_source_policy
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.logging_setup import EventLog


def campaign_replay() -> ReplayStore:
    """The same record/replay switch as the rest of the CLI (HIPSTRAW_REPLAY, HIPSTRAW_REPLAY_DIR)."""
    mode = mode_from_env()
    replay_dir = os.environ.get("HIPSTRAW_REPLAY_DIR")
    if mode != "off" and not replay_dir:
        raise PreconditionError("HIPSTRAW_REPLAY_DIR must be set when HIPSTRAW_REPLAY is 'replay' or 'record'")
    return ReplayStore(Path(replay_dir) if replay_dir else None, mode=mode)


def default_fetch(config_dir: Path) -> Fetch:
    policy = load_source_policy(config_dir / "source_policy.yaml")
    settings = load_settings(config_dir).fetch
    fetcher = Fetcher(
        replay_store=campaign_replay(), denylist_domains=policy.denylistDomains, user_agent=policy.userAgent,
        timeout_seconds=settings.timeoutSeconds, max_bytes=settings.maxBytes,
    )

    def fetch(url: str) -> PageRead:
        result = fetcher.fetch(url)
        return PageRead(url=url, ok=result.ok, text=result.text, reason=result.fail_reason)

    return fetch


@dataclass
class CampaignModels:
    """The router's ModelContext for the E2 Moves: the frontier client, and no open-weight tier in G0."""

    llm: LLMClient
    open_llm: LLMClient | None = None


def campaign_models() -> CampaignModels | None:
    """The frontier model from LLM_MODEL (default gpt-4o), live or replayed. None when neither a key nor a
    recording is available, so the E2 Moves report "no model" instead of failing mid-Line."""
    replay = campaign_replay()
    if replay.mode == "off" and not os.environ.get("OPENAI_API_KEY"):
        return None
    log = EventLog(runs_dir=Path(".runs"))
    # Temperature 0: a review should give the same verdict on the same evidence.
    return CampaignModels(llm=LLMClient(model=os.environ.get("LLM_MODEL") or "gpt-4o", replay=replay, log=log,
                                        extra_params={"temperature": 0}))
