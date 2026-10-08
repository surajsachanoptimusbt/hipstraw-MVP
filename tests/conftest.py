"""T014: Test harness: --emulator option, store, replay adapters, and test config fixtures."""

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from hipstraw_mm.adapters.fetch import Fetcher
from hipstraw_mm.adapters.llm import LLMClient
from hipstraw_mm.adapters.replay import ReplayStore
from hipstraw_mm.adapters.search import BraveSearch
from hipstraw_mm.config import LoadedConfig, load_config
from hipstraw_mm.store.memory import MemoryStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_DIR = FIXTURES_DIR / "recorded"
TEST_CONFIG_DIR = FIXTURES_DIR / "config"
LOCALHOST = ["127.0.0.1", "localhost", "::1"]


def pytest_addoption(parser):
    parser.addoption(
        "--emulator",
        action="store_true",
        default=False,
        help="also run tests marked 'emulator' against the Firestore emulator (needs FIRESTORE_EMULATOR_HOST)",
    )


def pytest_collection_modifyitems(config, items):
    enabled = config.getoption("--emulator") and os.environ.get("FIRESTORE_EMULATOR_HOST")
    reason = "needs --emulator and FIRESTORE_EMULATOR_HOST"
    for item in items:
        if "viewer" in item.keywords:
            item.add_marker(pytest.mark.allow_hosts(LOCALHOST))
        if "emulator" not in item.keywords:
            continue
        if enabled:
            # Sockets stay blocked except to the local emulator.
            item.add_marker(pytest.mark.allow_hosts(LOCALHOST))
        else:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def memory_store():
    return MemoryStore()


@pytest.fixture
def test_config() -> LoadedConfig:
    """Config overrides from tests/fixtures/config/: `.test` domains in the denylist and source types."""
    return load_config(TEST_CONFIG_DIR)


@dataclass
class ReplayAdapters:
    replay: ReplayStore
    llm: LLMClient
    search: BraveSearch
    config: LoadedConfig

    def new_fetcher(self) -> Fetcher:
        policy = self.config.source_policy
        return Fetcher(
            replay_store=self.replay,
            denylist_domains=policy.denylistDomains,
            user_agent=policy.userAgent,
            timeout_seconds=self.config.run.fetch.timeoutSeconds,
            max_bytes=self.config.run.fetch.maxBytes,
        )


@pytest.fixture
def replay_adapters(test_config):
    """Factory: model, search, and fetch adapters in replay mode for tests/fixtures/recorded/<scenario>/."""

    def _factory(scenario: str) -> ReplayAdapters:
        replay = ReplayStore(RECORDED_DIR / scenario, mode="replay")
        return ReplayAdapters(
            replay=replay,
            llm=LLMClient(model=test_config.run.model.name, replay=replay),
            search=BraveSearch(replay, denylist_domains=test_config.source_policy.denylistDomains),
            config=test_config,
        )

    return _factory
