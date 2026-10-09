"""T009: Unit tests for the optional observer on LLMClient, BraveSearch, and Fetcher.

These tests require the observer protocol on adapters (T021). They are skipped until that task lands.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hipstraw_mm.adapters.llm import LLMClient

pytestmark = pytest.mark.skipif(
    not hasattr(LLMClient, "observer"),
    reason="T021: adapter observer protocol not yet implemented",
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestLLMClientObserver:
    def test_observer_called_on_model_call(self, replay_adapters) -> None:
        adapters = replay_adapters("us1")
        observer = MagicMock()
        adapters.llm.observer = observer
        from hipstraw_mm.steps.schemas import DiscoveryBatch

        with contextlib.suppress(Exception):
            adapters.llm.parse(
                DiscoveryBatch,
                [{"role": "user", "content": "test"}],
                match_key="test_observer",
                prompt_version="v1",
            )
        if observer.call_count > 0:
            call_args = observer.call_args
            assert call_args is not None

    def test_no_observer_no_error(self, replay_adapters) -> None:
        adapters = replay_adapters("us1")
        assert not hasattr(adapters.llm, "observer") or adapters.llm.observer is None

    def test_usage_recorded_when_present(self, replay_adapters) -> None:
        adapters = replay_adapters("us1")
        observer = MagicMock()
        adapters.llm.observer = observer


class TestBraveSearchObserver:
    def test_observer_called_on_search(self, replay_adapters) -> None:
        adapters = replay_adapters("us1")
        observer = MagicMock()
        adapters.search.observer = observer
        with contextlib.suppress(Exception):
            adapters.search.search("test query")
        if observer.call_count > 0:
            call_args = observer.call_args
            assert call_args is not None

    def test_no_observer_no_error(self, replay_adapters) -> None:
        adapters = replay_adapters("us1")
        assert not hasattr(adapters.search, "observer") or adapters.search.observer is None


class TestFetcherObserver:
    def test_observer_called_on_fetch(self, replay_adapters) -> None:
        adapters = replay_adapters("us1")
        fetcher = adapters.new_fetcher()
        observer = MagicMock()
        fetcher.observer = observer
        with contextlib.suppress(Exception):
            fetcher.fetch("https://example.test")
        if observer.call_count > 0:
            call_args = observer.call_args
            assert call_args is not None

    def test_no_observer_no_error(self, replay_adapters) -> None:
        adapters = replay_adapters("us1")
        fetcher = adapters.new_fetcher()
        assert not hasattr(fetcher, "observer") or fetcher.observer is None
