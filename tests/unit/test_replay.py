"""T012: Replay tests (research R11)."""

import json

import pytest

from hipstraw_mm.adapters.replay import (
    ReplayMissingError,
    ReplayStore,
    match_key_hash,
)


@pytest.fixture
def tmp_replay_dir(tmp_path):
    scenario_dir = tmp_path / "test_scenario" / "fetch"
    scenario_dir.mkdir(parents=True)
    return tmp_path / "test_scenario"


class TestReplayStore:
    def test_replay_returns_recorded_response(self, tmp_replay_dir):
        match_key = "https://example.test/page"
        key_hash = match_key_hash(match_key)
        record = {
            "matchKey": match_key,
            "request": {"url": match_key},
            "response": {"status": 200, "text": "hello"},
        }
        out = tmp_replay_dir / "fetch" / f"{key_hash}.json"
        out.write_text(json.dumps(record))

        store = ReplayStore(tmp_replay_dir, mode="replay")
        resp = store.get("fetch", match_key)
        assert resp["status"] == 200
        assert resp["text"] == "hello"

    def test_missing_recording_raises(self, tmp_replay_dir):
        store = ReplayStore(tmp_replay_dir, mode="replay")
        with pytest.raises(ReplayMissingError):
            store.get("fetch", "https://missing.test/page")

    def test_record_mode_writes_file(self, tmp_replay_dir):
        store = ReplayStore(tmp_replay_dir, mode="record")
        match_key = "test query"
        request = {"query": "test query", "headers": {"Authorization": "Bearer sk-secret123"}}
        response = {"results": [{"url": "https://example.test"}]}

        store.put("search", match_key, request, response)

        key_hash = match_key_hash(match_key)
        written = json.loads((tmp_replay_dir / "search" / f"{key_hash}.json").read_text())
        assert written["matchKey"] == match_key
        assert written["response"] == response

    def test_record_mode_redacts_authorization(self, tmp_replay_dir):
        store = ReplayStore(tmp_replay_dir, mode="record")
        request = {"headers": {"Authorization": "Bearer sk-secret123"}}
        response = {"ok": True}

        store.put("fetch", "https://example.test", request, response)

        key_hash = match_key_hash("https://example.test")
        written = json.loads((tmp_replay_dir / "fetch" / f"{key_hash}.json").read_text())
        assert written["request"]["headers"]["Authorization"] == "[redacted]"

    def test_record_mode_redacts_subscription_token(self, tmp_replay_dir):
        store = ReplayStore(tmp_replay_dir, mode="record")
        request = {"headers": {"X-Subscription-Token": "BSA_key123"}}
        response = {"ok": True}

        store.put("search", "test", request, response)

        key_hash = match_key_hash("test")
        written = json.loads((tmp_replay_dir / "search" / f"{key_hash}.json").read_text())
        assert written["request"]["headers"]["X-Subscription-Token"] == "[redacted]"

    def test_record_mode_redacts_api_key(self, tmp_replay_dir):
        store = ReplayStore(tmp_replay_dir, mode="record")
        request = {"api_key": "sk-secret123"}
        response = {"ok": True}

        store.put("model", "test", request, response)

        key_hash = match_key_hash("test")
        written = json.loads((tmp_replay_dir / "model" / f"{key_hash}.json").read_text())
        assert written["request"]["api_key"] == "[redacted]"


class TestMatchKeyHash:
    def test_deterministic(self):
        key = "https://example.test/page"
        assert match_key_hash(key) == match_key_hash(key)

    def test_is_sha256_hex(self):
        h = match_key_hash("test")
        assert len(h) == 64
        int(h, 16)  # valid hex
