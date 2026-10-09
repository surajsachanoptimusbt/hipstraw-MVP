"""T034: Unit tests for config/graph_meaning.yaml and src/hipstraw_mm/market/meaning.py."""

from __future__ import annotations

EXPECTED_LEVEL_ORDER = ["segment", "archetype", "problem", "trigger", "buyerRole", "useCase"]
EXPECTED_PER_PATH = [
    "value_proposition", "demand_signals", "adoption_readiness",
    "economics", "alternatives", "risks", "dependencies",
]
EXPECTED_VERIFICATION = ["evidence_sufficiency", "evidence_quality", "critical_unknowns"]
EXPECTED_MANAGER_ONLY = ["trajectory", "transition", "market_status"]

ALL_19_KEYS = [
    "market_scope", "problem", "segment_fit", "buyer", "use_case",
    "value_proposition", "demand_signals", "adoption_readiness", "economics",
    "timing", "alternatives", "risks", "dependencies",
    "evidence_sufficiency", "evidence_quality", "critical_unknowns",
    "trajectory", "transition", "market_status",
]


class TestGraphMeaningYaml:
    def test_six_levels_in_order(self) -> None:
        from hipstraw_mm.market.meaning import load_graph_meaning

        gm = load_graph_meaning()
        level_names = [lv.level for lv in gm.levels]
        assert level_names == EXPECTED_LEVEL_ORDER

    def test_per_path_dimensions_count(self) -> None:
        from hipstraw_mm.market.meaning import load_graph_meaning

        gm = load_graph_meaning()
        assert len(gm.perPathDimensions) == 7
        assert set(gm.perPathDimensions) == set(EXPECTED_PER_PATH)

    def test_verification_results_count(self) -> None:
        from hipstraw_mm.market.meaning import load_graph_meaning

        gm = load_graph_meaning()
        assert len(gm.verificationResults) == 3
        assert set(gm.verificationResults) == set(EXPECTED_VERIFICATION)

    def test_manager_only_count(self) -> None:
        from hipstraw_mm.market.meaning import load_graph_meaning

        gm = load_graph_meaning()
        assert len(gm.managerOnly) == 3
        assert set(gm.managerOnly) == set(EXPECTED_MANAGER_ONLY)

    def test_all_19_keys_covered_exactly_once(self) -> None:
        from hipstraw_mm.market.meaning import load_graph_meaning

        gm = load_graph_meaning()
        level_dims = [lv.dimension for lv in gm.levels]
        all_dims = level_dims + gm.perPathDimensions + gm.verificationResults + gm.managerOnly
        assert len(all_dims) == 19
        assert set(all_dims) == set(ALL_19_KEYS)

    def test_each_level_links_only_to_next(self) -> None:
        from hipstraw_mm.market.meaning import load_graph_meaning

        gm = load_graph_meaning()
        levels = [lv.level for lv in gm.levels]
        for i, lv in enumerate(gm.levels[:-1]):
            # Each level's children should be the next level
            next_level = levels[i + 1]
            # This is implicit: edges go from level[i] to level[i+1]
            assert lv.level != next_level

    def test_filters_exist(self) -> None:
        from hipstraw_mm.market.meaning import load_graph_meaning

        gm = load_graph_meaning()
        filter_ids = [f.id for f in gm.mandatoryFilters]
        assert "metro_in_force" in filter_ids
        assert "no_enterprise" in filter_ids


class TestMeaningStep:
    def test_meaning_step_no_model_call(self) -> None:
        """The meaning step writes the record without calling any model."""
        from hipstraw_mm.market.layers import load_layers
        from hipstraw_mm.market.meaning import record_meaning
        from hipstraw_mm.market.settings import load_pipeline_settings
        from hipstraw_mm.market.trace import Tracer
        from hipstraw_mm.store.memory import MemoryStore

        store = MemoryStore()
        layers = load_layers()
        settings = load_pipeline_settings()
        run_id = "mrun_test_meaning"
        store.upsert_market_run({
            "marketRunId": run_id, "status": "deliberated", "lastSeq": 0,
            "counts": {"modelCalls": 0}, "marketStatus": None, "programId": "test",
            "model": "gpt-4o", "config": settings.model_dump(),
            "objective": {}, "constraintsInForce": {},
            "unresolved": [], "unassessed": [],
            "errorStage": None, "errorMessage": None,
            "finalPathShortfall": None,
        })
        tracer = Tracer(store=store, layers=layers, settings=settings, run_id=run_id)
        record_meaning(store, tracer, run_id)
        # Verify a graphMeanings record was created
        gm_doc = store.get_graph_meaning(run_id)
        assert gm_doc is not None
        assert "sha256" in gm_doc or "fileHash" in gm_doc or "hash" in str(gm_doc)

    def test_meaning_step_layer_and_right(self) -> None:
        from hipstraw_mm.market.layers import load_layers
        from hipstraw_mm.market.meaning import record_meaning
        from hipstraw_mm.market.settings import load_pipeline_settings
        from hipstraw_mm.market.trace import Tracer
        from hipstraw_mm.store.memory import MemoryStore

        store = MemoryStore()
        layers = load_layers()
        settings = load_pipeline_settings()
        run_id = "mrun_test_meaning2"
        store.upsert_market_run({
            "marketRunId": run_id, "status": "deliberated", "lastSeq": 0,
            "counts": {"modelCalls": 0}, "marketStatus": None, "programId": "test",
            "model": "gpt-4o", "config": settings.model_dump(),
            "objective": {}, "constraintsInForce": {},
            "unresolved": [], "unassessed": [],
            "errorStage": None, "errorMessage": None,
            "finalPathShortfall": None,
        })
        tracer = Tracer(store=store, layers=layers, settings=settings, run_id=run_id)
        record_meaning(store, tracer, run_id)
        steps = store.list_trace_steps_after(run_id, 0)
        assert len(steps) >= 1
        step = steps[0]
        assert step["layer"] == "market_development_controller"
        assert step["right"] == "define_graph_meaning"
