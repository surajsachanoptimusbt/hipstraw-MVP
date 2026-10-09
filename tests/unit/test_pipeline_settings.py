"""T004: Unit tests for config/pipeline.yaml and src/hipstraw_mm/market/settings.py."""

from __future__ import annotations

import pytest

from hipstraw_mm.market.settings import load_pipeline_settings


class TestPipelineSettings:
    def test_defaults_match_contract(self) -> None:
        s = load_pipeline_settings()
        assert s.beam.width == 5
        assert s.beam.finalPaths == 3
        assert s.beam.companiesPerPath == 5
        assert s.beam.minSearchScore == 0.75
        assert s.repair.maxAttempts == 3
        assert s.vichara.maxItemsPerDimension == 3
        assert s.links.lowConfidenceThreshold == 0.5
        assert s.links.linksPerCall == 12
        assert s.budgets.modelCallsPerRun == 300
        assert s.trace.maxBlobBytes == 900_000
        assert s.viewer.host == "127.0.0.1"
        assert s.viewer.port == 8765
        assert s.viewer.pollSeconds == 2

    def test_final_paths_le_width(self) -> None:
        s = load_pipeline_settings()
        assert s.beam.finalPaths <= s.beam.width

    def test_companies_per_path_le_10(self) -> None:
        s = load_pipeline_settings()
        assert s.beam.companiesPerPath <= 10

    def test_factor_weights_all_positive(self) -> None:
        s = load_pipeline_settings()
        for name, weight in s.factorWeights.items():
            assert weight > 0, f"weight for {name} must be > 0"

    def test_factor_weights_normalize(self) -> None:
        s = load_pipeline_settings()
        total = sum(s.factorWeights.values())
        normalized = {k: v / total for k, v in s.factorWeights.items()}
        assert abs(sum(normalized.values()) - 1.0) < 1e-9

    def test_repair_max_attempts_between_1_and_3(self) -> None:
        s = load_pipeline_settings()
        assert 1 <= s.repair.maxAttempts <= 3

    def test_viewer_host_must_be_loopback(self) -> None:
        s = load_pipeline_settings()
        assert s.viewer.host in ("127.0.0.1", "localhost", "::1")

    def test_missing_model_gives_unknown_cost(self) -> None:
        s = load_pipeline_settings()
        cost = s.model_cost("some-unknown-model-xyz", 1000, 500)
        assert cost is None

    def test_known_model_gives_cost(self) -> None:
        s = load_pipeline_settings()
        cost = s.model_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(2.50 + 10.00)
