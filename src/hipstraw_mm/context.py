"""What every step receives (Context) and returns (CommandResult). The CLI builds the real Context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hipstraw_mm.adapters.fetch import Fetcher
from hipstraw_mm.adapters.llm import LLMClient
from hipstraw_mm.adapters.search import BraveSearch
from hipstraw_mm.config import LoadedConfig
from hipstraw_mm.logging_setup import EventLog
from hipstraw_mm.store.base import Store


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Context:
    """Everything a step needs. Tests build their own with a MemoryStore and replay adapters."""

    config: LoadedConfig
    store: Store
    log: EventLog
    llm: LLMClient
    search: BraveSearch
    new_fetcher: Callable[[], Fetcher]
    reports_dir: Path = Path("reports")
    now: Callable[[], datetime] = _utc_now

    def now_iso(self) -> str:
        return self.now().isoformat()


@dataclass
class CommandResult:
    command: str
    message: str = ""
    runId: str | None = None
    status: str | None = None
    counts: dict[str, int] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"command": self.command}
        for key in ("runId", "status", "counts"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.warnings:
            out["warnings"] = self.warnings
        return out
