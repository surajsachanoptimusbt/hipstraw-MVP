"""The Tracer: sole writer of trace records (Constitution XII).

Every pipeline step records its trace through this class. No step writes a trace record any
other way. Secrets are scrubbed at the single write point. The model-call ceiling is enforced here.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Any

from hipstraw_mm.logging_setup import scrub
from hipstraw_mm.market.layers import LayerConfig, check_layer_right
from hipstraw_mm.market.settings import PipelineSettings
from hipstraw_mm.store.base import Doc, InvalidTransitionError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _scrub_deep(obj: Any) -> Any:
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, dict):
        return {_scrub_deep(k): _scrub_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_deep(item) for item in obj]
    return obj


class ModelCallCeilingError(Exception):
    pass


class TraceStepContext:
    """Context manager for one trace step. Collects fields, seals on exit."""

    def __init__(self, tracer: Tracer, step_id: str, seq: int) -> None:
        self._tracer = tracer
        self.step_id = step_id
        self.seq = seq
        self._inputs: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}
        self._decision: str | None = None
        self._rationale: str | None = None
        self._alternatives: list[dict[str, Any]] = []
        self._checks: list[dict[str, Any]] = []
        self._model_info: dict[str, Any] | None = None
        self._prompt_blob_id: str | None = None
        self._response_blob_id: str | None = None
        self._tool_calls: list[dict[str, Any]] = []
        self._cost_input_tokens: int | None = None
        self._cost_output_tokens: int | None = None
        self._cost_usd: float | None = None

    def set_inputs(self, inputs: dict[str, Any]) -> None:
        self._inputs = inputs

    def set_outputs(self, outputs: dict[str, Any]) -> None:
        self._outputs = outputs

    def set_decision(self, decision: str, rationale: str | None = None) -> None:
        self._decision = decision
        self._rationale = rationale

    def add_alternative(self, option: str, reason: str) -> None:
        self._alternatives.append({"option": option, "reason": reason})

    def add_check(self, name: str, status: str, reason: str) -> None:
        self._checks.append({"name": name, "status": status, "reason": reason})

    def record_model_call(
        self,
        *,
        name: str,
        prompt_version: str,
        schema: str,
        attempt: int,
        prompt_content: str,
        response_content: str,
        usage: dict[str, Any] | None = None,
    ) -> None:
        self._model_info = {
            "name": name,
            "promptVersion": prompt_version,
            "schema": schema,
            "attempt": attempt,
        }
        blob_n = 0
        self._prompt_blob_id = self._tracer._write_blob(
            self.step_id, self.seq, blob_n, "prompt", prompt_content
        )
        blob_n += 1
        self._response_blob_id = self._tracer._write_blob(
            self.step_id, self.seq, blob_n, "response", response_content
        )
        if usage:
            self._cost_input_tokens = usage.get("inputTokens") or usage.get("input_tokens")
            self._cost_output_tokens = usage.get("outputTokens") or usage.get("output_tokens")
            model_name = name or ""
            usd = self._tracer._settings.model_cost(
                model_name,
                self._cost_input_tokens or 0,
                self._cost_output_tokens or 0,
            )
            self._cost_usd = usd

    def _seal_fields(self, status: str, error: str | None, end_time: str, latency_ms: int) -> Doc:
        return {
            "status": status,
            "inputs": self._inputs,
            "outputs": self._outputs,
            "decision": self._decision,
            "rationale": self._rationale,
            "alternatives": self._alternatives,
            "checks": self._checks,
            "model": self._model_info,
            "promptBlobId": self._prompt_blob_id,
            "responseBlobId": self._response_blob_id,
            "toolCalls": self._tool_calls,
            "cost": {
                "inputTokens": self._cost_input_tokens,
                "outputTokens": self._cost_output_tokens,
                "usd": self._cost_usd,
            },
            "latencyMs": latency_ms,
            "endedAt": end_time,
            "error": error,
        }


class Tracer:
    def __init__(
        self,
        *,
        store: Any,
        layers: LayerConfig,
        settings: PipelineSettings,
        run_id: str,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._layers = layers
        self._settings = settings
        self._run_id = run_id
        self._clock = clock
        self._current_step: TraceStepContext | None = None
        existing = store.get_market_run(run_id) or {}
        self._seq = int(existing.get("lastSeq") or 0)
        self._model_call_count = int((existing.get("counts") or {}).get("modelCalls") or 0)

    @contextlib.contextmanager
    def step(
        self,
        layer: str,
        actor: str,
        operation: str,
        *,
        right: str | None = None,
    ) -> Iterator[TraceStepContext]:
        if right is not None:
            check_layer_right(self._layers, layer, actor, right)
        else:
            layer_def = self._layers.layer_by_id(layer)
            if layer_def is None:
                raise ValueError(f"unknown layer: {layer!r}")
            if actor not in layer_def.actors:
                all_actors = {a for ly in self._layers.layers for a in ly.actors}
                if actor in all_actors:
                    raise ValueError(f"actor {actor!r} belongs to another layer, not {layer!r}")
                raise ValueError(f"unknown actor: {actor!r}")

        self._seq += 1
        seq = self._seq
        step_id = f"{self._run_id}__{seq:06d}"
        start_time = self._clock()
        start_iso = start_time.isoformat()

        parent_step_id = self._current_step.step_id if self._current_step else None
        step_doc: Doc = _scrub_deep({
            "stepId": step_id,
            "marketRunId": self._run_id,
            "seq": seq,
            "parentStepId": parent_step_id,
            "layer": layer,
            "actor": actor,
            "operation": operation,
            "status": "running",
            "inputs": {},
            "outputs": {},
            "decision": None,
            "right": right,
            "rationale": None,
            "alternatives": [],
            "checks": [],
            "model": None,
            "promptBlobId": None,
            "responseBlobId": None,
            "toolCalls": [],
            "cost": {"inputTokens": None, "outputTokens": None, "usd": None},
            "latencyMs": None,
            "startedAt": start_iso,
            "endedAt": None,
            "error": None,
        })
        self._store.create_trace_step(step_doc)

        self._update_run({"lastSeq": seq}, counts={"traceSteps": seq})

        ctx = TraceStepContext(self, step_id, seq)
        prev_step = self._current_step
        self._current_step = ctx

        error_msg: str | None = None
        status = "ok"
        try:
            yield ctx
        except Exception as exc:
            status = "failed"
            error_msg = scrub(str(exc))
            raise
        finally:
            self._current_step = prev_step
            end_time = self._clock()
            latency_ms = max(0, int((end_time - start_time).total_seconds() * 1000))
            seal_fields = _scrub_deep(ctx._seal_fields(status, error_msg, end_time.isoformat(), latency_ms))
            with contextlib.suppress(InvalidTransitionError):
                self._store.finish_trace_step(step_id, seal_fields)

    def observe_tool_call(
        self,
        *,
        kind: str,
        target: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        if self._current_step is not None:
            tc: dict[str, Any] = {"kind": kind, "target": target, "status": status}
            if detail is not None:
                tc["detail"] = detail
            self._current_step._tool_calls.append(tc)
        count_key = {"search": "searches", "fetch": "fetches"}.get(kind)
        if count_key:
            run = self._store.get_market_run(self._run_id) or {}
            self._update_run({}, counts={count_key: int((run.get("counts") or {}).get(count_key) or 0) + 1})

    def observe_model_call(self) -> None:
        self._model_call_count += 1
        ceiling = self._settings.budgets.modelCallsPerRun
        if self._model_call_count > ceiling:
            raise ModelCallCeilingError(
                f"model call ceiling exceeded: {self._model_call_count} > {ceiling}"
            )
        self._update_run({}, counts={"modelCalls": self._model_call_count})

    def record_usage(self, *, model_calls: int = 0, searches: int = 0, fetches: int = 0) -> None:
        """Usage made outside this tracer's model_call (feature 002 child runs): counted toward the ceiling."""
        run = self._store.get_market_run(self._run_id) or {}
        counts = run.get("counts") or {}
        self._update_run({}, counts={
            "searches": int(counts.get("searches") or 0) + searches,
            "fetches": int(counts.get("fetches") or 0) + fetches,
        })
        for _ in range(model_calls):
            self.observe_model_call()

    def _update_run(self, fields: dict[str, Any], counts: dict[str, int]) -> None:
        run_doc = self._store.get_market_run(self._run_id)
        if not run_doc:
            return
        run_doc.update(fields)
        run_doc["counts"] = {**(run_doc.get("counts") or {}), **counts}
        self._store.upsert_market_run(run_doc)

    def _write_blob(
        self, step_id: str, seq: int, n: int, kind: str, content: str
    ) -> str:
        blob_id = f"{self._run_id}__{seq:06d}__{n}"
        max_bytes = self._settings.trace.maxBlobBytes
        original_bytes = len(content)
        truncated = original_bytes > max_bytes
        if truncated:
            content = content[:max_bytes]
        blob_doc: Doc = _scrub_deep({
            "blobId": blob_id,
            "marketRunId": self._run_id,
            "stepId": step_id,
            "kind": kind,
            "content": content,
            "truncated": truncated,
            "bytes": original_bytes,
        })
        self._store.create_trace_blob(blob_doc)
        return blob_id
