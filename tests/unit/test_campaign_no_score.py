"""T008: no campaign record or structured model output has a score, probability or forecast field
(FR-003; HA section 12 architecture check)."""

from __future__ import annotations

import importlib
import inspect

import pytest
from pydantic import BaseModel

BANNED = ("score", "probability", "forecast", "likelihood", "successrate")
MODULES = ["hipstraw_mm.campaign.models", "hipstraw_mm.campaign.llm_outputs"]


def _models(module_name: str) -> list[type[BaseModel]]:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        pytest.skip(f"{module_name} not built yet")
    return [
        obj for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, BaseModel) and obj.__module__ == module_name
    ]


@pytest.mark.parametrize("module_name", MODULES)
def test_no_banned_field_names(module_name: str) -> None:
    models = _models(module_name)
    assert models, f"no models found in {module_name}"
    offenders = [
        f"{model.__name__}.{field}"
        for model in models for field in model.model_fields
        if any(word in field.lower() for word in BANNED)
    ]
    assert offenders == []
