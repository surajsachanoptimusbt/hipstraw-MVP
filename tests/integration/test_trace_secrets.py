"""T013: Integration test – planted secrets never appear in stored traces."""

from __future__ import annotations

import io
import json
import os
from unittest.mock import patch

import pytest

from hipstraw_mm.cli import main
from hipstraw_mm.store.memory import MemoryStore

FAKE_OPENAI_KEY = "sk-planted-secret-abcdefghijklmnop"
FAKE_BRAVE_KEY = "BSAplanted-brave-secret-1234567890"


@pytest.fixture
def secret_harness(test_config, replay_adapters):
    from hipstraw_mm.context import Context
    from hipstraw_mm.logging_setup import EventLog

    store = MemoryStore()
    adapters = replay_adapters("us1")

    def context_factory(config):
        return Context(
            config=test_config,
            store=store,
            log=EventLog(runs_dir=None, stream=None),
            llm=adapters.llm,
            search=adapters.search,
            new_fetcher=adapters.new_fetcher,
        )

    return store, context_factory


class TestTraceSecrets:
    def test_planted_secrets_absent_from_traces(self, secret_harness) -> None:
        store, ctx_factory = secret_harness
        env = {"OPENAI_API_KEY": FAKE_OPENAI_KEY, "BRAVE_API_KEY": FAKE_BRAVE_KEY}
        with patch.dict(os.environ, env):
            main(["intake", "--program", "invoice_alpha"], context_factory=ctx_factory, stdout=io.StringIO())
            main(
                ["market", "start", "--program", "invoice_alpha_genesis"],
                context_factory=ctx_factory,
                stdout=io.StringIO(),
            )

        runs = store.list_market_runs()
        assert len(runs) >= 1
        run_id = runs[0]["marketRunId"]

        steps = store.list_trace_steps_after(run_id, 0)
        for step in steps:
            text = json.dumps(step)
            assert FAKE_OPENAI_KEY not in text, f"OPENAI key found in step {step['stepId']}"
            assert FAKE_BRAVE_KEY not in text, f"BRAVE key found in step {step['stepId']}"

        # Also scan blobs
        for step in steps:
            for blob_suffix in range(5):
                blob_id = f"{step['stepId']}__{blob_suffix}"
                blob = store.get_trace_blob(blob_id)
                if blob is not None:
                    blob_text = json.dumps(blob)
                    assert FAKE_OPENAI_KEY not in blob_text, f"OPENAI key in blob {blob_id}"
                    assert FAKE_BRAVE_KEY not in blob_text, f"BRAVE key in blob {blob_id}"
