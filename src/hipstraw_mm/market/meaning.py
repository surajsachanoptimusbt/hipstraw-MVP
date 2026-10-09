"""Loads config/graph_meaning.yaml and records the meaning step (no model call)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict


class LevelDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: str
    dimension: str
    maxNodes: int
    maxParents: int
    minNodes: int = 1


class FilterDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    appliesTo: str
    description: str


class GraphMeaning(BaseModel):
    model_config = ConfigDict(extra="forbid")
    levels: list[LevelDef]
    perPathDimensions: list[str]
    verificationResults: list[str]
    managerOnly: list[str]
    mandatoryFilters: list[FilterDef]


_CONFIG_PATH = Path("config") / "graph_meaning.yaml"


def load_graph_meaning(config_dir: Path = Path("config")) -> GraphMeaning:
    path = config_dir / "graph_meaning.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return GraphMeaning.model_validate(raw)


def record_meaning(store: Any, tracer: Any, run_id: str) -> None:
    gm = load_graph_meaning()
    raw_bytes = _CONFIG_PATH.read_bytes()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()

    with tracer.step(
        "market_development_controller",
        "graph_meaning",
        "define_graph_meaning",
        right="define_graph_meaning",
    ) as ctx:
        ctx.set_inputs({"source": str(_CONFIG_PATH)})
        doc = {
            "marketRunId": run_id,
            "levels": [lv.model_dump() for lv in gm.levels],
            "perPathDimensions": gm.perPathDimensions,
            "verificationResults": gm.verificationResults,
            "managerOnly": gm.managerOnly,
            "mandatoryFilters": [f.model_dump() for f in gm.mandatoryFilters],
            "fileHash": file_hash,
        }
        store.create_graph_meaning(run_id, doc)
        ctx.set_outputs({"fileHash": file_hash, "levelCount": len(gm.levels)})
