"""Helpers shared by the steps: run preconditions, failure marking, evidence IDs, and reliability."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any, TypeVar

from hipstraw_mm.config import SourcePolicy
from hipstraw_mm.context import Context
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.logging_setup import scrub
from hipstraw_mm.models import Reliability, SourceType, host_of
from hipstraw_mm.store.base import Doc, Store, StoreError

T = TypeVar("T")

# claimField of a CompanyEvidence claim -> the `unknowns` field it counts toward (data-model.md).
UNKNOWN_FIELD_FOR_CLAIM = {
    "hq": "hq",
    "employees": "size",
    "revenue": "size",
    "parent": "parent",
    "parent_employees": "parent",
    "parent_revenue": "parent",
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


_CAUSES = {
    "dns_error": "the domain does not resolve",
    "robots_disallowed": "robots.txt disallows automated access",
    "network_error": "the connection failed",
    "too_many_redirects": "too many redirects",
    "not_html": "the page is not HTML",
    "too_large": "the page is too large",
    "denylisted": "the site is on the denylist",
    "bad_url": "the address is not a web URL",
}


def website_problem(status: str, fail_reason: str | None, http_status: int | None, final_url: str | None) -> str:
    """Why the website check did not pass, for unknowns and Review reasons (research R4):
    "website does not exist (HTTP 404)" or "website could not be read (robots.txt disallows ...)"."""
    if fail_reason == "http_error" and http_status is not None:
        cause = f"HTTP {http_status}"
    elif fail_reason == "redirect_off_site":
        cause = f"it redirects to another domain ({host_of(final_url or '') or 'unknown'})"
    else:
        cause = _CAUSES.get(fail_reason or "", fail_reason or "unknown failure")
    if status == "fails":
        return f"website does not exist ({cause})"
    return f"website could not be read ({cause})"


def merge_counts(existing: dict[str, Any] | None, add: dict[str, int]) -> dict[str, int]:
    out = dict(existing or {})
    for key, value in add.items():
        out[key] = int(out.get(key, 0)) + value
    return out
