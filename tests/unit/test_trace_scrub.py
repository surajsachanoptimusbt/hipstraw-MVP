"""T006: Unit tests for secret scrubbing in trace records and blobs."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from hipstraw_mm.market.layers import load_layers
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer
from hipstraw_mm.store.memory import MemoryStore

FAKE_OPENAI_KEY = "sk-fake-openai-key-1234567890abcdef"
FAKE_BRAVE_KEY = "BSAfake-brave-key-9876543210abcdef"


@pytest.fixture
def scrub_setup():
    store = MemoryStore()
    layers = load_layers()
    settings = load_pipeline_settings()
    run_id = "mrun_scrub_test"
    store.upsert_market_run({"marketRunId": run_id, "status": "opened", "lastSeq": 0, "counts": {}})
    env = {"OPENAI_API_KEY": FAKE_OPENAI_KEY, "BRAVE_API_KEY": FAKE_BRAVE_KEY}
    with patch.dict(os.environ, env):
        tracer = Tracer(store=store, layers=layers, settings=settings, run_id=run_id)
        yield store, tracer, run_id


class TestTraceScrub:
    def test_secret_in_inputs_is_scrubbed(self, scrub_setup) -> None:
        store, tracer, run_id = scrub_setup
        with tracer.step("workers", "llm_worker", "test_op", right="call_model") as step:
            step.set_inputs({"key": FAKE_OPENAI_KEY, "nested": {"api_key": FAKE_BRAVE_KEY}})
        doc = store.get_trace_step(f"{run_id}__000001")
        text = json.dumps(doc)
        assert FAKE_OPENAI_KEY not in text
        assert FAKE_BRAVE_KEY not in text

    def test_secret_in_blob_is_scrubbed(self, scrub_setup) -> None:
        store, tracer, run_id = scrub_setup
        with tracer.step("workers", "llm_worker", "test_op", right="call_model") as step:
            step.record_model_call(
                name="gpt-4o", prompt_version="v1", schema="Test", attempt=1,
                prompt_content=f'{{"header": "{FAKE_OPENAI_KEY}"}}',
                response_content=f'{{"token": "{FAKE_BRAVE_KEY}"}}',
                usage=None,
            )
        for n in range(3):
            blob_id = f"{run_id}__000001__{n}"
            blob = store.get_trace_blob(blob_id)
            if blob is not None:
                text = json.dumps(blob)
                assert FAKE_OPENAI_KEY not in text, f"OPENAI key in blob {blob_id}"
                assert FAKE_BRAVE_KEY not in text, f"BRAVE key in blob {blob_id}"

    def test_request_headers_never_recorded_in_tool_call(self, scrub_setup) -> None:
        store, tracer, run_id = scrub_setup
        with tracer.step("workers", "fetch_worker", "fetch_op", right="fetch_page") as step:
            tracer.observe_tool_call(
                kind="fetch", target="https://example.test",
                status="ok", detail="200",
            )
        doc = store.get_trace_step(f"{run_id}__000001")
        for tc in doc["toolCalls"]:
            assert "headers" not in tc
            assert "Authorization" not in json.dumps(tc)
