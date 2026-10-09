"""Shaping functions over ReadStore for the viewer API (contracts/viewer-api.md)."""

from __future__ import annotations

from typing import Any

from hipstraw_mm.store.base import Doc


def shape_runs(store: Any) -> list[Doc]:
    runs = store.list_market_runs()
    result = []
    for r in runs:
        result.append({
            "marketRunId": r.get("marketRunId"),
            "status": r.get("status"),
            "programId": r.get("programId"),
            "model": r.get("model"),
            "createdAt": r.get("createdAt"),
            "counts": r.get("counts", {}),
            "marketStatus": r.get("marketStatus"),
        })
    return result


def shape_steps(
    store: Any,
    run_id: str,
    *,
    after: int | None = None,
    refresh: list[int] | None = None,
) -> list[Doc]:
    if refresh is not None:
        return store.get_trace_steps(run_id, refresh)
    steps = store.list_trace_steps_after(run_id, after or 0)
    for s in steps:
        s.pop("createdAt", None)
    return steps


def shape_step(store: Any, run_id: str, seq: int) -> Doc | None:
    results = store.get_trace_steps(run_id, [seq])
    if not results:
        return None
    step = results[0]
    step.pop("createdAt", None)
    return step


def shape_blob(store: Any, blob_id: str) -> Doc | None:
    blob = store.get_trace_blob(blob_id)
    if blob is None:
        return None
    return {
        "blobId": blob.get("blobId"),
        "kind": blob.get("kind"),
        "content": blob.get("content"),
        "truncated": blob.get("truncated", False),
        "bytes": blob.get("bytes", 0),
    }


def shape_run_detail(store: Any, run_id: str) -> Doc | None:
    run = store.get_market_run(run_id)
    if run is None:
        return None
    run.pop("createdAt", None)
    return run
