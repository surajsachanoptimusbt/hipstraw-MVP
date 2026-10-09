"""T003: Unit tests for config/layers.yaml and src/hipstraw_mm/market/layers.py."""

from __future__ import annotations

import pytest

from hipstraw_mm.market.layers import LayerConfig, check_layer_right, load_layers

EXPECTED_LAYER_IDS = [
    "market_manager",
    "market_development_controller",
    "search_research",
    "position_evaluation",
    "workers",
]


class TestLayerConfig:
    def test_five_layers_in_order(self) -> None:
        cfg = load_layers()
        assert [layer.id for layer in cfg.layers] == EXPECTED_LAYER_IDS

    def test_right_belongs_to_exactly_one_layer(self) -> None:
        cfg = load_layers()
        seen: dict[str, str] = {}
        for layer in cfg.layers:
            for right in layer.rights:
                assert right not in seen, f"right {right!r} in both {seen[right]!r} and {layer.id!r}"
                seen[right] = layer.id

    def test_actors_are_unique(self) -> None:
        cfg = load_layers()
        seen: dict[str, str] = {}
        for layer in cfg.layers:
            for actor in layer.actors:
                assert actor not in seen, f"actor {actor!r} in both {seen[actor]!r} and {layer.id!r}"
                seen[actor] = layer.id

    def test_check_accepts_declared_triple(self) -> None:
        cfg = load_layers()
        for layer in cfg.layers:
            for actor in layer.actors:
                for right in layer.rights:
                    check_layer_right(cfg, layer.id, actor, right)

    def test_check_rejects_undeclared_actor(self) -> None:
        cfg = load_layers()
        with pytest.raises(ValueError, match="actor"):
            check_layer_right(cfg, "workers", "not_an_actor", "call_model")

    def test_check_rejects_undeclared_right(self) -> None:
        cfg = load_layers()
        with pytest.raises(ValueError, match="right"):
            check_layer_right(cfg, "workers", "llm_worker", "not_a_right")

    def test_check_rejects_right_from_another_layer(self) -> None:
        cfg = load_layers()
        with pytest.raises(ValueError, match="right"):
            check_layer_right(cfg, "search_research", "vichara", "decide_path")
