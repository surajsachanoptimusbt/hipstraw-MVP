"""Loads config/layers.yaml and validates (layer, actor, right) triples (Constitution XIV)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class LayerDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    responsibility: str
    actors: list[str]
    rights: list[str]


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layers: list[LayerDef]

    def layer_by_id(self, layer_id: str) -> LayerDef | None:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None


def load_layers(config_dir: Path = Path("config")) -> LayerConfig:
    path = config_dir / "layers.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return LayerConfig.model_validate(raw)


def check_layer_right(cfg: LayerConfig, layer_id: str, actor: str, right: str) -> None:
    layer = cfg.layer_by_id(layer_id)
    if layer is None:
        raise ValueError(f"unknown layer: {layer_id!r}")
    if actor not in layer.actors:
        all_actors = {a for ly in cfg.layers for a in ly.actors}
        if actor in all_actors:
            raise ValueError(f"actor {actor!r} belongs to another layer, not {layer_id!r}")
        raise ValueError(f"unknown actor: {actor!r}")
    if right not in layer.rights:
        all_rights = {r for ly in cfg.layers for r in ly.rights}
        if right in all_rights:
            raise ValueError(f"right {right!r} belongs to another layer, not {layer_id!r}")
        raise ValueError(f"unknown right: {right!r}")
