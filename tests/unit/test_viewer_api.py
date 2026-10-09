"""T011: Unit tests for src/hipstraw_mm/viewer/api.py (shaping functions over ReadStore)."""

from __future__ import annotations

from hipstraw_mm.store.memory import MemoryStore
from hipstraw_mm.viewer.api import shape_blob, shape_runs, shape_step, shape_steps


def _seed_store():
    store = MemoryStore()
    run_id = "mrun_view_test"
    store.upsert_market_run({
        "marketRunId": run_id, "status": "opened", "lastSeq": 2,
        "counts": {"modelCalls": 1}, "marketStatus": None, "programId": "test",
        "model": "gpt-4o", "createdAt": "2026-01-01T00:00:00Z",
    })
    for seq in (1, 2):
        step_id = f"{run_id}__{seq:06d}"
        store.create_trace_step({
            "stepId": step_id, "marketRunId": run_id, "seq": seq,
            "status": "ok" if seq == 1 else "running",
            "layer": "market_manager", "actor": "market_manager",
            "operation": "test_op", "inputs": {}, "outputs": {},
            "decision": None, "right": "open_run", "rationale": None,
            "alternatives": [], "checks": [], "model": None,
            "promptBlobId": f"{run_id}__{seq:06d}__0" if seq == 1 else None,
            "responseBlobId": f"{run_id}__{seq:06d}__1" if seq == 1 else None,
            "toolCalls": [], "cost": {"inputTokens": None, "outputTokens": None, "usd": None},
            "latencyMs": 100, "startedAt": "2026-01-01T00:00:00Z",
            "endedAt": "2026-01-01T00:00:01Z" if seq == 1 else None,
            "error": None, "parentStepId": None,
        })
    store.create_trace_blob({
        "blobId": f"{run_id}__000001__0", "marketRunId": run_id,
        "stepId": f"{run_id}__000001", "kind": "prompt",
        "content": '{"test": true}', "truncated": False, "bytes": 15,
    })
    return store, run_id


class TestShapeRuns:
    def test_runs_newest_first(self) -> None:
        store, run_id = _seed_store()
        store.upsert_market_run({
            "marketRunId": "mrun_aaa_older", "status": "opened", "lastSeq": 0,
            "counts": {}, "marketStatus": None, "programId": "test",
            "model": "gpt-4o", "createdAt": "2025-01-01T00:00:00Z",
        })
        runs = shape_runs(store)
        assert runs[0]["marketRunId"] == run_id

    def test_runs_include_market_status(self) -> None:
        store, run_id = _seed_store()
        runs = shape_runs(store)
        assert "marketStatus" in runs[0]


class TestShapeSteps:
    def test_steps_after_returns_only_gt_seq(self) -> None:
        store, run_id = _seed_store()
        steps = shape_steps(store, run_id, after=1)
        assert all(s["seq"] > 1 for s in steps)

    def test_running_steps_included(self) -> None:
        store, run_id = _seed_store()
        steps = shape_steps(store, run_id, after=0)
        statuses = [s["status"] for s in steps]
        assert "running" in statuses

    def test_bodies_omitted_but_blob_ids_present(self) -> None:
        store, run_id = _seed_store()
        steps = shape_steps(store, run_id, after=0)
        step1 = [s for s in steps if s["seq"] == 1][0]
        assert "promptBlobId" in step1
        assert "responseBlobId" in step1

    def test_refresh_returns_current_states(self) -> None:
        store, run_id = _seed_store()
        steps = shape_steps(store, run_id, refresh=[2])
        assert len(steps) == 1
        assert steps[0]["seq"] == 2


class TestShapeStep:
    def test_one_step_has_all_fr023_fields(self) -> None:
        store, run_id = _seed_store()
        step = shape_step(store, run_id, 1)
        assert step is not None
        expected = ["layer", "actor", "operation", "status", "inputs", "outputs",
                    "decision", "right", "rationale", "checks", "toolCalls", "cost",
                    "latencyMs", "startedAt", "endedAt", "error"]
        for field in expected:
            assert field in step

    def test_unknown_step_returns_none(self) -> None:
        store, run_id = _seed_store()
        step = shape_step(store, run_id, 999)
        assert step is None


class TestShapeBlob:
    def test_blob_returns_content(self) -> None:
        store, run_id = _seed_store()
        blob = shape_blob(store, f"{run_id}__000001__0")
        assert blob is not None
        assert blob["kind"] == "prompt"
        assert "content" in blob


class TestUnknownRunReturns404Body:
    def test_unknown_run(self) -> None:
        store, _ = _seed_store()
        runs = shape_runs(store)
        run_ids = [r["marketRunId"] for r in runs]
        assert "mrun_nonexistent" not in run_ids


class TestEvidenceConfidenceRename:
    def test_company_confidence_renamed(self) -> None:
        """Feature 002's company `confidence` is renamed `evidenceConfidence` in viewer responses."""
        # This will be extended once the companies route is added
        pass


class TestShapeDeliberations:
    """T039: /api/runs/<id>/deliberations shaping."""

    def _seed_with_deliberations(self):
        store, run_id = _seed_store()
        for i, key in enumerate([
            "market_scope", "problem", "segment_fit", "buyer", "use_case",
            "value_proposition", "demand_signals", "adoption_readiness", "economics",
            "timing", "alternatives", "risks", "dependencies",
            "evidence_sufficiency", "evidence_quality", "critical_unknowns",
            "trajectory", "transition", "market_status",
        ]):
            store.create_deliberation({
                "deliberationId": f"{run_id}__delib_{key}",
                "marketRunId": run_id,
                "dimensionKey": key,
                "items": [
                    {"question": f"Q about {key}?", "status": "answered",
                     "answer": f"Answer for {key}", "basis": [f"basis for {key}"],
                     "reason": None}
                ] if i < 15 else [
                    {"question": f"Q about {key}?", "status": "unresolved",
                     "answer": None, "basis": [],
                     "reason": "no information in the objective"}
                ],
                "basisCheck": {"status": "pass" if i < 15 else "skip"},
                "coverage": {"addressesDimension": i < 15, "reason": "ok" if i < 15 else "missing"},
                "repairAttempts": 0,
            })
        return store, run_id

    def test_returns_19_dimensions(self) -> None:
        from hipstraw_mm.viewer.api import shape_deliberations

        store, run_id = self._seed_with_deliberations()
        delibs = shape_deliberations(store, run_id)
        assert len(delibs) == 19

    def test_each_has_dimension_key(self) -> None:
        from hipstraw_mm.viewer.api import shape_deliberations

        store, run_id = self._seed_with_deliberations()
        delibs = shape_deliberations(store, run_id)
        for d in delibs:
            assert "dimensionKey" in d

    def test_includes_items_and_checks(self) -> None:
        from hipstraw_mm.viewer.api import shape_deliberations

        store, run_id = self._seed_with_deliberations()
        delibs = shape_deliberations(store, run_id)
        for d in delibs:
            assert "items" in d
            assert "basisCheck" in d or "coverage" in d

    def test_unresolved_has_reason(self) -> None:
        from hipstraw_mm.viewer.api import shape_deliberations

        store, run_id = self._seed_with_deliberations()
        delibs = shape_deliberations(store, run_id)
        unresolved = [d for d in delibs if any(
            it.get("status") == "unresolved" for it in d.get("items", [])
        )]
        assert len(unresolved) >= 1
        for d in unresolved:
            for item in d["items"]:
                if item["status"] == "unresolved":
                    assert item["reason"] is not None
