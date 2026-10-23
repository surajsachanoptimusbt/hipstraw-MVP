"""The open-weight tier's client: endpoint from the environment, and the optional reasoning setting
(OPEN_WEIGHT_REASONING_EFFORT) that hosted reasoning models such as GLM-5.3-Flash need switched off."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from hipstraw_mm.adapters.llm import LLMClient, open_weight_client
from hipstraw_mm.adapters.replay import ReplayStore


class Answer(BaseModel):
    text: str


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs.append(kwargs)
        message = SimpleNamespace(content='{"text": "ok"}', refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            model=kwargs["model"],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3),
        )


def _with_fake(client: LLMClient) -> FakeCompletions:
    completions = FakeCompletions()
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return completions


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_WEIGHT_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPEN_WEIGHT_MODEL", "accounts/fireworks/models/glm-5p3-flash")
    monkeypatch.delenv("OPEN_WEIGHT_REASONING_EFFORT", raising=False)


def test_no_endpoint_means_no_open_weight_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPEN_WEIGHT_BASE_URL", raising=False)
    monkeypatch.delenv("OPEN_WEIGHT_MODEL", raising=False)
    assert open_weight_client(ReplayStore(None, "off"), None, 60) is None


def test_reasoning_effort_is_sent_when_set(endpoint: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_WEIGHT_REASONING_EFFORT", "none")
    client = open_weight_client(ReplayStore(None, "off"), None, 60)
    assert client is not None
    completions = _with_fake(client)
    assert client.parse(Answer, [{"role": "user", "content": "q"}], "k", "v1").text == "ok"
    assert completions.kwargs[0]["reasoning_effort"] == "none"
    assert completions.kwargs[0]["model"] == "accounts/fireworks/models/glm-5p3-flash"


def test_reasoning_effort_is_left_out_when_unset(endpoint: None) -> None:
    client = open_weight_client(ReplayStore(None, "off"), None, 60)
    assert client is not None
    completions = _with_fake(client)
    client.parse(Answer, [{"role": "user", "content": "q"}], "k", "v1")
    assert "reasoning_effort" not in completions.kwargs[0]


def test_frontier_client_never_sends_reasoning_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_WEIGHT_REASONING_EFFORT", "none")
    client = LLMClient(model="gpt-4o", replay=ReplayStore(None, "off"))
    completions = _with_fake(client)
    client.parse(Answer, [{"role": "user", "content": "q"}], "k", "v1")
    assert "reasoning_effort" not in completions.kwargs[0]
