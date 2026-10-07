"""Helpers shared by the steps: run preconditions, failure marking, evidence IDs, and reliability."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any, TypeVar

from hipstraw_mm.config import SourcePolicy
from hipstraw_mm.context import Context
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.logging_setup import scrub
from hipstraw_mm.models import Reliability, SourceType
from hipstraw_mm.store.base import Doc, Store, StoreError

T = TypeVar("T")

# claimField of a CompanyEvidence claim -> the `unknowns` field it counts toward (data-model.md).
UNKNOWN_FIELD_FOR_CLAIM = {
    "hq": "hq",
    "employees": "size",
    "revenue": "size",
    "parent": "parent",
    "fit_buyer": "fit",
    "fit_problem": "fit",
    "fit_trigger": "fit",
    "signal_pain": "interestSignal",
    "signal_exploration": "interestSignal",
}


def require_run(store: Store, run_id: str, status: str) -> Doc:
    """The run, if it exists and is at `status` (contracts/cli.md: exit code 2 otherwise)."""
    run = store.get_run(run_id)
    if run is None:
        raise PreconditionError(f"run {run_id} not found")
    if run.get("status") != status:
        raise PreconditionError(f"run {run_id} is '{run.get('status')}', but this step needs '{status}'")
    return run


def run_step(ctx: Context, run_id: str, step: str, body: Callable[[], T]) -> T:
    """Run a step's body; on any failure mark the run `failed` with errorStep and errorMessage."""
    ctx.log.step_start(run_id, step)
    try:
        return body()
    except BaseException as exc:
        message = scrub(f"{type(exc).__name__}: {exc}")
        ctx.log.event("step_failed", run_id=run_id, step=step, error=message)
        mark_failed(ctx.store, run_id, step, message)
        raise


def mark_failed(store: Store, run_id: str, step: str, message: str) -> None:
    run = store.get_run(run_id)
    if run is None or run.get("status") in ("failed", "reported"):
        return
    with contextlib.suppress(StoreError):  # never hide the original error
        store.transition_run(run_id, run["status"], "failed", {"errorStep": step, "errorMessage": message})


class EvidenceIds:
    """`ev_<runId>_<seq>`, with one sequence per run continuing across steps (data-model.md)."""

    def __init__(self, store: Store, run_id: str) -> None:
        self.run_id = run_id
        self.seq = len(store.list_evidence(run_id))

    def next(self) -> str:
        self.seq += 1
        return f"ev_{self.run_id}_{self.seq:04d}"


def reliability_for(source_type: SourceType, policy: SourcePolicy) -> Reliability:
    return policy.reliabilityBySourceType[source_type]


def load_failure(fail_reason: str | None, http_status: int | None) -> str:
    """Why a website did not load, for reasons and unknowns: "HTTP 404" or "robots_disallowed"."""
    if fail_reason in (None, "http_error") and http_status is not None:
        return f"HTTP {http_status}"
    return f"{fail_reason}, HTTP {http_status}" if http_status is not None else str(fail_reason)


def merge_counts(existing: dict[str, Any] | None, add: dict[str, int]) -> dict[str, int]:
    out = dict(existing or {})
    for key, value in add.items():
        out[key] = int(out.get(key, 0)) + value
    return out
