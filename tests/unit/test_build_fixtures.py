"""The committed recordings match their scenario files, so a scenario edit cannot silently go unbuilt."""

from __future__ import annotations

import json

import pytest

from tests.fixtures.build_fixtures import RECORDED_DIR, SCENARIOS_DIR, build

SCENARIOS = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))


def _contents(root):
    return {p.relative_to(root).as_posix(): json.loads(p.read_text(encoding="utf-8")) for p in root.rglob("*.json")}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_committed_recordings_are_up_to_date(scenario, tmp_path):
    build(SCENARIOS_DIR / f"{scenario}.yaml", tmp_path / scenario)
    committed = RECORDED_DIR / scenario
    assert committed.exists(), f"run: python tests/fixtures/build_fixtures.py {scenario}"
    assert _contents(committed) == _contents(tmp_path / scenario), (
        f"recordings are stale; run: python tests/fixtures/build_fixtures.py {scenario}"
    )
