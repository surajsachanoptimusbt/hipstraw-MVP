"""Fixtures for the integration tests. The helpers they use live in tests/integration/harness.py."""

from __future__ import annotations

import pytest

from hipstraw_mm import cli
from hipstraw_mm.adapters.llm import LLMClient
from hipstraw_mm.config import LoadedConfig
from hipstraw_mm.logging_setup import EventLog
from tests.integration.harness import FIXED_NOW, CompletedRun, Harness, run_basic


@pytest.fixture
def harness_for(tmp_path, memory_store, replay_adapters):
    """Factory: a Harness for one replay scenario under tests/fixtures/recorded/<scenario>/."""

    def _make(scenario: str) -> Harness:
        adapters = replay_adapters(scenario)
        runs_dir = tmp_path / ".runs"
        reports_dir = tmp_path / "reports"
        log = EventLog(runs_dir=runs_dir, stream=None, clock=lambda: FIXED_NOW)

        def context_factory(config: LoadedConfig) -> cli.Context:
            return cli.Context(
                config=config,
                store=memory_store,
                log=log,
                llm=LLMClient(model=config.run.model.name, replay=adapters.replay, log=log),
                search=adapters.search,
                new_fetcher=adapters.new_fetcher,
                reports_dir=reports_dir,
                now=lambda: FIXED_NOW,
            )

        return Harness(memory_store, runs_dir, reports_dir, context_factory)

    return _make


@pytest.fixture
def basic_run(harness_for) -> CompletedRun:
    """A completed `basic` run. Fails setup with the first command's error if any command failed."""
    completed = run_basic(harness_for("basic"))
    for command, result in completed.results.items():
        if result.code != 0:
            pytest.fail(f"`{command}` exited with {result.code}: {result.stderr.strip()}")
    return completed
