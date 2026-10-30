"""T006: the campaign config files load and reject unknown keys."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hipstraw_mm.campaign.config import load_campaign_layers, load_roles, load_settings

CONFIG = Path("config")


def test_layers_load_with_every_campaign_layer() -> None:
    layers = load_campaign_layers(CONFIG)
    assert {ly.id for ly in layers.layers} == {
        "campaign_manager", "readiness_testing", "authority_gate", "review", "workers",
    }
    workers = layers.layer_by_id("workers")
    assert workers is not None and "call_model" in workers.rights and "llm_worker" in workers.actors


def test_roles_load() -> None:
    roles = load_roles(CONFIG)
    assert "accept_review" in roles.roles["sponsor"]
    assert "choose_line" in roles.roles["campaign_manager"]
    assert "validate_review" in roles.roles["reviewer"]


def test_settings_load() -> None:
    settings = load_settings(CONFIG)
    assert settings.launchMarkets == ["US", "IN"]
    assert settings.nearDayZeroDays == 14
    assert "does not run campaigns" in settings.scopeStatement
    assert "{channel}" in settings.coreAssumptions.perChannel


@pytest.mark.parametrize("name,loader", [("roles.yaml", load_roles), ("settings.yaml", load_settings)])
def test_unknown_keys_are_rejected(tmp_path: Path, name: str, loader: object) -> None:
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    raw = yaml.safe_load((CONFIG / "campaign" / name).read_text(encoding="utf-8"))
    raw["surprise"] = 1
    (campaign / name).write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValidationError):
        loader(tmp_path)  # type: ignore[operator]
