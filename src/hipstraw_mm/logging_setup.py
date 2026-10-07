"""JSON-lines event log to stderr and `.runs/<runId>/run.log` (research R14, Constitution V)."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TextIO

SECRET_ENV_VARS = ("OPENAI_API_KEY", "BRAVE_API_KEY")
REDACTED = "[redacted]"


def secret_values() -> list[str]:
    values = (os.environ.get(name) for name in SECRET_ENV_VARS)
    return [v for v in values if v and len(v) >= 8]


def scrub(text: str) -> str:
    for value in secret_values():
        text = text.replace(value, REDACTED)
    return text


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventLog:
    """Writes one JSON object per line. Every event carries runId and step."""

    def __init__(
        self,
        runs_dir: Path | None = Path(".runs"),
        stream: TextIO | None | Literal["stderr"] = "stderr",
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.runs_dir = Path(runs_dir) if runs_dir is not None else None
        self._stream = stream
        self.clock = clock

    @property
    def stream(self) -> TextIO | None:
        # Resolved per write so a replaced sys.stderr (e.g. under pytest capture) is honoured.
        if isinstance(self._stream, str):
            return sys.stderr
        return self._stream

    def log_path(self, run_id: str) -> Path | None:
        return self.runs_dir / run_id / "run.log" if self.runs_dir is not None else None

    def event(
        self,
        event: str,
        *,
        run_id: str | None,
        step: str,
        company_record_id: str | None = None,
        **fields: Any,
    ) -> None:
        record: dict[str, Any] = {
            "ts": self.clock().isoformat(),
            "event": event,
            "runId": run_id,
            "step": step,
        }
        if company_record_id is not None:
            record["companyRecordId"] = company_record_id
        record.update(fields)
        line = scrub(json.dumps(record, default=str, ensure_ascii=False))
        stream = self.stream
        if stream is not None:
            stream.write(line + "\n")
            stream.flush()
        path = self.log_path(run_id) if run_id else None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def step_start(self, run_id: str, step: str) -> None:
        self.event("step_start", run_id=run_id, step=step)

    def step_end(self, run_id: str, step: str, counts: dict[str, int]) -> None:
        self.event("step_end", run_id=run_id, step=step, counts=counts)
