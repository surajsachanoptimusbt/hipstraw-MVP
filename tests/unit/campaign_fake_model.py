"""A canned model client for the E2 Move tests: returns a prepared answer per schema, records each call."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

Answer = BaseModel | Callable[[list[dict[str, str]]], BaseModel]


class CannedClient:
    def __init__(self, answers: dict[str, Answer], model: str = "gpt-test") -> None:
        self.model = model
        self.answers = answers
        self.calls = 0
        self.prompts: list[list[dict[str, str]]] = []
        self.last_usage = {"inputTokens": 1200, "outputTokens": 300}
        self.last_raw: dict[str, Any] | None = None

    def parse(self, schema: type[BaseModel], messages: list[dict[str, str]], match_key: str, prompt_version: str,
              **_: Any) -> BaseModel:
        self.calls += 1
        self.prompts.append(messages)
        answer = self.answers[schema.__name__]
        result = answer(messages) if callable(answer) else answer
        self.last_raw = {"content": result.model_dump_json(), "model": f"{self.model}-served"}
        return result


@dataclass
class CannedModels:
    """Satisfies the router's ModelContext: a frontier client and no open-weight tier."""

    llm: Any
    open_llm: Any = None
    extra: dict[str, Any] = field(default_factory=dict)
